"""Compare generation through first-day hydration with fixed provider responses and latency."""
import asyncio
import os
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet

# An optional backend checkout lets the exact same fixture run against the baseline.
sys.path.insert(0, str(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL='postgresql+asyncpg://postgres@127.0.0.1:55440/tripick_test',
                  SUPABASE_URL='https://example.supabase.co', SUPABASE_PUBLISHABLE_KEY='test',
                  FRONTEND_ORIGIN='http://localhost', SESSION_ENCRYPTION_KEY=Fernet.generate_key().decode())

from app import generation
from app.itinerary_agent import day_slots
from app.place_data import PlanningFailure
from app.planning import Conditions


async def measure(missing_routes):
    calls = Counter()
    conditions = Conditions(destinationId='kr-jeju', startDate='2027-01-11', endDate='2027-01-13',
                            party={'typeId': 'family', 'sizeBand': '4'}, interestIds=['nature'],
                            paceId='relaxed', transportMode='walking', mapProvider='google')

    async def ask(task, schema):
        calls['model'] += 1
        await asyncio.sleep(0.060)
        if schema.__name__ == 'Timetable':  # Reference version requests a second model response.
            hours = [(10, 12, 14, 18), (9, 10, 12, 14, 18), (10, 12, 14, 18)]
            return schema(days=[[dict(candidate=i+1, start=f'{h:02}:00', end=f'{h:02}:45')
                                 for i, h in enumerate(day)] for day in hours])
        return schema(**{f'day_{d+1}': [dict(name=f'{d}-{i}', nearbyAlternative=f'{d}-alt-{i}', stayMinutes=45)
                                        for i in range(len(day_slots(conditions, d)))] for d in range(3)})

    async def search(name, destination):
        calls['search'] += 1
        await asyncio.sleep(0.015)
        return dict(id=name, types=['restaurant'], location=dict(latitude=33.5, longitude=126.52 + int(name[-1]) * .001))

    async def route(client, key, mode, left, right, depart, arrive):
        calls['route'] += 1
        await asyncio.sleep(0.015)
        if missing_routes:
            return dict(mode=mode, status='no_route')
        return dict(mode=mode, status='verified', durationMinutes=5, distanceMeters=300)

    async def display(pid):
        calls['display'] += 1
        await asyncio.sleep(0.015)
        return dict(name=pid, providerPlaceId=pid, latitude=33.5, longitude=126.52)

    def instant(zone, day, time):
        return datetime.fromisoformat(f'{day}T{time}').replace(tzinfo=timezone.utc)

    async def leg_times(zone, day, items, indices):
        if indices:
            calls['leg_time_batches'] += 1
        return {i: (instant(zone, day, items[i]['endTime']), instant(zone, day, items[i+1]['startTime']))
                for i in indices}

    stages = []
    async def calendar(zone, dates):
        return date(2027, 1, 10), [instant(zone, day, '00:00') for day in dates]

    with (patch.object(generation, 'local_today', return_value=date(2027, 1, 10), create=True),
          patch.object(generation, 'local_instant', side_effect=instant, create=True),
          patch.object(generation, 'trip_calendar', calendar, create=True),
          patch.object(generation, 'day_leg_times', leg_times, create=True),
          patch.object(generation.GooglePlaces, 'search', AsyncMock(side_effect=search)),
          patch.object(generation.GooglePlaces, 'display', AsyncMock(side_effect=display)),
          patch.object(generation, 'route_option', side_effect=route),
          patch.object(generation.httpx, 'AsyncClient')):
        start = perf_counter()
        try:
            content = await generation.build(conditions, ask, None, lambda s, *args, **kw: stages.append(s))
            await generation.display_day(content, 1)
            outcome = f"{sum(len(d['items']) for d in content['days'])} visits"
        except PlanningFailure as exc:
            outcome = f'day {exc.day}, {stages[-1]}, {exc.reason}'
        return (perf_counter() - start) * 1000, outcome, dict(calls)


async def main():
    for missing in (False, True):
        samples = [await measure(missing) for _ in range(5)]
        elapsed, outcomes, counts = zip(*samples)
        assert len(set(outcomes)) == 1 and all(c == counts[0] for c in counts)
        print(f'missing_routes={missing}, median={statistics.median(elapsed):.0f} ms, {outcomes[0]}, {counts[0]}', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
