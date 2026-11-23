"""Build and verify itineraries. Only the user's plan and provider place IDs survive the run."""
import asyncio
import json
import logging
import math
from copy import deepcopy
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select, update

from . import config
from .db import engine
from .itinerary_agent import Candidate, candidate_schema, candidate_task, day_slots, fixed_start, instructions, run_planner
from .models import generation_jobs as jobs
from .place_data import GooglePlaces, PlanningFailure
from .planning import DESTINATIONS
from .route_options import route_option
from .scheduling import Stop, VisitProblem, alternative_orders, fit_day, minutes, preferred_starts


MAX_INPUT = 32000
MAX_OUTPUT = 6000
MAX_ATTEMPTS = 1
PRICES = {'gpt-6-luna': (0.1, 0.5), 'gpt-6.1-terra': (1, 5)}

# Live updates are local to the worker executing each job.
active_progress: dict[str, dict] = {}


def cost(model, inputs, outputs):
    in_price, out_price = PRICES[model]
    return math.ceil((inputs * in_price + outputs * out_price) * config.generation_krw_per_usd / 1_000_000)


async def trip_calendar(zone, dates):
    midnights = [func.timezone(zone, datetime.combine(day, datetime.min.time())) for day in dates]
    async with engine.connect() as conn:
        today, *instants = (await conn.execute(select(func.timezone(zone, func.now()), *midnights))).one()
    return today.date(), instants


async def day_leg_times(zone, date, items, indices):
    """Convert all requested departure/arrival pairs in one PostgreSQL timezone query."""
    if not indices:
        return {}
    conversions = []
    for i in indices:
        for clock in (items[i]['endTime'], items[i+1]['startTime']):
            conversions.append(func.timezone(zone, datetime.fromisoformat(f'{date}T{clock}')))
    async with engine.connect() as conn:
        times = (await conn.execute(select(*conversions))).one()
    return {i: (times[2*n], times[2*n+1]) for n, i in enumerate(indices)}


