import unittest

from pydantic import ValidationError

from app.planning import Conditions, DESTINATIONS, options


class PlanningOptionsTests(unittest.TestCase):
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
