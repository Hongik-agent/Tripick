import unittest

from pydantic import ValidationError

from app.domestic_candidates import domestic_hints
from app.itinerary_agent import candidate_task, instructions
from app.planning import Conditions, DESTINATIONS, INTERESTS, options


class PlanningOptionsTests(unittest.TestCase):
    def test_short_hints_cover_each_domestic_destination_and_interest(self):
        for dest in options()['destinations']:
            with self.subTest(destination=dest['id']):
                hints = domestic_hints(dest['id'], list(INTERESTS))
                if dest['countryCode'] != 'KR':
                    self.assertEqual(hints, [])
                    continue
                self.assertLessEqual(len(hints), 6)
                self.assertEqual(len(hints), len(set(hints)))
                for interest in INTERESTS:
                    self.assertTrue(domestic_hints(dest['id'], [interest]), interest)

    def test_hints_are_optional_and_sent_once_regardless_of_trip_length(self):
        conditions = Conditions(destinationId='kr-busan', startDate='2026-12-01', endDate='2026-12-07',
                                party={'typeId': 'family', 'sizeBand': '4'}, interestIds=['nature'],
                                paceId='relaxed', transportMode='walking', mapProvider='google')
        prompt = instructions(conditions) + candidate_task(conditions)
        self.assertEqual(prompt.count('광안리해변'), 1)
        for unrelated in ('감천문화마을', '서울숲'):
            self.assertNotIn(unrelated, prompt)
        self.assertIn('7일차', prompt)
        osaka = conditions.model_copy(update={'destinationId': 'jp-osaka'})
        abroad = instructions(osaka) + candidate_task(osaka)
        self.assertNotIn('참고 예시', abroad)
        self.assertIn('광안리', prompt)
        self.assertNotIn('광안리', abroad)
        self.assertIn('검색순위·방문량은 추정하지 않는다', abroad)

    def test_korea_first_and_removed_destinations_rejected(self):
        removed = {'id-bali', 'id-jakarta', 'id-yogyakarta', 'gb-edinburgh',
                   'es-seville', 'fr-lyon', 'tw-taichung'}
        destinations = options()['destinations']
        self.assertEqual(len(destinations), 42)
        self.assertEqual([d['countryCode'] for d in destinations[:9]], ['KR'] * 9)
        self.assertFalse(removed & {d['id'] for d in destinations})
        self.assertNotIn('ID', {d['countryCode'] for d in destinations})
        body = dict(startDate='2026-12-01', endDate='2026-12-01',
                    party=dict(typeId='solo', sizeBand='1'), interestIds=['food'],
                    paceId='relaxed', transportMode='walking', mapProvider='google')
        Conditions(destinationId='kr-seoul', **body)
        for destination_id in removed:
            with self.subTest(destination_id=destination_id):
                with self.assertRaises(ValidationError):
                    Conditions(destinationId=destination_id, **body)
                self.assertIn('mapCenter', DESTINATIONS[destination_id])
