"""Build and verify itineraries. Only the user's plan and provider place IDs survive the run."""
import json
from datetime import datetime, timedelta
from itertools import permutations

from sqlalchemy import func, select

from . import config
from .db import engine
from .itinerary_agent import Timetable, candidate_schema, day_slots, fixed_start, ordered_timing
from .place_data import GooglePlaces, PlanningFailure
from .planning import DESTINATIONS
from .route_options import route_option
from .scheduling import Stop, VisitProblem, clock, fit_day, minutes


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


async def local_instant(zone, day, clock):
    local = datetime.fromisoformat(f'{day}T{clock}')
    async with engine.connect() as conn:
        return await conn.scalar(select(func.timezone(zone, local)))


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
