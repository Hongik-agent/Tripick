"""In-memory domestic itinerary references from Korea Tourism Organization's KorService2."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import unquote, urlencode
from urllib.request import urlopen

from . import config
from .domestic_candidates import DOMESTIC_CANDIDATES, DOMESTIC_SURVEY_PLACES, domestic_hints
from .place_data import distance_km
from .planning import DESTINATIONS


BASE_URL = 'https://apis.data.go.kr/B551011'
INTERESTS_BY_CLASS = {
    'NA': ('nature',), 'HS': ('culture', 'local_culture'), 'VE': ('culture',),
    'EX': ('activity', 'local_culture'), 'LS': ('activity',), 'SH': ('shopping',), 'FD': ('food',),
}
CONTENT_TYPES = ('12', '14', '28', '38', '39')
CATALOG = {}
HUBS = {}
PROVINCE_DESTINATIONS = {'kr-seoul', 'kr-busan', 'kr-incheon', 'kr-jeju'}
HUB_INTERESTS = {
    '자연관광': ('nature',), '문화관광': ('culture',), '역사관광': ('culture', 'local_culture'),
    '체험관광': ('activity', 'local_culture'), '레저스포츠': ('activity',),
    '쇼핑': ('shopping',), '음식': ('food',), '음식점': ('food',),
}
PROVIDER_ERRORS = (OSError, HTTPException, ValueError, KeyError, TypeError, AttributeError)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Place:
    name: str
    area: str
    lat: float
    lon: float
    interests: tuple[str, ...]

    @property
    def label(self):
        return f'{self.area}/{self.name}' if self.area else self.name

    @property
    def search_name(self):
        return self.name.replace(' ', '')


def fetch_page(operation, *, service='KorService2', **params):
    query = urlencode(dict(MobileOS='WEB', MobileApp='Tripick', _type='json',
                           serviceKey=unquote(config.tour_api_key), **params))
    # urllib does not emit request URLs (including the query-string key) at INFO.
    try:
        with urlopen(f'{BASE_URL}/{service}/{operation}?{query}', timeout=5) as response:
            payload = json.load(response)['response']
    except HTTPError as exc:
        if exc.code in (401, 403, 429):
            raise PermissionError('TourAPI access or quota unavailable') from None
        raise
    code = str(payload['header']['resultCode'])
    if code == '03':
        return [], 0
    if code in ('20', '22', '30', '31', '32'):
        raise PermissionError('TourAPI access or quota unavailable')
    if code not in ('0000', '00'):
        raise ValueError('TourAPI request failed')
    body = payload['body']
    items = (body['items'] or {}).get('item', [])
    if not isinstance(items, list):
        raise ValueError('Invalid TourAPI items')
    return items, int(body['totalCount'])


def city_regions():
    """Discover city/district codes from the provider, including cities with multiple districts."""
    regions = {city: set() for city in DOMESTIC_CANDIDATES}
    page = 1
    received = 0
    while True:
        rows, total = fetch_page('ldongCode2', lDongListYn='Y', numOfRows=100, pageNo=page)
        for row in rows:
            if not isinstance(row, dict) or not row.get('lDongRegnCd'):
                continue
            province = str(row.get('lDongRegnNm') or '')
            district = str(row.get('lDongSignguNm') or '')
            for city, scopes in regions.items():
                label = DESTINATIONS[city]['label']
                if (province.startswith(label) or district.startswith(label + '시')) and row.get('lDongSignguCd'):
                    scopes.add((str(row['lDongRegnCd']), str(row['lDongSignguCd'])))
        received += len(rows)
        if not rows or received >= total:
            return regions
        page += 1


def parse_place(row):
    if not isinstance(row, dict):
        return None
    name = row.get('title')
    address = row.get('addr1')
    interests = INTERESTS_BY_CLASS.get(str(row.get('lclsSystm1')))
    if str(row.get('contenttypeid')) == '28':
        interests = ('activity',)
    elif row.get('lclsSystm2') == 'SH06':
        interests = ('shopping', 'local_culture')
    if not interests or not isinstance(name, str) or not 0 < len(name.strip()) <= 60:
        return None
    try:
        lat, lon = float(row['mapy']), float(row['mapx'])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    if not (32 <= lat <= 39 and 124 <= lon <= 132):
        return None
    parts = address.split() if isinstance(address, str) else []
    area = next((s for s in parts[1:4] if s.endswith(('읍', '면', '구', '동'))), '')
    return Place(' '.join(name.split()), area[:16], lat, lon, interests)


def fetch_city(city, scopes):
    places = {}
    for region, district in sorted(scopes):
        filters = {'lDongRegnCd': region}
        if district:
            filters['lDongSignguCd'] = district
        queries = [('areaBasedList2', {'contentTypeId': kind}) for kind in CONTENT_TYPES]
        queries.extend(('searchKeyword2', {'keyword': name}) for name in DOMESTIC_SURVEY_PLACES.get(city, ()))
        for operation, search in queries:
            rows, _ = fetch_page(operation, **filters, **search, arrange='C', pageNo=1, numOfRows=50)
            for row in rows:
                if not isinstance(row, dict) or any(str(row.get(k)) != v for k, v in filters.items()):
                    continue
                place = parse_place(row)
                if not place or not row.get('contentid'):
                    continue
                if 'keyword' in search and place.search_name != search['keyword']:
                    continue
                places[str(row['contentid'])] = place
    return tuple(places.values())


def fetch_hubs(scopes):
    # Centrality is ranked within each district. Use membership in its top 20, never a national rank.
    last_month = datetime.now(timezone(timedelta(hours=9))).date().replace(day=1) - timedelta(days=1)
    months = (last_month, last_month.replace(day=1) - timedelta(days=1))
    places = []
    for province, district in sorted(scopes):
        code = province + district
        for month in months:
            period = month.strftime('%Y%m')
            rows, _ = fetch_page('areaBasedList1', service='LocgoHubTarService1', areaCd=province,
                                 signguCd=code, baseYm=period, numOfRows=100, pageNo=1)
            if rows:
                break
        for row in rows:
            if not isinstance(row, dict) or str(row.get('signguCd')) != code or str(row.get('baseYm')) != period:
                continue
            tags = HUB_INTERESTS.get(str(row.get('hubCtgryMclsNm')))
            if not tags:
                continue
            try:
                rank = int(row['hubRank'])
                lat, lon = float(row['mapY']), float(row['mapX'])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            name = row.get('hubTatsNm')
            if not (1 <= rank <= 20 and 32 <= lat <= 39 and 124 <= lon <= 132 and isinstance(name, str)):
                continue
            name = ' '.join(name.replace('/', ' ').split())
            if 0 < len(name) <= 60:
                places.append(Place(name, str(row.get('signguNm') or '')[:16], lat, lon, tags))
    return tuple(places)


async def refresh_catalog():
    while True:
        delay = 86400
        try:
            regions = await asyncio.to_thread(city_regions)
            for city, scopes in regions.items():
                if not scopes:
                    continue
                try:
                    areas = {(r, '') for r, _ in scopes} if city in PROVINCE_DESTINATIONS else scopes
                    places = await asyncio.to_thread(fetch_city, city, areas)
                    if places:
                        CATALOG[city] = places
                except PROVIDER_ERRORS:
                    logger.warning('TourAPI refresh failed for %s', city)
            for city, scopes in regions.items():
                if scopes:
                    try:
                        HUBS[city] = await asyncio.to_thread(fetch_hubs, scopes)
                    except PermissionError:
                        logger.warning('TourAPI hub service access or quota unavailable')
                        break
                    except PROVIDER_ERRORS:
                        logger.warning('TourAPI hub lookup unavailable for %s', city)
        except PROVIDER_ERRORS:
            delay = 3600
            logger.warning('TourAPI region lookup failed')
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(refresh_catalog()) if config.tour_api_key else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def reference_hints(city, interests):
    fallback = domestic_hints(city, interests)
    hubs = set(HUBS.get(city, ()))
    pool = [p for p in (*HUBS.get(city, ()), *CATALOG.get(city, ())) if any(tag in interests for tag in p.interests)]
    if not pool:
        return fallback
    known = {entry.split('/', 1)[-1].replace(' ', ''): i for i, entry in enumerate(fallback)}
    surveyed = set(DOMESTIC_SURVEY_PLACES.get(city, ()))

    def evidence(place):
        return place.search_name not in surveyed, place not in hubs

    anchor = min(pool, key=lambda p: (*evidence(p), known.get(p.search_name, len(known))))

    def proximity(place):
        km = distance_km(anchor.lat, anchor.lon, place.lat, place.lon)
        return km > 3, evidence(place) if km <= 3 else (True, True), km

    pool.sort(key=proximity)
    selected = {}
    for tag in interests:
        match = next((p for p in pool if tag in p.interests), None)
        if match:
            selected[match.search_name] = match.label
        else:
            for hint in domestic_hints(city, [tag])[:1]:
                selected.setdefault(hint.split('/', 1)[-1].replace(' ', ''), hint)
    for p in pool:
        if len(selected) >= 6:
            break
        selected.setdefault(p.search_name, p.label)
    for hint in fallback:
        selected.setdefault(hint.split('/', 1)[-1].replace(' ', ''), hint)
    return list(selected.values())[:6]
