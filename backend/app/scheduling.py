"""Fit a proposed day's visits into verified local opening and walking windows."""
from dataclasses import dataclass

from .place_data import PlanningFailure, opening_windows


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
    windows: list
    basis: str | None
    problem: str | None

    @classmethod
    def from_place(cls, label, slot, place, date, today):
        windows, basis, problem = opening_windows(place, date, today)
        if place and slot != 'activity':
            types = place.get('types', [])
            if not any(t.endswith('restaurant') or t in ('food', 'cafe', 'bakery', 'coffee_shop')
                       for t in types):
                problem = 'place_missing'
                windows = []
        return cls(label, slot, place['id'] if place else None, windows, basis, problem)

    def evidence(self):
        return dict(name=self.label, slot=self.slot, hours=[[clock(a), clock(b)] for a, b in self.windows],
                    basis=self.basis, issue=self.problem)


class VisitProblem(PlanningFailure):
    def __init__(self, reason, day, index, slot):
        code = 'ROUTE_UNAVAILABLE' if reason == 'no_walk' else 'VERIFICATION_FAILED'
        super().__init__(code, reason, day, slot)
        self.index = index


def fit_day(stops, timing, walks, day, first_start):
    """A backwards deadline pass preserves later commitments; the forward pass prefers model times."""
    intervals, durations = [], []
    lunch = next((i for i, stop in enumerate(stops) if stop.slot == 'lunch'), None)
    for i, (stop, visit) in enumerate(zip(stops, timing, strict=True)):
        start = minutes(visit.start)
        duration = minutes(visit.end) - start
        if duration <= 0:
            raise PlanningFailure('VERIFICATION_FAILED', 'visit_times', day, stop.slot)
        if stop.problem:
            raise VisitProblem(stop.problem, day, i, stop.slot)
        # Missing published hours leave the proposed visit flexible within the local day.
        bounds = [(0, 1440)] if stop.basis == 'unknown' else stop.windows
        windows = [(left, min(right, 1439) - duration) for left, right in bounds]
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

    for i, walk in enumerate(walks):
        if walk is None:
            raise VisitProblem('no_walk', day, i + 1, stops[i+1].slot)
    latest = [0] * len(stops)
    for i in reversed(range(len(stops))):
        limit = latest[i+1] - durations[i] - walks[i] if i < len(walks) else 1439
        possible = [min(right, limit) for left, right in intervals[i] if left <= limit]
        if not possible:
            raise VisitProblem('time_conflict', day, i, stops[i].slot)
        latest[i] = max(possible)

    fitted = []
    earliest = 0
    for i, windows in enumerate(intervals):
        preferred = minutes(timing[i].start)
        choices = [max(left, earliest, min(right, latest[i], preferred)) for left, right in windows
                   if max(left, earliest) <= min(right, latest[i])]
        start = min(choices, key=lambda t: abs(t - preferred))
        end = start + durations[i]
        fitted.append((clock(start), clock(end)))
        if i < len(walks):
            earliest = end + walks[i]
    return fitted
