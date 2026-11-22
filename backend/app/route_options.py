"""Look up a single itinerary leg at its scheduled departure time."""
import asyncio
import math
import re
from datetime import datetime, timezone

import httpx


GOOGLE_MODES = {'walking': 'WALK', 'transit': 'TRANSIT', 'driving': 'DRIVE'}
ROUTES_URL = 'https://routes.googleapis.com/directions/v2:computeRoutes'


async def route_option(client: httpx.AsyncClient, api_key: str, mode: str, origin_id: str,
                       destination_id: str, departure: datetime, next_visit: datetime) -> dict:
    payload = {
        'origin': {'placeId': origin_id}, 'destination': {'placeId': destination_id},
        'travelMode': GOOGLE_MODES[mode],
    }
    if departure.utcoffset() is None or next_visit.utcoffset() is None:
        raise ValueError('route times must include an offset')
    if mode != 'walking':
        payload['departureTime'] = departure.astimezone(timezone.utc).isoformat()
    try:
        response = await client.post(ROUTES_URL, json=payload, timeout=10,
                                     headers={'X-Goog-Api-Key': api_key,
                                              'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters'})
        response.raise_for_status()
        routes = response.json().get('routes', [])
        if not isinstance(routes, list):
            raise ValueError('invalid routes')
        if not routes:
            return {'mode': mode, 'status': 'no_route'}
        route = routes[0]
        duration = route['duration']
        distance = route['distanceMeters']
        if not re.fullmatch(r'\d+(?:\.\d{1,9})?s', duration) or type(distance) is not int or distance < 0:
            raise ValueError('invalid route measurements')
        minutes = math.ceil(float(duration[:-1]) / 60)
        available = (next_visit.astimezone(timezone.utc) - departure.astimezone(timezone.utc)).total_seconds()
        return dict(mode=mode, status='verified' if minutes * 60 <= available else 'time_conflict',
                    durationMinutes=minutes, distanceMeters=distance, provider='google',
                    checkedAt=datetime.now(timezone.utc).isoformat())
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {'mode': mode, 'status': 'lookup_failed'}


async def route_choices(client, api_key, origin_id, destination_id, departure, next_visit):
    return await asyncio.gather(*(route_option(client, api_key, mode, origin_id, destination_id,
                                              departure, next_visit) for mode in GOOGLE_MODES))
