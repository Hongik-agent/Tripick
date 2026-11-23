import asyncio
import io
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import config, tour_api as tour
from app.itinerary_agent import candidate_task
from app.planning import Conditions


class TourApiTests(unittest.IsolatedAsyncioTestCase):
    def row(self, name, lon, category='NA', content_id='1', **overrides):
        return dict(title=name, contentid=content_id, addr1='부산광역시 수영구 광안해변로',
                    mapx=lon, mapy='35.153', lclsSystm1=category, lDongRegnCd='26') | overrides

    def test_request_contract_and_encoded_service_key(self):
        body = {'header': {'resultCode': '0000'}, 'body': {'items': '', 'totalCount': 0}}
        stream = io.BytesIO(json.dumps({'response': body}).encode())
        with patch.object(config, 'tour_api_key', 'test%2Bkey%2F%3D'), patch.object(tour, 'urlopen', return_value=stream) as get:
            self.assertEqual(tour.fetch_page('ldongCode2', lDongListYn='Y'), ([], 0))
        url = urlsplit(get.call_args.args[0])
        self.assertEqual(url.path, '/B551011/KorService2/ldongCode2')
        q = parse_qs(url.query)
        self.assertEqual((url.scheme, url.hostname, q['serviceKey'], q['_type']),
                         ('https', 'apis.data.go.kr', ['test+key/='], ['json']))

    def test_region_codes_follow_provider_pages_and_city_boundaries(self):
        def region(province, code, district, local):
            return dict(lDongRegnNm=province, lDongRegnCd=code, lDongSignguNm=district, lDongSignguCd=local)
        pages = [([region('제주특별자치도', '50', '서귀포시', '130'),
                   region('제주특별자치도', '50', '제주시', '110')], 4),
                 ([region('전북특별자치도', '52', '전주시 완산구', '111'),
                   region('전북특별자치도', '52', '전주시 덕진구', '113')], 4)]
        with patch.object(tour, 'fetch_page', side_effect=pages) as fetch:
            scopes = tour.city_regions()
        self.assertEqual(scopes['kr-jeju'], {('50', '130'), ('50', '110')})
        self.assertEqual(scopes['kr-jeonju'], {('52', '111'), ('52', '113')})
        self.assertEqual(fetch.call_args.kwargs['pageNo'], 2)

    def test_coordinate_order_categories_and_duplicates(self):
        records = [self.row('광안리해변', '129.118'), self.row('광안리해변', '129.118'),
                   self.row('잘못된 좌표', '35', mapy='129'), self.row('위치 없음', ''),
                   self.row('타 지역', '127', lDongSignguCd='150')]
        records = [dict(lDongSignguCd='265', **r) if 'lDongSignguCd' not in r else r for r in records]
        with patch.object(tour, 'fetch_page', return_value=(records, len(records))):
            places = tour.fetch_city('kr-busan', {('26', '265')})
        self.assertEqual(len(places), 1)
        self.assertEqual((places[0].lat, places[0].lon, places[0].interests), (35.153, 129.118, ('nature',)))

    def test_survey_place_is_searched_and_a_similarly_named_shop_is_not_promoted(self):
        def fetch(operation, **query):
            if operation == 'searchKeyword2' and query['keyword'] == '해운대해수욕장':
                return [self.row('해운대 해수욕장', '129.160'),
                        self.row('해운대해수욕장 기념품점', '129.161', 'SH', '2')], 2
            return [], 0
        with patch.object(tour, 'fetch_page', side_effect=fetch):
            found = tour.fetch_city('kr-busan', {('26', '')})
        self.assertEqual([p.name for p in found], ['해운대 해수욕장'])

    def test_hubs_use_recent_months_and_only_ranked_places_in_the_district(self):
        def fetch(operation, **q):
            self.assertEqual((q['service'], operation, q['signguCd']), ('LocgoHubTarService1', 'areaBasedList1', '26290'))
            if len(periods) == 0:
                periods.append(q['baseYm'])
                return [], 0
            self.assertLess(q['baseYm'], periods[0])
            base = dict(mapX=129.12, mapY=35.15, signguCd='26290', baseYm=q['baseYm'],
                        hubCtgryMclsNm='자연관광', signguNm='남구', hubRank='2', hubTatsNm='바다공원')
            return [base, dict(base, signguCd='99999'), dict(base, hubRank='27'), dict(base, baseYm='200101')], 4
        periods = []
        with patch.object(tour, 'fetch_page', side_effect=fetch):
            hubs = tour.fetch_hubs({('26', '290')})
        self.assertEqual([p.name for p in hubs], ['바다공원'])
        with (patch.dict(tour.HUBS, {'kr-busan': hubs}, clear=True),
              patch.dict(tour.CATALOG, {'kr-busan': (tour.parse_place(self.row('인근 공원', '129.121')),)}, clear=True)):
            self.assertEqual(tour.reference_hints('kr-busan', ['nature'])[0], '남구/바다공원')

    def test_prompt_uses_nearby_places_and_preserves_other_interests(self):
        records = [self.row('광안리해변', '129.118'), self.row('먼 식당', '129.40', 'FD'),
                   self.row('가까운 식당', '129.119', 'FD')]
        records.extend(self.row(f'공원{i}', 129.12 + i * .001) for i in range(8))
        conditions = Conditions(destinationId='kr-busan', startDate='2027-02-01', endDate='2027-02-07',
                                party={'typeId': 'family', 'sizeBand': '4'}, interestIds=['nature', 'food', 'culture'],
                                paceId='relaxed', transportMode='walking', mapProvider='google')
        with patch.dict(tour.CATALOG, {'kr-busan': tuple(map(tour.parse_place, records))}, clear=True):
            prompt = candidate_task(conditions)
            hints = tour.reference_hints('kr-busan', conditions.interestIds)
            self.assertEqual(len(hints), 6)
            self.assertEqual(prompt.count('광안리해변'), 1)
            self.assertIn('가까운 식당', prompt)
            self.assertIn('감천문화마을', prompt)
            self.assertNotIn('먼 식당', prompt)
            self.assertNotIn('129.118', prompt)
            self.assertNotIn('참고 예시', candidate_task(conditions.model_copy(update={'destinationId': 'jp-osaka'})))

    async def test_refresh_failure_preserves_existing_catalog(self):
        cached = (tour.parse_place(self.row('광안리해변', '129.118')),)
        async def run_sync(fn, *args):
            return fn(*args)
        with (patch.dict(tour.CATALOG, {'kr-busan': cached}, clear=True),
              patch.object(tour, 'city_regions', return_value={'kr-busan': {('26', '140')}}),
              patch.object(tour, 'fetch_city', side_effect=OSError('offline')),
              patch.object(tour, 'fetch_hubs', side_effect=OSError('offline')),
              patch.object(asyncio, 'to_thread', side_effect=run_sync),
              patch.object(asyncio, 'sleep', side_effect=asyncio.CancelledError),
              self.assertLogs(tour.logger, 'WARNING')):
            with self.assertRaises(asyncio.CancelledError):
                await tour.refresh_catalog()
            self.assertEqual(tour.CATALOG['kr-busan'], cached)

    async def test_rank_service_denial_still_publishes_new_tour_places(self):
        places = (tour.parse_place(self.row('부산 공원', '129.118')),)
        async def run_sync(fn, *args):
            return fn(*args)
        with (patch.dict(tour.CATALOG, clear=True),
              patch.object(tour, 'city_regions', return_value={'kr-busan': {('26', '350')}}),
              patch.object(tour, 'fetch_city', return_value=places) as fetch,
              patch.object(tour, 'fetch_hubs', side_effect=PermissionError),
              patch.object(asyncio, 'to_thread', side_effect=run_sync),
              patch.object(asyncio, 'sleep', side_effect=asyncio.CancelledError),
              self.assertLogs(tour.logger, 'WARNING')):
            with self.assertRaises(asyncio.CancelledError):
                await tour.refresh_catalog()
            fetch.assert_called_once_with('kr-busan', {('26', '')})
            self.assertIn('수영구/부산 공원', tour.reference_hints('kr-busan', ['nature']))

    async def test_unconfigured_key_does_not_start_refresh(self):
        with patch.object(config, 'tour_api_key', ''), patch.object(tour, 'refresh_catalog') as refresh:
            async with tour.lifespan(None):
                refresh.assert_not_called()