async def build(conditions, ask, client, report):
    places = GooglePlaces(client, config.maps_key)
    dest = DESTINATIONS[conditions.destinationId]
    zone = dest['timeZone']
    count = (conditions.endDate - conditions.startDate).days + 1
    dates = [conditions.startDate + timedelta(days=i) for i in range(count)]
    today, midnights = await trip_calendar(zone, dates)
    place_cache, walk_cache = {}, {}
    search_failed = False

    async def search(name):
        nonlocal search_failed
        try:
            return await places.search(name, conditions.destinationId)
        except PlanningFailure as exc:
            if exc.code != 'EXTERNAL_DATA_UNAVAILABLE':
                raise
            search_failed = True
            return None

    async def resolve(candidates, slots, date):
        missing = list(dict.fromkeys(c.name for c in candidates if c.name not in place_cache))
        results = await asyncio.gather(*(search(name) for name in missing))
        place_cache.update(zip(missing, results))
        return [Stop.from_place(c, slot, place_cache[c.name], date, today)
                for c, slot in zip(candidates, slots, strict=True)]

    async def walking(stops, midnight):
        pairs = [(left.place_id, right.place_id) if not (left.problem or right.problem) else None
                 for left, right in zip(stops, stops[1:])]
        missing = list(dict.fromkeys(pair for pair in pairs if pair and pair not in walk_cache))
        routes = await asyncio.gather(*(route_option(client, config.maps_key, 'walking', *pair,
                                                     midnight, midnight + timedelta(days=1)) for pair in missing))
        for pair, route in zip(missing, routes):
            walk_cache[pair] = route.get('durationMinutes')
        return [walk_cache.get(pair) for pair in pairs]

    async def fit_or_reorder(stops, starts, day, fixed, midnight):
        walks = await walking(stops, midnight)
        try:
            return stops, fit_day(stops, starts, walks, day, fixed), walks
        except VisitProblem as first:
            if first.reason not in ('time_conflict', 'visit_window', 'unconfirmed_area'):
                raise
            for reordered, preferred in alternative_orders(stops, starts):
                try:
                    # Reject impossible orders from known legs before requesting any new pairs.
                    known_walks = [walk_cache.get((a.place_id, b.place_id), 0)
                                   for a, b in zip(reordered, reordered[1:])]
                    fit_day(reordered, preferred, known_walks, day, fixed)
                    new_walks = await walking(reordered, midnight)
                    fitted = fit_day(reordered, preferred, new_walks, day, fixed)
                except VisitProblem:
                    continue
                return reordered, fitted, new_walks
            raise

    report('planning', 0)
    candidates = await ask(candidate_task(conditions), candidate_schema(conditions))
    repaired = False
    content_days = []
    for index, (date, midnight) in enumerate(zip(dates, midnights, strict=True)):
        day = index + 1
        report('checking', 1 + 2 * index, day)
        slots = day_slots(conditions, index)
        stops = await resolve(getattr(candidates, f'day_{day}'), slots, date)
        anchor = fixed_start(conditions, index)
        starts = preferred_starts(slots, anchor)
        report('verifying', 2 + 2 * index, day)
        free_slots = []
        replacement = None
        fitted = []
        while stops:
            fixed = minutes(anchor) if anchor and stops[0].slot == 'breakfast' else None
            try:
                stops, fitted, walks = await fit_or_reorder(stops, starts, day, fixed, midnight)
                break
            except VisitProblem as issue:
                pos = issue.index
                if issue.reason == 'unconfirmed_area':
                    left, right = stops[pos-1:pos+1]
                    if replacement in (left, right):
                        pos = stops.index(replacement)
                    elif (sum(left.nearby_distance_km(s) is not None for s in stops) <
                          sum(right.nearby_distance_km(s) is not None for s in stops)):
                        pos -= 1  # Keep the cluster, including when the first place was the outlier.
                stop = stops[pos]
                if not repaired:
                    repaired = True
                    report('repairing', day=day)
                    alternate = Candidate(name=stop.alternative, nearbyAlternative=stop.label, stayMinutes=stop.stay)
                    backup, = await resolve([alternate], [stop.slot], date)
                    if not backup.problem and backup.place_id not in {s.place_id for s in stops}:
                        stops[pos] = replacement = backup
                        continue
                free_slots.append(stops.pop(pos).slot)
                starts.pop(pos)

        items, legs = [], []
        for i, (stop, (start, end)) in enumerate(zip(stops, fitted)):
            item = dict(id=f'd{day}v{i+1}', order=i+1, kind='activity' if stop.slot == 'activity' else 'meal',
                        visitLabel=stop.label, startTime=start, endTime=end, place={'providerPlaceId': stop.place_id})
            if stop.basis in ('regular', 'unknown'):
                item['hoursBasis'] = stop.basis
            if items:
                leg = dict(fromItemId=items[-1]['id'], toItemId=item['id'], mode='walking')
                if walks[i-1] is None:
                    leg['status'] = 'unverified'
                legs.append(leg)
            items.append(item)
        verified = [i for i, leg in enumerate(legs) if leg.get('status') != 'unverified']
        for i, (depart, arrive) in (await day_leg_times(zone, date, items, verified)).items():
            if (arrive - depart).total_seconds() < walks[i]*60:
                raise VisitProblem('time_conflict', day, i+1, stops[i+1].slot)
        content_days.append(dict(day=day, date=date.isoformat(), items=items, legs=legs))
        if free_slots:
            content_days[-1]['freeSlots'] = free_slots
    if not any(day['items'] for day in content_days):
        if search_failed:
            raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE', 'place_lookup')
        raise PlanningFailure('VERIFICATION_FAILED', 'no_visits')
    return dict(storage='place_ids', conditions=conditions.model_dump(mode='json'),
                destination={**dest, 'name': dest['label']}, transportMode='walking',
                mapProvider='google', days=content_days, unmetConstraints=[])


