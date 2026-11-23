import asyncio
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app import domain, generation
from app.itinerary_agent import candidate_task, day_slots, fixed_start, instructions
from app.place_data import GooglePlaces, PlanningFailure, in_destination, opening_windows
from app.planning import Conditions, DESTINATIONS
from app.route_options import route_choices
from app.scheduling import Stop, VisitProblem, fit_day, preferred_starts


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
        self.assertEqual(opening_windows({'id': 'park', 'currentOpeningHours': None, 'regularOpeningHours': None},
                                         date.today(), date.today()), ([], 'unknown', None))
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
                starts = preferred_starts(slots, fixed_start(conditions, i))
                self.assertEqual(len(starts), len(slots))
                self.assertEqual(starts, sorted(starts))

    def test_transfer_estimate_respects_distance_opening_and_verified_walk(self):
        first = Stop(label='First', slot='activity', place_id='a', location={'latitude': 0, 'longitude': 0},
                     stay=45, alternative='', windows=[(0, 1440)], basis='regular', problem=None)
        first_start = 13 * 60 + 15  # The first visit ends at 14:00.
        def schedule(km, walk=None, opens=0):
            second = replace(first, place_id='b', location={'latitude': km / 111.2, 'longitude': 0},
                             windows=[(opens, 1440)])
            return fit_day([first, second], [first_start, 14 * 60], [walk], 1, first_start)[1][0]

        self.assertEqual(schedule(0), '14:00')
        self.assertEqual(schedule(0.25), '14:05')
        self.assertEqual(schedule(0.251), '14:10')
        self.assertEqual(schedule(0.8), '14:20')
        self.assertEqual(schedule(0.8, opens=14 * 60 + 30), '14:30')
        self.assertEqual(schedule(3), '15:00')
        self.assertEqual(schedule(0.8, walk=9), '14:09')
        with self.assertRaises(VisitProblem) as distant:
            schedule(3.001)
        self.assertEqual(distant.exception.reason, 'unconfirmed_area')

    async def test_place_search_skips_other_city_in_same_response(self):
        def record(pid, region):
            return dict(id=pid, addressComponents=[
                {'types': ['country'], 'shortText': 'KR'},
                {'types': ['administrative_area_level_1'], 'longText': region},
                {'types': ['route'], 'longText': '인천'},
            ])
        results = [record('other', '부산광역시'), record('wanted', '인천광역시')]
        places = GooglePlaces(None, 'test')
        with patch.object(places, 'request', return_value={'places': results}) as request:
            self.assertEqual((await places.search('동명 식당', 'kr-incheon'))['id'], 'wanted')
            request.assert_awaited_once()
        with patch.object(places, 'request', return_value={'places': results[:1]}):
            self.assertIsNone(await places.search('동명 식당', 'kr-incheon'))

    def test_destination_address_respects_area_granularity(self):
        for city, country, areas, expected in (
            ('kr-jeju', 'KR', [('locality', '서귀포시'), ('administrative_area_level_1', '제주특별자치도')], True),
            ('kr-jeonju', 'KR', [('administrative_area_level_2', 'Jeonju-si')], True),
            ('jp-okinawa', 'JP', [('locality', 'Naha'), ('administrative_area_level_1', 'Okinawa Prefecture')], True),
            ('jp-osaka', 'JP', [('locality', 'Sakai'), ('administrative_area_level_1', 'Osaka Prefecture')], False),
            ('jp-kyoto', 'JP', [('locality', 'Kyōto-shi')], True),
            ('it-rome', 'IT', [('locality', 'Roma')], True),
            ('gb-london', 'GB', [('postal_town', 'London')], True),
            ('us-las-vegas', 'US', [('locality', 'Las Vegas'), ('administrative_area_level_1', 'NM')], False),
            ('us-new-york', 'US', [('sublocality_level_1', 'Brooklyn'), ('administrative_area_level_1', 'NY')], True),
            ('hk-hong-kong', 'HK', [], True),
            ('kr-incheon', 'KR', [], False), ('kr-incheon', 'JP', [('locality', '인천')], False),
        ):
            with self.subTest(city=city, areas=areas):
                parts = [{'types': ['country'], 'shortText': country}]
                parts.extend({'types': [level], 'shortText': name} for level, name in areas)
                self.assertEqual(in_destination({'addressComponents': parts}, DESTINATIONS[city]), expected)
        parts = [{'types': ['country'], 'shortText': 'US'},
                 {'types': ['locality'], 'longText': 'San Francisco'},
                 {'types': ['administrative_area_level_1'], 'longText': '캘리포니아주'}]
        self.assertTrue(in_destination({'addressComponents': parts}, DESTINATIONS['us-san-francisco']))

    async def generate(self, *, closed=(), unknown=(), no_walk=(), failed_routes=False, far=(), failed_places=(), hours=None, offsets_km=None):
        inputs = {}
        for d in range(3):
            slots = day_slots(self.conditions, d)
            names = [f'{d+1}-{i+1}' for i in range(len(slots))]
            if d == 1:
                names[1], names[3] = '박물관', '공원'
            inputs[f'day_{d+1}'] = [dict(name=n, nearbyAlternative=n+'대안', stayMinutes=45) for n in names]

        async def ask(task, output_type):
            return output_type(**inputs)

        async def search(name, _):
            if failed_places == 'all' or name in failed_places:
                raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE')
            periods = [{'open': {'day': 0, 'hour': 0}}]
            if name == '박물관':
                periods = [{'open': {'day': 6, 'hour': 14}, 'close': {'day': 6, 'hour': 18}}]
            if hours and name in hours:
                left, right = hours[name]
                periods = [{'open': {'day': 6, 'hour': left}, 'close': {'day': 6, 'hour': right}}]
            if name in closed or closed == 'all':
                periods = []
            p = dict(id=name, types=['restaurant'], regularOpeningHours={'periods': periods},
                     location={'latitude': 33.45, 'longitude': 126.95 if name in far else 126.50})
            if offsets_km and name in offsets_km:
                p['location']['latitude'] += offsets_km[name] / 111.2
            if name in unknown:
                del p['regularOpeningHours']
            return p

        def instant(zone, date, time):
            return datetime.fromisoformat(f'{date}T{time}').replace(tzinfo=timezone(timedelta(hours=9)))

        def leg_times(zone, date, items, indices):
            return {i: (instant(zone, date, items[i]['endTime']), instant(zone, date, items[i+1]['startTime']))
                    for i in indices}

        model = AsyncMock(side_effect=ask)
        def route(client, key, mode, start, end, *args):
            if failed_routes:
                return {'status': 'lookup_failed'}
            if no_walk == 'all' or (start, end) in no_walk:
                return {'status': 'no_route'}
            return {'status': 'verified', 'durationMinutes': 5}
        with (patch.object(generation, 'trip_calendar', side_effect=lambda zone, dates:
                    (date(2026, 12, 1), [instant(zone, d, '00:00') for d in dates])),
              patch.object(generation, 'day_leg_times', side_effect=leg_times),
              patch.object(generation.GooglePlaces, 'search', side_effect=search),
              patch.object(generation, 'route_option', side_effect=route)):
            result = await generation.build(self.conditions, model, None, lambda *args, **kwargs: None)
        return result, model.await_count

    async def test_move_morning_museum_to_afternoon_without_replacement(self):
        result, calls = await self.generate()
        items = result['days'][1]['items']
        self.assertEqual(calls, 1)
        self.assertEqual([(v['visitLabel'], v['startTime']) for v in items],
                         [('2-1','09:00'), ('공원','10:00'), ('2-3','12:00'), ('박물관','14:00'), ('2-5','18:00')])

    async def test_packed_day_fits_four_visits_around_meals(self):
        self.conditions = self.conditions.model_copy(update={'paceId': 'packed'})
        for windows in [((9, 12), (9, 12), (14, 17), (19, 23)),
                        ((9, 12), (14, 17), (21, 23), (21, 23))]:
            hours = dict(zip(['박물관', '공원', '2-5', '2-7'], windows))
            result, calls = await self.generate(hours=hours)
            day = result['days'][1]
            self.assertEqual(calls, 1)
            self.assertCountEqual([i['visitLabel'] for i in day['items'] if i['kind'] == 'activity'], hours.keys())
            self.assertNotIn('freeSlots', day)

    async def test_failed_place_search_only_drops_affected_slot(self):
        result, calls = await self.generate(failed_places={'1-1', '1-1대안'})
        self.assertEqual(calls, 1)
        self.assertEqual(result['days'][0]['freeSlots'], ['activity'])
        self.assertEqual([i['visitLabel'] for i in result['days'][0]['items']], ['1-2', '1-3', '1-4'])
        with self.assertRaises(PlanningFailure) as outage:
            await self.generate(failed_places='all')
        self.assertEqual(outage.exception.code, 'EXTERNAL_DATA_UNAVAILABLE')

    async def test_details_and_routes_overlap_and_detail_error_is_preserved(self):
        content, _ = await self.generate()
        route_started = asyncio.Event()
        async def display(pid):
            await asyncio.wait_for(route_started.wait(), 1)
            raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE')

        async def route(*args):
            route_started.set()
            return {'status': 'verified'}

        with (patch.object(generation.GooglePlaces, 'display', side_effect=display),
              patch.object(generation, 'day_leg_times', return_value={0: (None, None)}),
              patch.object(generation, 'route_option', side_effect=route),
              self.assertRaises(PlanningFailure) as outage):
            await generation.display_day(content, 1)
        self.assertEqual(outage.exception.code, 'EXTERNAL_DATA_UNAVAILABLE')

    async def test_one_replacement_keeps_neighbouring_times(self):
        result, calls = await self.generate(closed={'2-1'}, unknown={'2-1대안'})
        items = result['days'][1]['items']
        self.assertEqual(calls, 1)
        self.assertEqual(items[0]['hoursBasis'], 'unknown')
        self.assertEqual([(i['visitLabel'], i['startTime']) for i in items[:2]], [('2-1대안','09:00'), ('공원','10:00')])

    async def test_jeju_nearby_unconfirmed_routes_preserve_order_and_publish_without_metrics(self):
        self.conditions = self.conditions.model_copy(update={'destinationId': 'kr-jeju'})
        for failed in [False, True]:
            with self.subTest(lookup_failed=failed):
                result, calls = await self.generate(no_walk='all', failed_routes=failed)
                self.assertEqual(calls, 1)
                first = result['days'][0]
                self.assertEqual([i['visitLabel'] for i in first['items']], ['1-1', '1-2', '1-3', '1-4'])
                self.assertEqual(len(first['legs']), 3)
                for leg in first['legs']:
                    self.assertEqual(leg['status'], 'unverified')
                    self.assertNotIn('durationMinutes', leg)
                    self.assertNotIn('distanceMeters', leg)
                draft = dict(ownerId='u', version=1, status='success',
                             expiresAt=domain.now()+timedelta(hours=1), content=result)
                saved = domain.validate_draft(draft, 'u', domain.Save(draftId='draft', draftVersion=1))
                public = domain.public_copy(saved)
                self.assertTrue(all(p.get('outgoingRouteUnverified') for p in public['places'][:3]))
                self.assertNotIn('outgoingRouteUnverified', public['places'][3])

    def test_jeju_popularity_uses_selected_conditions_and_local_reference(self):
        jeju = self.conditions.model_copy(update={'destinationId': 'kr-jeju', 'interestIds': ['nature', 'food']})
        prompt = instructions(jeju) + candidate_task(jeju)
        for text in ['자연과 휴식', '맛집 탐방', '함덕해수욕장', '한국인 여행객', '2027-01-01', 'solo', 'relaxed']:
            self.assertIn(text, prompt)
        self.assertNotIn('함덕해수욕장', candidate_task(self.conditions))
        culture = candidate_task(jeju.model_copy(update={'interestIds': ['culture']}))
        self.assertIn('방주교회', culture)
        self.assertNotIn('함덕해수욕장', culture)

    async def test_reorders_unconfirmed_legs_before_using_a_free_slot(self):
        result, calls = await self.generate(no_walk='all', offsets_km={'1-1': 0, '1-2': 2, '1-3': 4, '1-4': 0.1})
        day = result['days'][0]
        self.assertEqual(calls, 1)
        self.assertEqual([i['visitLabel'] for i in day['items']], ['1-3', '1-2', '1-1', '1-4'])
        self.assertNotIn('freeSlots', day)
        self.assertTrue(all(leg['status'] == 'unverified' for leg in day['legs']))

    async def test_distant_first_stop_does_not_displace_the_rest_of_the_day(self):
        result, _ = await self.generate(no_walk='all', far={'1-1', '1-1대안'})
        first = result['days'][0]
        self.assertEqual(first['freeSlots'], ['activity'])
        self.assertEqual([item['visitLabel'] for item in first['items']], ['1-2', '1-3', '1-4'])

    async def test_unknown_venue_and_meal_hours_are_advisory_through_publication(self):
        result, calls = await self.generate(unknown={'1-1', '1-2'})
        self.assertEqual(calls, 1)
        self.assertEqual([(v['visitLabel'], v['hoursBasis']) for v in result['days'][0]['items'][:2]],
                         [('1-1', 'unknown'), ('1-2', 'unknown')])
        public = domain.public_copy(result)
        self.assertEqual([(v['name'], v['hoursBasis']) for v in public['places'][:2]],
                         [('1-1', 'unknown'), ('1-2', 'unknown')])

    async def test_closed_day_leaves_free_slots_and_rest_of_trip_is_savable(self):
        result, calls = await self.generate(closed={'1-1', '1-1대안', '1-2', '1-3', '1-4'})
        first = result['days'][0]
        self.assertEqual((first['items'], first['legs']), ([], []))
        self.assertCountEqual(first['freeSlots'], ['activity', 'meal', 'activity', 'meal'])
        self.assertEqual(calls, 1)
        draft = dict(ownerId='u', version=1, status='success', expiresAt=domain.now()+timedelta(hours=1), content=result)
        saved = domain.validate_draft(draft, 'u', domain.Save(draftId='draft', draftVersion=1))
        public = domain.public_copy(saved)
        self.assertEqual(public['freeSlots']['1'], first['freeSlots'])
        self.assertTrue(all(p['day'] > 1 for p in public['places']))

    async def test_closed_stop_with_unreachable_backup_reconnects_remaining_visits(self):
        result, _ = await self.generate(closed={'1-2'}, no_walk='all', far={'1-2대안'})
        first = result['days'][0]
        self.assertEqual(first['freeSlots'], ['meal'])
        self.assertEqual([item['visitLabel'] for item in first['items']], ['1-1','1-3','1-4'])
        self.assertEqual([(leg['fromItemId'], leg['toItemId']) for leg in first['legs']],
                         [('d1v1','d1v2'), ('d1v2','d1v3')])

    async def test_trip_with_no_visitable_places_does_not_issue_empty_draft(self):
        with self.assertRaises(PlanningFailure) as failure:
            await self.generate(closed='all')
        self.assertEqual(failure.exception.reason, 'no_visits')

    async def test_failure_accounting_retains_only_diagnostic_fields(self):
        async def failed(conditions, ask, client, report):
            report('repairing', day=2)
            raise PlanningFailure('VERIFICATION_FAILED', 'place_missing', 2, 'breakfast')

        db = MagicMock()
        write = db.begin.return_value.__aenter__.return_value.execute = AsyncMock()
        with (patch.object(generation, 'build', failed), patch.object(generation, 'engine', db),
              self.assertLogs(generation.__name__, level='WARNING') as logs):
            await generation.execute('test-job', self.conditions)
        values = write.await_args.args[0].compile().params
        self.assertEqual(values['status'], 'failed')
        self.assertEqual(values['content'], {'failure': dict(stage='repairing', day=2, reason='place_missing', slot='breakfast')})
        self.assertIn('place_missing', logs.output[0])
        self.assertNotIn('test-job', generation.active_progress)
