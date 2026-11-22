"""Build and verify itineraries. Only the user's plan and provider place IDs survive the run."""
import asyncio
import json
import logging
import math
from copy import deepcopy
from datetime import datetime, timedelta
from itertools import permutations

import httpx
from sqlalchemy import func, select, update

from . import config
from .db import engine
from .itinerary_agent import Timetable, candidate_schema, day_slots, fixed_start, instructions, ordered_timing, run_planner
from .models import generation_jobs as jobs
from .place_data import GooglePlaces, PlanningFailure
from .planning import DESTINATIONS
from .route_options import route_option
from .scheduling import Stop, VisitProblem, clock, fit_day, minutes


MAX_INPUT = 32000
MAX_OUTPUT = 6000
MAX_ATTEMPTS = 2
PRICES = {'gpt-6-luna': (0.1, 0.5), 'gpt-6.1-terra': (1, 5)}

# Live updates are local to the worker executing each job.
active_progress: dict[str, dict] = {}


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def cost(model, inputs, outputs):
    in_price, out_price = PRICES[model]
    return math.ceil((inputs * in_price + outputs * out_price) * config.generation_krw_per_usd / 1_000_000)


async def local_instant(zone, day, clock):
    local = datetime.fromisoformat(f'{day}T{clock}')
    async with engine.connect() as conn:
        return await conn.scalar(select(func.timezone(zone, local)))


async def leg_times(content, day, index):
    items = day['items']
    zone = content['destination']['timeZone']
    return (await local_instant(zone, day['date'], items[index]['endTime']),
            await local_instant(zone, day['date'], items[index+1]['startTime']))


async def local_today(zone):
    async with engine.connect() as conn:
        return (await conn.scalar(select(func.timezone(zone, func.now())))).date()


