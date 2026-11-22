from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from .planning import DESTINATIONS


class PlanningFailure(Exception):
    def __init__(self, code, reason=None, day=None, slot=None):
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.day = day
        self.slot = slot


class GooglePlaces:
    def __init__(self, client, key):
        self.client = client
        self.key = key

    async def request(self, method, path, fields, **kwargs):
        try:
            result = await self.client.request(method, f'https://places.googleapis.com/v1/{path}',
                headers={'X-Goog-Api-Key': self.key, 'X-Goog-FieldMask': fields}, timeout=12, **kwargs)
            result.raise_for_status()
            return result.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE') from exc

    async def search(self, name, destination_id):
        dest = DESTINATIONS[destination_id]
        center = dest['mapCenter']
        result = await self.request('POST', 'places:searchText',
            'places.id,places.displayName,places.location,places.businessStatus,places.addressComponents,'
            'places.currentOpeningHours,places.regularOpeningHours,places.types',
            json={'textQuery': f"{name}, {dest['label']}, {dest['countryCode']}", 'languageCode': 'ko',
                  'pageSize': 1, 'locationBias': {'circle': {'center': center, 'radius': 25000}}})
        for place in result.get('places', []):
            country_ok = any('country' in a.get('types', []) and a.get('shortText') == dest['countryCode']
                             for a in place.get('addressComponents', []))
            if country_ok and place.get('id'):
                return place
        return None

    async def display(self, place_id):
        place = await self.request('GET', 'places/' + quote(place_id, safe=''),
                                   'id,displayName,location,attributions', params={'languageCode': 'ko'})
        try:
            return dict(provider='google', providerPlaceId=place_id,
                        name=place['displayName']['text'], **place['location'],
                        attributions=place.get('attributions', []))
        except KeyError as exc:
            raise PlanningFailure('EXTERNAL_DATA_UNAVAILABLE') from exc


def week_minute(point):
    return point['day'] * 1440 + point.get('hour', 0) * 60 + point.get('minute', 0)


def opening_windows(place, visit_date, local_today):
    """Return local minute intervals on this date, their source and any failure reason."""
    if not place:
        return [], None, 'place_missing'
    if place.get('businessStatus') in ('CLOSED_TEMPORARILY', 'CLOSED_PERMANENTLY', 'FUTURE_OPENING'):
        return [], None, 'closed'
    current = place.get('currentOpeningHours', {})
    dated = local_today <= visit_date < local_today + timedelta(days=7) and 'periods' in current
    hours = current if dated else place.get('regularOpeningHours', {})
    basis = 'current' if dated else 'regular'
    if not isinstance(hours.get('periods'), list):
        return [], 'unknown', None
    midnight = datetime.combine(visit_date, datetime.min.time())
    weekday = (visit_date.weekday() + 1) % 7
    windows = []
    incomplete = False
    for period in hours['periods']:
        opening = period.get('open', {})
        closing = period.get('close')
        if closing is None:
            if opening.get('day') == 0 and week_minute(opening) == 0:
                return [(0, 1440)], basis, None
            incomplete = True
            continue
        if dated and 'date' in opening and 'date' in closing:
            def local_point(p):
                return datetime.combine(date(**p['date']), datetime.min.time()).replace(
                    hour=p.get('hour', 0), minute=p.get('minute', 0))
            intervals = [((local_point(opening) - midnight) // timedelta(minutes=1),
                          (local_point(closing) - midnight) // timedelta(minutes=1))]
        elif 'day' in opening and 'day' in closing:
            left, right = week_minute(opening), week_minute(closing)
            if right <= left:
                right += 7 * 1440
            intervals = [(left - weekday*1440 - offset, right - weekday*1440 - offset)
                         for offset in (0, 7*1440)]
        else:
            incomplete = True
            continue
        for left, right in intervals:
            if max(0, left) < min(1440, right):
                windows.append((max(0, left), min(1440, right)))
    if not windows and incomplete:
        return [], 'unknown', None
    return sorted(windows), basis, None if windows else 'closed'