async def execute(job_id, conditions):
    inputs = outputs = attempts = 0
    uncertain = False
    total_steps = 1 + 2 * ((conditions.endDate - conditions.startDate).days + 1)
    completed_steps = 0

    def report(stage, completed=0, day=None):
        nonlocal completed_steps
        # A replacement repeats checks already counted for this request.
        completed_steps = max(completed_steps, completed)
        progress = dict(stage=stage, percent=100 * completed_steps // total_steps)
        if day is not None:
            progress['day'] = day
        active_progress[job_id] = progress

    async def ask(task, output_type):
        nonlocal inputs, outputs, attempts, uncertain
        # UTF-8 bytes bound ordinary tokenizer output. Include the structured response schema and framing.
        size = len((instructions(conditions)+task+json.dumps(output_type.model_json_schema())).encode()) + 2048
        if size > MAX_INPUT:
            raise PlanningFailure('GENERATION_FAILED', 'input_limit')
        if attempts >= MAX_ATTEMPTS:
            raise PlanningFailure('GENERATION_FAILED', 'call_limit')
        attempts += 1
        uncertain = True
        result = await run_planner(conditions, task, config.openai_key, output_type)
        usage = result.context_wrapper.usage
        inputs += usage.input_tokens
        outputs += usage.output_tokens
        uncertain = not usage.total_tokens
        return result.final_output

    values = {}
    try:
        async with asyncio.timeout(540), httpx.AsyncClient() as client:
            content = await build(conditions, ask, client, report)
        values.update(content=content, status='completed')
    except PlanningFailure as exc:
        current = active_progress.get(job_id, {})
        detail = dict(stage=current.get('stage'), day=exc.day or current.get('day'),
                      reason=exc.reason or exc.code, slot=exc.slot)
        logging.getLogger(__name__).warning('Generation %s failed: %s', job_id, detail)
        values.update(status='failed', error_code=exc.code, content={'failure': detail})
    except Exception as exc:
        current = active_progress.get(job_id, {})
        detail = dict(stage=current.get('stage'), day=current.get('day'), reason='generation_error')
        logging.getLogger(__name__).warning('Generation %s failed (%s): %s', job_id, type(exc).__name__, detail)
        values.update(status='failed', error_code='GENERATION_FAILED', content={'failure': detail})
    finally:
        active_progress.pop(job_id, None)
    if not uncertain:
        values['cost_krw'] = cost(conditions.modelId, inputs, outputs)
    values.update(input_tokens=inputs, output_tokens=outputs)
    async with engine.begin() as conn:
        await conn.execute(update(jobs).where(jobs.c.id == job_id, jobs.c.status == 'running').values(**values))


async def display_day(content, number):
    if content.get('storage') != 'place_ids':
        return content
    content = deepcopy(content)
    async with httpx.AsyncClient() as client:
        places = GooglePlaces(client, config.maps_key)
        for day in content['days']:
            if day['day'] != number:
                day.update(items=[], legs=[])
                day.pop('freeSlots', None)
                continue
            items = day['items']
            async def refresh(i, depart, arrive):
                leg = day['legs'][i]
                metrics = await route_option(client, config.maps_key, leg['mode'], items[i]['place']['providerPlaceId'],
                                             items[i+1]['place']['providerPlaceId'], depart, arrive)
                leg.update(metrics)

            # Both lookups use the stored place IDs. Cancel sibling requests on a detail failure.
            try:
                async with asyncio.TaskGroup() as group:
                    details = [group.create_task(places.display(item['place']['providerPlaceId'])) for item in items]
                    indices = [i for i, leg in enumerate(day['legs']) if leg.get('status') != 'unverified']
                    times = await day_leg_times(content['destination']['timeZone'], day['date'], items, indices)
                    for i, (depart, arrive) in times.items():
                        group.create_task(refresh(i, depart, arrive))
            except* PlanningFailure as errors:
                raise errors.exceptions[0]
            for item, detail in zip(items, details):
                item['place'] = detail.result()
    return content
