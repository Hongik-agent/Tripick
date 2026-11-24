import asyncio
import base64
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlsplit, parse_qs

from cryptography.fernet import Fernet

# 운영 .env를 사용하지 않는 전용 로컬 테스트 DB. 실행 전 Alembic upgrade가 필요하다.
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres@127.0.0.1:55440/tripick_test'
os.environ['SUPABASE_URL'] = 'https://example.supabase.co'
os.environ['SUPABASE_PUBLISHABLE_KEY'] = 'test-key'
os.environ['FRONTEND_ORIGIN'] = 'https://frontend.example'
os.environ['SESSION_ENCRYPTION_KEY'] = Fernet.generate_key().decode()

import httpx
from sqlalchemy import insert, delete, select, update, func, event
from app import auth, domain, config
from app.main import app
from app.models import users, trips, auth_sessions, posts, post_hearts, oauth_transactions
from app.db import engine


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.uid, self.other = uuid4(), uuid4()
        self.sid, self.csrf = uuid4().hex, uuid4().hex
        stamp = auth.now()
        async with engine.begin() as conn:
            await conn.execute(insert(users), [dict(id=self.uid, nickname='User'+self.uid.hex[:12]), dict(id=self.other, nickname='User'+self.other.hex[:12])])
            await conn.execute(insert(auth_sessions).values(hash=auth.digest(self.sid), user_id=self.uid, csrf=self.csrf,
                tokens=auth.encrypt(dict(access_token='access', refresh_token='refresh')), created_at=stamp,
                last_seen=stamp, checked_at=stamp, expires_at=stamp+timedelta(days=7), token_expires_at=stamp+timedelta(hours=1)))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.frontend_origin,
            headers={'Origin': config.frontend_origin, 'X-CSRF-Token': self.csrf}, cookies={config.session_cookie: self.sid})
        async def loader():
            async def load(conn, uid, body):
                return self.draft(uid, body)
            return load
        app.dependency_overrides[domain.verified_drafts] = loader

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.client.aclose()
        async with engine.begin() as conn:
            await conn.execute(delete(users).where(users.c.id.in_([self.uid, self.other])))
            await conn.execute(delete(oauth_transactions))
        await engine.dispose()

    def conditions(self):
        return dict(optionsVersion='v1', destinationId='jp-tokyo', startDate='2026-12-01', endDate='2026-12-01',
            party=dict(typeId='friends', sizeBand='2'), interestIds=['food'],
            paceId='relaxed', transportMode='walking', mapProvider='google')

    async def test_generation_limit_matches_admission_and_resets_at_korean_midnight(self):
        model = 'gpt-6-luna'
        path = '/api/generation-limit?modelId=' + model
        # 한국 시간 12월 31일 오후 11시, 다음 달 경계도 함께 확인한다.
        stamp = datetime(2026, 12, 31, 14, tzinfo=timezone.utc)

        async def seed(count, created_at, uid):
            async with engine.begin() as conn:
                await conn.execute(insert(domain.jobs), [
                    dict(id=uuid4().hex, user_id=uid, fingerprint=uuid4().hex,
                         created_at=created_at, expires_at=created_at+timedelta(hours=1),
                         status='failed', cost_krw=0) for _ in range(count)])

        with (patch.object(domain, 'now', return_value=stamp) as clock,
              patch.object(config, 'openai_key', 'test'), patch.object(config, 'maps_key', 'test')):
            await seed(5, stamp, self.other)
            await seed(4, stamp, self.uid)
            self.assertEqual((await self.client.get(path)).json(), {'limit': None})
            await seed(1, stamp, self.uid)
            reset = '2027-01-01T00:00:00+09:00'
            self.assertEqual((await self.client.get(path)).json()['limit'],
                             dict(code='DAILY_LIMIT_REACHED', resetsAt=reset))
            await seed(15, stamp-timedelta(days=1), self.uid)
            limit = (await self.client.get(path)).json()['limit']
            self.assertEqual(limit, dict(code='MONTHLY_LIMIT_REACHED', resetsAt=reset))
            rejected = await self.client.post('/api/generations', json=self.conditions(),
                                              headers={'Idempotency-Key': uuid4().hex})
            self.assertEqual(rejected.status_code, 429)
            self.assertEqual({k: rejected.json()['error'][k] for k in limit}, limit)
            clock.return_value = stamp+timedelta(hours=1)
            self.assertEqual((await self.client.get(path)).json(), {'limit': None})
            with patch.object(config, 'generation_budget_krw', domain.reservation_cost(model)):
                self.assertIsNone((await self.client.get(path)).json()['limit'])
                premium = await self.client.get('/api/generation-limit?modelId=gpt-6.1-terra')
                self.assertEqual(premium.json()['limit'], dict(code='BUDGET_EXHAUSTED', resetsAt=None))

    async def test_postgres_batches_leg_times_across_a_dst_transition(self):
        from app.generation import day_leg_times
        items = [{'endTime': '00:30'}, {'startTime': '01:30', 'endTime': '01:45'}, {'startTime': '02:15'}]
        statements = []
        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(engine.sync_engine, 'before_cursor_execute', record)
        try:
            self.assertEqual(await day_leg_times('America/New_York', '2027-11-07', items, []), {})
            result = await day_leg_times('America/New_York', '2027-11-07', items, [0, 1])
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', record)
        self.assertEqual(len(statements), 1)
        def utc(hour, minute):
            return datetime(2027, 11, 7, hour, minute, tzinfo=timezone.utc)
        self.assertEqual(result, {0: (utc(4, 30), utc(6, 30)), 1: (utc(6, 45), utc(7, 15))})

    async def test_seven_day_schedule_batches_timezone_queries(self):
        from app import generation
        from app.planning import Conditions

        conditions = Conditions(**{**self.conditions(), 'destinationId': 'kr-incheon',
                                   'startDate': '2027-01-11', 'endDate': '2027-01-17', 'paceId': 'packed'})

        async def ask(task, schema):
            return schema(**{f'day_{i+1}': [
                dict(name=f'{i}-{j}', nearbyAlternative=f'대안{i}-{j}', stayMinutes=30)
                for j in range(len(generation.day_slots(conditions, i)))] for i in range(7)})

        def search(name, city):
            return dict(id=name, types=['restaurant'], location=dict(latitude=37.4, longitude=126.7))

        statements = []
        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, 'before_cursor_execute', record)
        try:
            with (patch.object(generation.GooglePlaces, 'search', side_effect=search),
                  patch.object(generation.GooglePlaces, 'display', side_effect=lambda pid: dict(name=pid)),
                  patch.object(generation, 'route_option', return_value=dict(
                      mode='walking', status='verified', durationMinutes=5, distanceMeters=300))):
                content = await generation.build(conditions, ask, None, lambda *args, **kwargs: None)
                self.assertEqual(sum(len(d['items']) for d in content['days']), 47)
                self.assertEqual(sum(len(d['legs']) for d in content['days']), 40)
                self.assertEqual(len(statements), 8)  # Calendar once, then all leg times once per day.
                statements.clear()
                await generation.display_day(content, 1)
                self.assertEqual(len(statements), 1)
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', record)

    async def test_generate_verify_open_and_save(self):
        from app import generation

        app.dependency_overrides.pop(domain.verified_drafts)
        inputs = dict(self.conditions(), modelId='gpt-6.1-terra', destinationId='kr-jeju')
        usage = SimpleNamespace(input_tokens=50, output_tokens=100, total_tokens=150)
        async def model_response(conditions, task, api_key, output_type):
            plan = output_type(day_1=[
                dict(name=f'장소{i}', nearbyAlternative=f'대안{i}', stayMinutes=45) for i in range(4)])
            return SimpleNamespace(final_output=plan, context_wrapper=SimpleNamespace(usage=usage))
        in_progress = []

        async def search(name, _):
            if name == '장소0':
                async with engine.connect() as conn:
                    job = await conn.scalar(select(generation.jobs.c.id).where(generation.jobs.c.user_id == self.uid))
                in_progress.append((await self.client.get('/api/generations/' + job)).json())
                return {'id': name, 'types': ['park'], 'location': {'latitude': 33.5, 'longitude': 126.52}}
            return {'id': name, 'types':['restaurant'], 'location': {'latitude': 33.5, 'longitude': 126.53},
                    'regularOpeningHours': {'periods': [{'open': {'day': 0, 'hour': 0}}]}}

        async def display(place_id):
            return dict(providerPlaceId=place_id, name=place_id, latitude=33.5, longitude=126.53)

        def route(client, key, mode, left, right, *times):
            if left == '장소0' and mode == 'walking':
                return dict(mode=mode, status='no_route')
            return dict(mode=mode, status='verified', durationMinutes=5, distanceMeters=300)

        with (patch.object(config, 'openai_key', 'test'), patch.object(config, 'maps_key', 'test'),
              patch.object(generation, 'run_planner', side_effect=model_response) as planner,
              patch.object(generation.GooglePlaces, 'search', side_effect=search),
              patch.object(generation.GooglePlaces, 'display', side_effect=display),
              patch.object(generation, 'route_option', side_effect=route),
              patch.object(domain, 'route_option', side_effect=route)):
            headers = {'Idempotency-Key': uuid4().hex}
            accepted = await self.client.post('/api/generations', json=inputs, headers=headers)
            self.assertEqual(accepted.status_code, 202, accepted.text)
            with patch.object(config, 'generation_budget_krw', 1):
                recovered = await self.client.get('/api/generation-requests/' + headers['Idempotency-Key'])
                self.assertEqual(recovered.json(), accepted.json())
                missing = await self.client.get('/api/generation-requests/' + uuid4().hex)
                self.assertEqual(missing.json()['error']['code'], 'GENERATION_REQUEST_NOT_FOUND')
            job = accepted.json()['generationId']
            status = (await self.client.get('/api/generations/' + job)).json()
            self.assertEqual(status['status'], 'completed', status)
            self.assertEqual(status['progress'], {'stage': 'completed', 'percent': 100})
            self.assertNotIn(job, generation.active_progress)
            self.assertEqual(in_progress[0]['status'], 'running')
            self.assertEqual(in_progress[0]['progress'], {'stage': 'checking', 'percent': 33, 'day': 1})
            draft = (await self.client.get('/api/drafts/' + status['draftId'])).json()
            self.assertEqual(len(draft['days'][0]['items']), 4)
            self.assertEqual(draft['days'][0]['items'][0]['hoursBasis'], 'unknown')
            self.assertEqual(draft['days'][0]['legs'][0]['status'], 'unverified')
            self.assertNotIn('durationMinutes', draft['days'][0]['legs'][0])
            self.assertEqual(draft['days'][0]['legs'][1]['durationMinutes'], 5)
            await self.client.post('/api/generations', json=inputs, headers=headers)
            self.assertEqual(planner.await_count, 1)
            self.assertTrue(all(call.args[0].modelId == inputs['modelId'] for call in planner.await_args_list))
            saved = await self.client.post('/api/trips', headers={'Idempotency-Key': uuid4().hex},
                                           json={'draftId': draft['id'], 'draftVersion': draft['version']})
            self.assertEqual(saved.status_code, 201, saved.text)
            path = '/api/trips/' + saved.json()['id']
            reopened = (await self.client.get(path)).json()
            self.assertEqual(reopened['days'][0]['legs'][0]['status'], 'unverified')
            publication = (await self.client.post(path + '/publication')).json()
            public = (await self.client.get('/api/posts/' + publication['postId'])).json()
            self.assertTrue(public['places'][0]['outgoingRouteUnverified'])
            changed = await self.client.put(path + '/days/1/legs/1', json={'mode': 'driving'},
                                            headers={'If-Match': str(reopened['version'])})
            self.assertEqual(changed.status_code, 200, changed.text)
            reopened = (await self.client.get(path)).json()
            self.assertEqual(reopened['days'][0]['legs'][0]['status'], 'verified')

    def draft(self, uid, body):
        return dict(ownerId=str(uid), version=1, status='success', expiresAt=auth.now()+timedelta(hours=1),
            sourceTripId=getattr(self, 'source', None), baseTripVersion=body.baseTripVersion,
            content=dict(destination=dict(id='jp-tokyo'), conditions=self.conditions(), mapProvider='google', transportMode='walking',
                days=[dict(day=1, date='2026-12-01', items=[dict(id='item_1', order=1, startTime='10:00', endTime='11:00', reason='test',
                    place=dict(id='place1', provider='google', providerPlaceId='test-place', name='검증 장소', address='test', latitude=35.0, longitude=139.0, checkedAt='2026-11-15T00:00:00Z'))], legs=[])], warnings=[], unmetConstraints=[]))

    async def create(self, draft=None, key=None):
        return await self.client.post('/api/trips', json=dict(draftId=draft or 'draft_'+uuid4().hex, draftVersion=1), headers={'Idempotency-Key': key or uuid4().hex})

    async def test_csrf_and_foreign_origin_rejected(self):
        for headers in ({'X-CSRF-Token': 'wrong'}, {'Origin': 'https://evil.example'}):
            r = await self.client.put('/api/users/me/nickname', json={'nickname':'ValidName'}, headers=headers)
            self.assertEqual(r.status_code, 403, r.text)

    async def test_cors(self):
        for origin, status in ((config.frontend_origin, 200), ('https://evil.example', 400)):
            r = await self.client.options('/api/trips', headers={'Origin':origin, 'Access-Control-Request-Method':'PUT', 'Access-Control-Request-Headers':'content-type,x-csrf-token,idempotency-key,if-match'})
            self.assertEqual(r.status_code, status)
        r = await self.client.options('/api/trips', headers={'Access-Control-Request-Method':'PATCH'})
        self.assertEqual(r.status_code, 400)

    async def test_auth_no_provider_call_within_interval(self):
        with patch.object(auth, 'provider_request') as call:
            for _ in range(2):
                r = await self.client.get('/api/auth/me')
                self.assertEqual(r.status_code, 200, r.text)
            call.assert_not_called()
        self.assertEqual(r.json()['csrfToken'], self.csrf)
        self.assertIn('no-store', r.headers['cache-control'])
        self.assertNotIn('access', r.text)

    async def test_expired_session_revoked_and_cookie_cleared(self):
        async with engine.begin() as conn:
            await conn.execute(update(auth_sessions).where(auth_sessions.c.user_id == self.uid).values(last_seen=auth.now()-timedelta(days=2)))
        r = await self.client.get('/api/auth/me')
        self.assertEqual(r.status_code, 401)
        self.assertIn('Max-Age=0', r.headers['set-cookie'])
        async with engine.connect() as conn:
            self.assertEqual(await conn.scalar(select(func.count()).select_from(auth_sessions).where(auth_sessions.c.user_id == self.uid)), 0)

    async def test_concurrent_refresh_only_once(self):
        async with engine.begin() as conn:
            await conn.execute(update(auth_sessions).where(auth_sessions.c.user_id == self.uid).values(token_expires_at=auth.now()))
        identity = dict(id=str(self.uid), email=None, app_metadata={'providers':['google']})
        def provider(path, token=None, body=None):
            if path.startswith('token'):
                return dict(access_token='renewed', refresh_token='new-refresh', expires_in=3600, user=identity)
            return identity
        with patch.object(auth, 'provider_request', side_effect=provider) as call:
            result = await asyncio.gather(*[self.client.get('/api/auth/me') for _ in range(3)])
            self.assertTrue(all(r.status_code == 200 for r in result))
            self.assertEqual(sum(c.args[0].startswith('token') for c in call.call_args_list), 1)

    async def begin_login(self, return_to='saved'):
        r = await self.client.post('/api/auth/login/google', json={'returnTo': return_to})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('HttpOnly', r.headers['set-cookie'])
        params = parse_qs(urlsplit(r.json()['url']).query)
        self.assertNotIn('state', params)  # Supabase 자체 state와 분리한다.
        callback = urlsplit(params['redirect_to'][0])
        self.assertEqual(callback.scheme+'://'+callback.netloc+callback.path, config.oauth_callback_url)
        return parse_qs(callback.query)['state'][0], params

    def provider(self, path, token=None, body=None):
        if path == 'user':
            return dict(id=str(self.uid), email=None, app_metadata={'providers':['google']})
        return dict(access_token='new-access', refresh_token='new-refresh', expires_in=3600)

    async def test_bff_code_exchange_and_single_use(self):
        state, params = await self.begin_login()
        async with engine.connect() as conn:
            txn = (await conn.execute(select(oauth_transactions).where(oauth_transactions.c.state_hash == auth.digest(state)))).mappings().one()
        verifier = auth.decrypt(txn['verifier'])['verifier']
        self.assertNotIn(verifier, txn['verifier'])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(params['code_challenge'], [challenge])
        with patch.object(auth, 'provider_request', side_effect=self.provider) as call:
            r = await self.client.get('/api/auth/callback', params={'state':state, 'code':'one-use-code'})
            self.assertEqual(r.status_code, 303)
            self.assertEqual(r.headers['location'], config.frontend_origin+'/?view=saved')
            self.assertIn('HttpOnly', r.headers['set-cookie'])
            self.assertIn('Secure', r.headers['set-cookie'])
            self.assertIn('SameSite=lax', r.headers['set-cookie'])
            self.assertNotIn('new-access', str(r.headers)+r.text)
            call.assert_any_call('token?grant_type=pkce', None, {'auth_code':'one-use-code', 'code_verifier':verifier})
            self.assertEqual(call.call_count, 2)
            again = await self.client.get('/api/auth/callback', params={'state':state, 'code':'one-use-code'})
            self.assertIn('authError', again.headers['location'])
            self.assertEqual(call.call_count, 2)
        async with engine.connect() as conn:
            rows = (await conn.execute(select(auth_sessions).where(auth_sessions.c.user_id == self.uid))).mappings().all()
            txn = (await conn.execute(select(oauth_transactions).where(oauth_transactions.c.state_hash == auth.digest(state)))).mappings().one()
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]['hash'], auth.digest(self.sid))
        self.assertNotIn('new-access', rows[0]['tokens'])
        self.assertEqual(auth.decrypt(rows[0]['tokens'])['access_token'], 'new-access')
        self.assertIsNone(txn['verifier'])
        self.assertIsNotNone(txn['consumed_at'])

    async def test_oauth_boundaries_and_expiry(self):
        self.assertEqual((await self.client.post('/api/auth/login/google', json={'returnTo':'https://evil.example'})).status_code, 422)
        self.assertEqual((await self.client.post('/api/auth/login/google', json={}, headers={'Origin':'https://evil.example'})).status_code, 403)
        self.assertEqual((await self.client.post('/api/auth/login/github', json={})).status_code, 403)
        self.assertEqual((await self.client.post('/api/auth/session', json={'accessToken':'old'})).status_code, 404)
        state, _ = await self.begin_login()
        with patch.object(auth, 'provider_request') as call:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.frontend_origin) as outsider:
                r = await outsider.get('/api/auth/callback', params={'state':state,'code':'stolen'})
                self.assertIn('authError', r.headers['location'])
            async with engine.begin() as conn:
                await conn.execute(update(oauth_transactions).where(oauth_transactions.c.state_hash == auth.digest(state)).values(expires_at=auth.now()-timedelta(seconds=1)))
            r = await self.client.get('/api/auth/callback', params={'state':state,'code':'expired'})
            self.assertIn('authError', r.headers['location'])
            self.assertNotIn('set-cookie', r.headers)
            call.assert_not_called()

    async def test_concurrent_callback_exchanges_once(self):
        state, _ = await self.begin_login()
        with patch.object(auth, 'provider_request', side_effect=self.provider) as call:
            results = await asyncio.gather(*[self.client.get('/api/auth/callback', params={'state':state,'code':'same'}) for _ in range(2)])
            self.assertEqual(sum('view=saved' in r.headers['location'] for r in results), 1)
            self.assertEqual(sum(c.args[0].startswith('token') for c in call.call_args_list), 1)

    async def test_cancelled_oauth_preserves_session(self):
        state, _ = await self.begin_login()
        with patch.object(auth, 'provider_request') as call:
            r = await self.client.get('/api/auth/callback', params={'state':state,'error':'access_denied'})
            self.assertIn('authError', r.headers['location'])
            self.assertNotIn('set-cookie', r.headers)
            again = await self.client.get('/api/auth/callback', params={'state':state,'code':'late'})
            self.assertIn('authError', again.headers['location'])
            self.assertEqual((await self.client.get('/api/auth/me')).status_code, 200)
            call.assert_not_called()

    async def test_login_limits(self):
        async with engine.begin() as conn:
            await conn.execute(update(users).where(users.c.id == self.uid).values(session_window_start=auth.now(), session_issue_count=config.login_limit))
        state, _ = await self.begin_login()
        with patch.object(auth, 'provider_request', side_effect=self.provider):
            r = await self.client.get('/api/auth/callback', params={'state':state, 'code':'over-limit'})
        self.assertIn('authError', r.headers['location'])
        self.assertNotIn('set-cookie', r.headers)
        self.assertEqual((await self.client.get('/api/auth/me')).status_code, 200)
        for _ in range(config.login_limit-1):
            await self.begin_login()
        r = await self.client.post('/api/auth/login/google', json={})
        self.assertEqual(r.status_code, 429)

    async def test_limit_and_idempotent_retry(self):
        draft, key = 'draft_'+uuid4().hex, uuid4().hex
        first = await self.create(draft, key)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual((await self.create(draft, key)).json(), first.json())
        self.assertEqual((await self.create(draft)).status_code, 409)
        self.assertEqual((await self.create()).status_code, 201)
        results = await asyncio.gather(self.create(), self.create())
        self.assertEqual(sorted(r.status_code for r in results), [201, 409])
        self.assertEqual((await self.client.get('/api/trips')).json()['capacity']['savedCount'], 3)
        self.assertEqual((await self.client.post('/api/generations', json=self.conditions())).json()['error']['code'], 'SAVED_TRIP_LIMIT_EXCEEDED')

    async def test_owner_version_and_invalid_draft_preserve_original(self):
        trip_id = (await self.create()).json()['id']
        async with engine.begin() as conn:
            await conn.execute(update(trips).where(trips.c.id == trip_id).values(owner_id=self.other))
        self.assertEqual((await self.client.get('/api/trips/'+trip_id)).status_code, 404)
        async with engine.begin() as conn:
            await conn.execute(update(trips).where(trips.c.id == trip_id).values(owner_id=self.uid))
        self.assertEqual((await self.client.delete('/api/trips/'+trip_id, headers={'If-Match':'2'})).status_code, 409)
        r = await self.client.put('/api/trips/'+trip_id, json=dict(draftId='new', draftVersion=1, baseTripVersion=1), headers={'Idempotency-Key':uuid4().hex,'If-Match':'1'})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual((await self.client.get('/api/trips/'+trip_id)).json()['version'], 1)
        self.source = trip_id
        r = await self.client.put('/api/trips/'+trip_id, json=dict(draftId='new', draftVersion=1, baseTripVersion=1), headers={'Idempotency-Key':uuid4().hex,'If-Match':'1'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['version'], 2)

    async def test_public_copy_hearts_and_cascade(self):
        trip_id = (await self.create()).json()['id']
        post_id = (await self.client.post('/api/trips/'+trip_id+'/publication')).json()['postId']
        self.assertEqual((await self.client.post('/api/trips/'+trip_id+'/publication')).status_code, 409)
        for _ in range(2):
            self.assertEqual((await self.client.put('/api/posts/'+post_id+'/heart')).json()['heartCount'], 1)
        r = await self.client.get('/api/posts/'+post_id)
        self.assertEqual(r.json()['places'][0]['visitTime'], '10:00')
        self.assertEqual(r.json()['places'][0]['googlePlaceId'], 'test-place')
        self.assertNotIn('latitude', r.json()['places'][0])
        for forbidden in ('startDate', 'email', str(self.uid), 'providerPlaceId', '2026-12-01'):
            self.assertNotIn(forbidden, r.text)
        name = 'Name'+uuid4().hex[:8]
        await self.client.put('/api/users/me/nickname', json={'nickname':name})
        self.assertEqual((await self.client.get('/api/posts/'+post_id)).json()['authorNickname'], name)
        r = await self.client.delete('/api/trips/'+trip_id, headers={'If-Match':'1'})
        self.assertEqual(r.status_code, 204, r.text)
        self.assertEqual((await self.client.get('/api/posts/'+post_id)).status_code, 404)
        async with engine.connect() as conn:
            self.assertEqual(await conn.scalar(select(func.count()).select_from(post_hearts).where(post_hearts.c.post_id == post_id)), 0)

    async def test_public_map_shares_repeated_place_lookup_and_skips_missing_ids(self):
        trip_id = (await self.create()).json()['id']
        post_id = (await self.client.post('/api/trips/'+trip_id+'/publication')).json()['postId']
        url = '/api/posts/'+post_id+'/map?day=1'
        async with engine.begin() as conn:
            content = await conn.scalar(select(posts.c.content).where(posts.c.id == post_id))
            first = content['places'][0]
            content['places'].extend([dict(mapPlaceId='unknown', order=2, day=1, name='미확인'),
                                      dict(first, mapPlaceId='again', order=3)])
            await conn.execute(update(posts).where(posts.c.id == post_id).values(content=content))
        with patch.object(config, 'maps_key', 'test'), patch.object(domain.GooglePlaces, 'request',
                    return_value={'location': {'latitude': 35, 'longitude': 139}}) as lookup:
            self.assertFalse((await self.client.get(url.replace('day=1', 'day=2'))).json()['available'])
            lookup.assert_not_called()
            result = (await self.client.get(url)).json()
            self.assertEqual([p['order'] for p in result['items']], [1, 3])
            lookup.assert_awaited_once_with('GET', 'places/test-place', 'location,attributions')

    async def test_nickname_whitespace_and_case_sensitive(self):
        for name in [' a', 'ab ', 'a b', 'a\tb', 'a\nb', 'a']:
            self.assertEqual((await self.client.put('/api/users/me/nickname', json={'nickname':name})).status_code, 422)
        name = 'Case'+uuid4().hex[:8]
        async with engine.begin() as conn:
            await conn.execute(update(users).where(users.c.id == self.other).values(nickname=name.lower()))
        self.assertEqual((await self.client.put('/api/users/me/nickname', json={'nickname':name})).status_code, 200)
        self.assertEqual((await self.client.put('/api/users/me/nickname', json={'nickname':name.lower()})).status_code, 409)

    async def test_default_loader_blocks_unverified_operating_data(self):
        app.dependency_overrides.clear()
        self.assertEqual((await self.create()).json()['error']['code'], 'INVALID_DRAFT')

    async def test_invalid_conditions_and_content(self):
        conditions = self.conditions()
        for change in ({'endDate':'2026-12-08'}, {'mapProvider':'naver'}, {'transportMode':'flying'}, {'party':dict(typeId='solo',sizeBand='5_plus')}):
            r = await self.client.post('/api/generations', json={**conditions, **change})
            self.assertEqual(r.status_code, 422, r.text)
        body = domain.Save(draftId='draft',draftVersion=1)
        for mutation in ('destination', 'date', 'coordinates', 'conditions', 'expiry', 'endTime', 'checkedAt'):
            draft = self.draft(self.uid, body)
            if mutation == 'destination': draft['content']['destination']['id'] = 'jp-osaka'
            if mutation == 'date': draft['content']['days'][0]['date'] = '1999-01-01'
            if mutation == 'coordinates': draft['content']['days'][0]['items'][0]['place']['latitude'] = 999
            if mutation == 'expiry': draft['expiresAt'] = None
            if mutation == 'endTime': draft['content']['days'][0]['items'][0]['endTime'] = '12:xx'
            if mutation == 'checkedAt': draft['content']['days'][0]['items'][0]['place']['checkedAt'] = 'not-a-time'
            if mutation == 'conditions': draft['content']['conditions']['party']['sizeBand'] = '6'
            with self.assertRaises(Exception) as error:
                domain.validate_draft(draft, self.uid, body)
            self.assertEqual(error.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
