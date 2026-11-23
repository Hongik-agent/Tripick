"""Fit a proposed day's visits into verified local opening and walking windows."""
from dataclasses import dataclass
from itertools import permutations
from math import ceil

from .place_data import PlanningFailure, distance_km, opening_windows


MEAL_START_WINDOWS = {'breakfast': (360, 630), 'lunch': (660, 870), 'dinner': (1020, 1260)}


def minutes(clock):
    hour, minute = map(int, clock.split(':'))
    return hour * 60 + minute


def clock(minute):
    return f'{minute // 60:02d}:{minute % 60:02d}'


@dataclass
class Stop:
    label: str
    slot: str
    place_id: str | None
    location: dict
    stay: int
    alternative: str
    windows: list
    basis: str | None
    problem: str | None

    @classmethod
    def from_place(cls, candidate, slot, place, date, today):
        windows, basis, problem = opening_windows(place, date, today)
        if place and slot != 'activity':
            types = place.get('types', [])
            if not any(t.endswith('restaurant') or t in ('food', 'cafe', 'bakery', 'coffee_shop')
                       for t in types):
                problem = 'place_missing'
                windows = []
        return cls(candidate.name, slot, place['id'] if place else None, (place or {}).get('location') or {},
                   candidate.stayMinutes, candidate.nearbyAlternative, windows, basis, problem)

    def nearby_distance_km(self, other) -> float | None:
        """Return the coordinate distance only for stops within the 3 km fallback radius."""
        for location in (self.location, other.location):
            if not all(type(location.get(k)) in (float, int) and -bound <= location[k] <= bound
                       for k, bound in [('latitude', 90), ('longitude', 180)]):
                return None
        km = distance_km(self.location['latitude'], self.location['longitude'],
                         other.location['latitude'], other.location['longitude'])
        return km if km <= 3 else None


class VisitProblem(PlanningFailure):
    def __init__(self, reason, day, index, slot):
        super().__init__('VERIFICATION_FAILED', reason, day, slot)
        self.index = index


def preferred_starts(slots, first_start):
    if first_start:
        hours = {5: (10, 12, 14, 18), 6: (10, 12, 14, 18, 20), 7: (10, 12, 14, 16, 18, 20)}
        return [minutes(first_start)] + [hour * 60 for hour in hours[len(slots)]]
    hours = {4: (10, 12, 14, 18), 5: (10, 12, 14, 16, 18), 6: (10, 12, 14, 15.5, 17, 18)}
    return [int(hour * 60) for hour in hours[len(slots)]]


def alternative_orders(stops, starts):
    activities = tuple(i for i, stop in enumerate(stops) if stop.slot == 'activity')
    meals = [stop for stop in stops if stop.slot != 'activity']
    layouts = [(activities, starts)]
    if len(activities) == 4 and [stop.slot for stop in meals] == ['breakfast', 'lunch', 'dinner']:
        # A packed full day can fit its fourth visit before lunch or after dinner as well.
        layouts.extend([((1, 2, 4, 6), [480, 540, 630, 720, 840, 1080, 1200]),
                        ((1, 3, 5, 6), [480, 600, 720, 840, 1080, 1140, 1230])])
    orders = sorted(permutations(activities), key=lambda order: sum(a != b for a, b in zip(activities, order)))
    for order in orders:
        for positions, preferred in layouts:
            if order == activities and positions == activities:
                continue
            visits = dict(zip(positions, (stops[i] for i in order)))
            meal_order = iter(meals)
            yield [visits[i] if i in visits else next(meal_order) for i in range(len(stops))], preferred


def fit_day(stops, starts, walks, day, first_start):
    """Fit suggested visits around actual opening windows and known transfer durations."""
    intervals, durations = [], []
    seen_places = set()
    lunch = next((i for i, stop in enumerate(stops) if stop.slot == 'lunch'), None)
    for i, (stop, preferred) in enumerate(zip(stops, starts, strict=True)):
        duration = stop.stay
        if stop.problem:
            raise VisitProblem(stop.problem, day, i, stop.slot)
        if stop.place_id in seen_places:
            raise VisitProblem('duplicate_place', day, i, stop.slot)
        seen_places.add(stop.place_id)
        # Missing published hours leave the proposed visit flexible within the local day.
        bounds = [(0, 1440)] if stop.basis == 'unknown' else stop.windows
        windows = [(left, min(right, 1439) - duration) for left, right in bounds]
        meal = ('lunch' if preferred == 720 else 'dinner') if stop.slot == 'meal' else stop.slot
        if meal in MEAL_START_WINDOWS:
            earliest, latest = MEAL_START_WINDOWS[meal]
            windows = [(max(left, earliest), min(right, latest)) for left, right in windows]
        if lunch is not None and stop.slot == 'activity':
            if i < lunch:
                windows = [(left, min(right, 719)) for left, right in windows]
            else:
                windows = [(max(left, 720), right) for left, right in windows]
        fixed = first_start if i == 0 else None
        if fixed is not None:
            windows = [(fixed, fixed) for left, right in windows if left <= fixed <= right]
        windows = [(left, right) for left, right in windows if left <= right]
        if not windows:
            raise VisitProblem('visit_window', day, i, stop.slot)
        intervals.append(windows)
        durations.append(duration)

    gaps = []
    for i, walk in enumerate(walks):
        if walk is None:
            km = stops[i].nearby_distance_km(stops[i+1])
            if km is None:
                raise VisitProblem('unconfirmed_area', day, i + 1, stops[i+1].slot)
            # Allow 2 minutes per 100 m, rounded up to a 5-minute interval.
            walk = 5 * ceil(km * 20 / 5)
        gaps.append(walk)
    latest = [0] * len(stops)
    for i in reversed(range(len(stops))):
        limit = latest[i+1] - durations[i] - gaps[i] if i < len(gaps) else 1439
        possible = [min(right, limit) for left, right in intervals[i] if left <= limit]
        if not possible:
            raise VisitProblem('time_conflict', day, i, stops[i].slot)
        latest[i] = max(possible)

    fitted = []
    earliest = 0
    for i, windows in enumerate(intervals):
        preferred = starts[i]
        choices = [max(left, earliest, min(right, latest[i], preferred)) for left, right in windows
                   if max(left, earliest) <= min(right, latest[i])]
        start = min(choices, key=lambda t: abs(t - preferred))
        end = start + durations[i]
        fitted.append((clock(start), clock(end)))
        if i < len(gaps):
            earliest = end + gaps[i]
    return fitted
