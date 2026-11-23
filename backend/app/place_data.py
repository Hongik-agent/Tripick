import math
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from .planning import DESTINATIONS


# These destinations cover a whole first-level region, including its districts or islands.
REGIONAL_DESTINATIONS = {
    'kr-seoul', 'kr-incheon', 'kr-busan', 'kr-jeju', 'jp-tokyo', 'jp-okinawa',
    'cn-beijing', 'cn-shanghai', 'cn-chongqing', 'th-bangkok', 'th-phuket',
    'tw-taipei', 'tw-kaohsiung', 'tw-taichung', 'id-bali', 'id-jakarta',
}
AREA_ALIASES = {
    'kr-jeju': ('Jeju Special Self-Governing Province',),
    'jp-tokyo': ('東京',), 'jp-osaka': ('大阪',), 'jp-sapporo': ('札幌',), 'jp-kyoto': ('京都',),
    'jp-fukuoka': ('福岡',), 'jp-okinawa': ('沖縄',),
    'cn-beijing': ('北京',), 'cn-shanghai': ('上海',), 'cn-chongqing': ('重庆', '重慶'),
    'cn-chengdu': ('成都',), 'cn-qingdao': ('青岛', '青島'),
    'tw-taipei': ('臺北', '台北'), 'tw-kaohsiung': ('高雄',), 'tw-taichung': ('臺中', '台中'),
    'it-rome': ('Roma',), 'it-florence': ('Firenze',), 'it-venice': ('Venezia',), 'it-milan': ('Milano',),
    'es-seville': ('Sevilla',), 'gb-london': ('Greater London',),
    'us-new-york': ('Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'The Bronx', 'Staten Island'),
    'th-bangkok': ('Krung Thep Maha Nakhon', 'กรุงเทพมหานคร'), 'th-phuket': ('ภูเก็ต',),
    'th-chiang-mai': ('เชียงใหม่',),
}
US_STATES = {
    'us-new-york': ('ny', 'newyork', '뉴욕', '뉴욕주'), 'us-las-vegas': ('nv', 'nevada', '네바다', '네바다주'),
    'us-honolulu': ('hi', 'hawaii', '하와이', '하와이주'),
    'us-los-angeles': ('ca', 'california', '캘리포니아', '캘리포니아주'),
    'us-san-francisco': ('ca', 'california', '캘리포니아', '캘리포니아주'),
}


def area_key(name):
    folded = unicodedata.normalize('NFKD', name.casefold())
    unaccented = ''.join(c for c in folded if not unicodedata.combining(c))
    return ''.join(c for c in unicodedata.normalize('NFC', unaccented) if c.isalnum())


def in_destination(place, destination):
    parts = place.get('addressComponents') or []
    country = destination['countryCode']
    if not any('country' in part.get('types', ()) and part.get('shortText') == country for part in parts):
        return False
    if country in ('HK', 'MO'):
        return True
    city = destination['id']
    if city in US_STATES and not any(
        area_key(p.get(field) or '') in US_STATES[city]
        for p in parts if 'administrative_area_level_1' in p.get('types', ())
        for field in ('shortText', 'longText')
    ):
        return False
    names = {area_key(n) for n in (destination['label'], city.split('-', 1)[1], *AREA_ALIASES.get(city, ()))}
    levels = {'locality', 'postal_town', 'administrative_area_level_3'}
    if country in ('KR', 'CN', 'TW') or city == 'gb-london':
        levels.add('administrative_area_level_2')
    if city in REGIONAL_DESTINATIONS:
        levels.add('administrative_area_level_1')
    if city == 'us-new-york':
        levels.add('sublocality_level_1')
    suffixes = ('시', '광역시', '특별시', '특별자치도', '도', '현', '부', '市', '都', '県', '府',
                'city', 'metropolitancity', 'province', 'prefecture', 'metropolis', 'si', 'shi', 'do', 'to', 'ken')
    for part in parts:
        if levels.isdisjoint(part.get('types', ())):
            continue
        for field in ('longText', 'shortText'):
            key = area_key(part.get(field) or '')
            if key in names or any(key.endswith(s) and key[:-len(s)] in names for s in suffixes):
                return True
    return False


def distance_km(lat1, lon1, lat2, lon2):
    """Local straight-line approximation for grouping nearby places."""
    lon_delta = (lon2 - lon1 + 180) % 360 - 180
    return 111.2 * math.hypot(lat2 - lat1, lon_delta * math.cos(math.radians((lat1 + lat2) / 2)))


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
            'places.id,places.location,places.businessStatus,places.addressComponents,'
            'places.currentOpeningHours,places.regularOpeningHours,places.types',
            json={'textQuery': f"{name}, {dest['label']}, {dest['countryCode']}", 'languageCode': 'ko',
                  'pageSize': 3, 'locationBias': {'circle': {'center': center, 'radius': 25000}}})
        for place in result.get('places', []):
            if place.get('id') and in_destination(place, dest):
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
    current = place.get('currentOpeningHours') or {}
    dated = local_today <= visit_date < local_today + timedelta(days=7) and isinstance(current.get('periods'), list)
    hours = current if dated else place.get('regularOpeningHours') or {}
    basis = 'current' if dated else 'regular'
    if not isinstance(hours.get('periods'), list):
        return [], 'unknown', None
    midnight = datetime.combine(visit_date, datetime.min.time())
    weekday = (visit_date.weekday() + 1) % 7
    windows = []
    incomplete = False
    for period in hours['periods']:
        if not isinstance(period, dict):
            incomplete = True
            continue
        opening = period.get('open') or {}
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
