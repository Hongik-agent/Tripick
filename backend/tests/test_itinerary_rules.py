import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx

from app import generation
from app.itinerary_agent import Timetable, day_slots
from app.place_data import PlanningFailure, opening_windows
from app.planning import Conditions
from app.route_options import route_choices


class ItineraryRules(unittest.IsolatedAsyncioTestCase):
    async def test_modes_and_failed_lookup_are_independent(self):
        def respond(request):
            import json
            mode = json.loads(request.content)['travelMode']
            if mode == 'TRANSIT':
                return httpx.Response(200, json={})
            if mode == 'DRIVE':
                return httpx.Response(503)
            return httpx.Response(200, json={'routes': [{'duration': '1801s', 'distanceMeters': 2100}]})

        start = datetime(2027, 1, 2, 10, tzinfo=timezone.utc)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            options = await route_choices(client, 'test', 'a', 'b', start, start + timedelta(minutes=30))
            self.assertEqual([item['status'] for item in options], ['time_conflict', 'no_route', 'lookup_failed'])
            options = await route_choices(client, 'test', 'a', 'b', start, start + timedelta(minutes=31))
            self.assertEqual(options[0]['status'], 'verified')
            self.assertEqual(options[0]['durationMinutes'], 31)

    def setUp(self):
        self.conditions = Conditions(destinationId='jp-tokyo', startDate='2027-01-01', endDate='2027-01-03',
                                     party={'typeId':'solo','sizeBand':'1'}, interestIds=['food'],
                                     paceId='relaxed', transportMode='walking', mapProvider='google')

    def test_date_specific_hours_override_regular_and_split_at_midnight(self):
        period = {'open': {'day': 6, 'hour': 22}, 'close': {'day': 0, 'hour': 2}}
        place = {'regularOpeningHours': {'periods': [period]}, 'currentOpeningHours': {'periods': []}}
        self.assertEqual(opening_windows(place, date(2027, 1, 3), date(2027, 1, 1)), ([], 'current', 'closed'))
        self.assertEqual(opening_windows(place, date(2027, 1, 3), date(2026, 12, 1)), ([(0, 120)], 'regular', None))
        self.assertEqual(opening_windows({}, date.today(), date.today())[2], 'place_missing')
        self.assertEqual(opening_windows({'id': 'park'}, date.today(), date.today()), ([], 'unknown', None))
        dated = {'currentOpeningHours': {'periods': [{'open': {'date': {'year': 2027, 'month': 1, 'day': 3}, 'hour': 9},
                                                      'close': {'date': {'year': 2027, 'month': 1, 'day': 3}, 'hour': 18}}]}}
        self.assertEqual(opening_windows(dated, date(2027, 1, 3), date(2027, 1, 1)), ([(540, 1080)], 'current', None))

    def test_density_templates(self):
        for pace, activities in [('relaxed', 2), ('balanced', 3), ('packed', 4)]:
            conditions = self.conditions.model_copy(update={'paceId': pace})
            for i, expected_meals in enumerate([2, 3, 2]):
                slots = day_slots(conditions, i)
                self.assertEqual(slots.count('activity'), activities)
                self.assertEqual(len(slots) - activities, expected_meals)

    async def generate(self, *, closed=(), unknown=(), museum_first=False, no_walk=()):
        inputs = {}
        schedules = []
        for d in range(3):
            slots = day_slots(self.conditions, d)
            names = [f'{d+1}-{i+1}' for i in range(len(slots))]
            if d == 1:
                names[1], names[3] = '박물관', '공원'
            inputs[f'day_{d+1}'] = [dict(name=n, nearbyAlternative=n+'대안') for n in names]
            order = [1, 4, 3, 2, 5] if d == 1 else [1, 2, 3, 4]
            if museum_first and d == 1:
                order = [1, 2, 3, 4, 5]
            starts = [8, 10, 12, 14, 18] if d == 1 else [10, 12, 14, 18]
            schedules.append([dict(candidate=n, start=f'{h:02}:00', end=f'{h:02}:30') for n, h in zip(order, starts)])

        async def ask(task, output_type):
            if output_type is Timetable:
                self.assertIn('"walkingMinutes":', task)
                if unknown and not closed:
                    self.assertIn('"hours":[],"basis":"unknown","issue":null', task)
                return Timetable(days=schedules)
            return output_type(**inputs)

        async def search(name, _):
            periods = [{'open': {'day': 0, 'hour': 0}}]
            if name == '박물관':
                periods = [{'open': {'day': 6, 'hour': 14}, 'close': {'day': 6, 'hour': 18}}]
            if name in closed or closed == 'all':
                periods = []
            p = dict(id=name, types=['restaurant'], regularOpeningHours={'periods': periods})
            if name in unknown:
                del p['regularOpeningHours']
            return p

        def instant(zone, date, time):
            return datetime.fromisoformat(f'{date}T{time}').replace(tzinfo=timezone(timedelta(hours=9)))

        model = AsyncMock(side_effect=ask)
        def route(client, key, mode, start, end, *args):
            if (start, end) in no_walk:
                return {'status': 'no_route'}
            return {'status': 'verified', 'durationMinutes': 5}
        with (patch.object(generation, 'local_today', return_value=date(2026, 12, 1)),
              patch.object(generation, 'local_instant', side_effect=instant),
              patch.object(generation.GooglePlaces, 'search', side_effect=search),
              patch.object(generation, 'route_option', side_effect=route)):
            result = await generation.build(self.conditions, model, None, lambda *args, **kwargs: None)
        return result, model.await_count

    async def test_move_morning_museum_to_afternoon_without_replacement(self):
        result, calls = await self.generate()
        items = result['days'][1]['items']
        self.assertEqual(calls, 2)
        self.assertEqual([(v['visitLabel'], v['startTime']) for v in items],
                         [('2-1','09:00'), ('공원','10:00'), ('2-3','12:00'), ('박물관','14:00'), ('2-5','18:00')])

    async def test_one_replacement_keeps_neighbouring_times(self):
        result, calls = await self.generate(closed={'2-1'}, unknown={'2-1대안'})
        items = result['days'][1]['items']
        self.assertEqual(calls, 2)
        self.assertEqual(items[0]['hoursBasis'], 'unknown')
        self.assertEqual([(i['visitLabel'], i['startTime']) for i in items[:2]], [('2-1대안','09:00'), ('공원','10:00')])

    async def test_server_swaps_activities_if_model_keeps_closed_morning_slot(self):
        result, calls = await self.generate(museum_first=True)
        items = result['days'][1]['items']
        self.assertEqual(calls, 2)
        self.assertEqual([v['visitLabel'] for v in items], ['2-1', '공원', '2-3', '박물관', '2-5'])
        self.assertLess(items[1]['startTime'], '12:00')
        self.assertGreaterEqual(items[3]['startTime'], '14:00')

    async def test_closed_stop_with_unreachable_backup_reconnects_remaining_visits(self):
        result, _ = await self.generate(closed={'1-2'}, no_walk={('1-2대안','1-3'), ('1-2대안','1-1')})
        first = result['days'][0]
        self.assertEqual(first['freeSlots'], ['meal'])
        self.assertEqual([item['visitLabel'] for item in first['items']], ['1-1','1-3','1-4'])
        self.assertEqual([(leg['fromItemId'], leg['toItemId']) for leg in first['legs']],
                         [('d1v1','d1v2'), ('d1v2','d1v3')])

    async def test_trip_with_no_visitable_places_does_not_issue_empty_draft(self):
        with self.assertRaises(PlanningFailure) as failure:
            await self.generate(closed='all')
        self.assertEqual(failure.exception.reason, 'no_visits')