async def build(conditions, ask, client, report):
    places = GooglePlaces(client, config.maps_key)
    dest = DESTINATIONS[conditions.destinationId]
    zone = dest['timeZone']
    today = await local_today(zone)
    count = (conditions.endDate - conditions.startDate).days + 1
    place_cache, walk_cache = {}, {}

    async def lookup(label, slot, date):
        if label not in place_cache:
            place_cache[label] = await places.search(label, conditions.destinationId)
        return Stop.from_place(label, slot, place_cache[label], date, today)

    async def walking(stops, midnight):
        durations = []
        for left, right in zip(stops, stops[1:]):
            pair = left.place_id, right.place_id
            if None in pair or left.problem or right.problem:
                durations.append(None)
                continue
            if pair not in walk_cache:
                # WALK uses place IDs only. Check the actual visit-time gap when fitting the day.
                route = await route_option(client, config.maps_key, 'walking', *pair, midnight, midnight + timedelta(days=1))
                if route['status'] == 'lookup_failed':
                    raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE', 'route_lookup')
                walk_cache[pair] = route.get('durationMinutes')
            durations.append(walk_cache[pair])
        return durations

    async def fit_or_reorder(stops, timing, walks, day, fixed, midnight):
        try:
            return stops, timing, fit_day(stops, timing, walks, day, fixed), walks
        except VisitProblem as first:
            if first.reason not in ('time_conflict', 'no_walk', 'visit_window'):
                raise
            activities = [i for i, stop in enumerate(stops) if stop.slot == 'activity']
            # At most four activities. Prefer orders that move the fewest original visits.
            alternatives = sorted(permutations(activities), key=lambda order: sum(a != b for a, b in zip(activities, order)))
            for order in alternatives[1:]:
                reordered, times = stops.copy(), timing.copy()
                for target, source in zip(activities, order):
                    reordered[target] = stops[source]
                    visit = timing[source]
                    stay = minutes(visit.end) - minutes(visit.start)
                    start = min(minutes(timing[target].start), 1439 - stay)
                    times[target] = visit.model_copy(update={'start': clock(start), 'end': clock(start + stay)})
                try:
                    # Eliminate impossible opening-hour orders before looking up new legs.
                    fit_day(reordered, times, [0] * len(walks), day, fixed)
                    new_walks = await walking(reordered, midnight)
                    fitted = fit_day(reordered, times, new_walks, day, fixed)
                except VisitProblem:
                    continue
                return reordered, times, fitted, new_walks
            raise

    report('planning', 0)
    candidates = await ask('날짜별 자리 순서대로 서로 도보 이동이 편한 후보를 채운다. 이름과 같은 용도의 인근 대안만 반환한다.',
                           candidate_schema(conditions))
    days, evidence = [], []
    for index in range(count):
        day = index + 1
        report('checking', day, day)
        date = conditions.startDate + timedelta(days=index)
        midnight = await local_instant(zone, date, '00:00')
        names = getattr(candidates, f'day_{day}')
        stops = [await lookup(candidate.name, slot, date)
                 for candidate, slot in zip(names, day_slots(conditions, index), strict=True)]
        days.append((date, midnight, names, stops))
        evidence.append(dict(date=date.isoformat(), candidates=[s.evidence() for s in stops],
                             walkingMinutes=await walking(stops, midnight)))

    report('scheduling', 1 + count)
    schedule = await ask('각 날짜의 후보 번호(1부터)를 한 번씩 사용한다. hours는 현지 방문 가능 구간, '
                         'basis=unknown이면 영업정보가 없는 장소이므로 적절한 방문 시각을 제안한다. '
                         'walkingMinutes는 후보 순서에서 이웃 간 도보 분이다. null이면 이동시간이 확인되지 않았다. '
                         '체류시간과 이동 여유를 두고 식사 순서를 지킨다. 관광은 같은 날 안에서 재배치한다. '
                         '영업 불가 후보도 번호는 유지하여 서버가 해당 자리만 교체할 수 있게 한다.\n'
                         + compact_json(evidence), Timetable)
    if len(schedule.days) != count:
        raise PlanningFailure('VERIFICATION_FAILED', 'day_count')

    repaired = False
    content_days = []
    for index, (timing, data) in enumerate(zip(schedule.days, days)):
        date, midnight, names, candidates_for_day = data
        day = index + 1
        report('verifying', 2 + count + index, day)
        order = [v.candidate - 1 for v in timing]
        if sorted(order) != list(range(len(names))):
            raise PlanningFailure('VERIFICATION_FAILED', 'candidate_count', day)
        anchor = fixed_start(conditions, index)
        timing = ordered_timing(timing, [s.slot for s in candidates_for_day], anchor is not None)
        order = [v.candidate - 1 for v in timing]
        stops = [candidates_for_day[i] for i in order]
        free_slots = []
        hours_replacement = None
        fitted = []
        while stops:
            fixed = minutes(anchor) if anchor and stops[0].slot == 'breakfast' else None
            walks = await walking(stops, midnight)
            try:
                stops, timing, fitted, walks = await fit_or_reorder(stops, timing, walks, day, fixed, midnight)
                break
            except VisitProblem as issue:
                pos = issue.index
                hours_issue = issue.reason in ('closed', 'visit_window', 'time_conflict')
                if not repaired:
                    repaired = True
                    report('repairing', day=day)
                    alternative = names[timing[pos].candidate - 1].nearbyAlternative
                    replacement = await lookup(alternative, stops[pos].slot, date)
                    if not replacement.problem and replacement.place_id not in {s.place_id for s in stops}:
                        stops[pos] = replacement
                        if hours_issue:
                            hours_replacement = replacement
                        continue
                if not hours_issue:
                    if issue.reason != 'no_walk' or hours_replacement not in stops[max(0, pos-1):pos+1]:
                        raise
                    pos = stops.index(hours_replacement)
                free_slots.append(stops.pop(pos).slot)
                timing.pop(pos)

        items, legs = [], []
        for i, (stop, (start, end)) in enumerate(zip(stops, fitted)):
            item = dict(id=f'd{day}v{i+1}', order=i+1, kind='activity' if stop.slot == 'activity' else 'meal',
                        visitLabel=stop.label, startTime=start, endTime=end, place={'providerPlaceId': stop.place_id})
            if stop.basis in ('regular', 'unknown'):
                item['hoursBasis'] = stop.basis
            if items:
                depart = await local_instant(zone, date, items[-1]['endTime'])
                arrive = await local_instant(zone, date, start)
                if (arrive - depart).total_seconds() < walks[i-1]*60:
                    raise VisitProblem('time_conflict', day, i, stop.slot)
                legs.append(dict(fromItemId=items[-1]['id'], toItemId=item['id'], mode='walking'))
            items.append(item)
        content_days.append(dict(day=day, date=date.isoformat(), items=items, legs=legs))
        if free_slots:
            content_days[-1]['freeSlots'] = free_slots
    if not any(day['items'] for day in content_days):
        raise PlanningFailure('VERIFICATION_FAILED', 'no_visits')
    return dict(storage='place_ids', conditions=conditions.model_dump(mode='json'),
                destination={**dest, 'name': dest['label']}, transportMode='walking',
                mapProvider='google', days=content_days, unmetConstraints=[])


async def execute(job_id, conditions):
    inputs = outputs = attempts = 0
    uncertain = False
    # One candidate plan, one schedule, and two checks per travel day.
    total_steps = 2 + 2 * ((conditions.endDate - conditions.startDate).days + 1)
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
            displays = await asyncio.gather(*(places.display(item['place']['providerPlaceId']) for item in items))
            for item, place in zip(items, displays):
                item['place'] = place
            for i, leg in enumerate(day['legs']):
                depart, arrive = await leg_times(content, day, i)
                metrics = await route_option(client, config.maps_key, leg['mode'], items[i]['place']['providerPlaceId'],
                                             items[i+1]['place']['providerPlaceId'], depart, arrive)
                leg.update(metrics)
    return content
