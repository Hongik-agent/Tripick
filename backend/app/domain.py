import hashlib
import json
import re
import math
import asyncio
from datetime import timedelta, datetime, time, timezone
from uuid import uuid4
from urllib.parse import quote
from typing import Literal
from copy import deepcopy

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
import httpx
import logging
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError
from sqlalchemy import select, insert, update, delete, func, literal, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from .auth import authenticate, now
from .config import idempotency_ttl_seconds
from .db import engine
from .errors import fail
from .models import users, trips, posts, post_hearts as hearts, idempotency_keys as keys
from .planning import Conditions, GenerationModel, options, DESTINATIONS, INTERESTS
from . import config, generation
from .models import generation_jobs as jobs, generation_requests as counters
from .place_data import GooglePlaces, PlanningFailure
from .route_options import GOOGLE_MODES, route_choices, route_option

router = APIRouter(prefix='/api')


async def verified_drafts():
    async def load(conn, uid, body):
        row = (await conn.execute(select(jobs).where(jobs.c.id == body.draftId, jobs.c.user_id == uid,
            jobs.c.status == 'completed', jobs.c.expires_at > now()).with_for_update())).mappings().first()
        if not row:
            fail(409, 'INVALID_DRAFT', '검증된 생성 결과가 필요합니다.')
        conditions = row['content']['conditions']
        return dict(ownerId=str(uid), version=row['version'], status='success', expiresAt=row['expires_at'],
                    sourceTripId=conditions.get('sourceTripId'), baseTripVersion=conditions.get('baseTripVersion'),
                    content=row['content'])
    return load


class Save(BaseModel):
    model_config = ConfigDict(extra='forbid')
    draftId: str | None = Field(default=None, max_length=100)
    draftVersion: int | None = Field(default=None, ge=1)
    editDraftId: str | None = Field(default=None, max_length=100)
    editVersion: int | None = Field(default=None, ge=1)
    baseTripVersion: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def valid(self):
        if bool(self.draftId) == bool(self.editDraftId):
            raise ValueError('생성 초안과 편집 작업본 중 하나가 필요합니다.')
        if self.draftId and (self.draftVersion is None or self.editVersion is not None):
            raise ValueError('초안 버전을 확인해 주세요.')
        if self.editDraftId and (self.editVersion is None or self.draftVersion is not None or self.baseTripVersion is None):
            raise ValueError('편집 버전을 확인해 주세요.')
        return self


class Nickname(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nickname: str


def capacity(count):
    return dict(limit=3, savedCount=count, remainingSlots=max(0, 3-count))


async def lock_user(conn, uid):
    await conn.execute(select(users.c.id).where(users.c.id == uid).with_for_update())


async def owned(conn, uid, trip_id):
    row = (await conn.execute(select(trips).where(trips.c.id == trip_id, trips.c.owner_id == uid).with_for_update())).mappings().first()
    if row is None:
        fail(404, 'RESOURCE_NOT_FOUND', '일정을 찾을 수 없습니다.')
    return row


def match_version(request, version):
    if request.headers.get('if-match') != str(version):
        fail(409, 'VERSION_CONFLICT', '최신 일정을 확인한 뒤 다시 시도해 주세요.')


async def count_trips(conn, uid):
    return await conn.scalar(select(func.count()).select_from(trips).where(trips.c.owner_id == uid))


async def replay(conn, request, uid, body):
    key = request.headers.get('idempotency-key', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', key):
        fail(422, 'INVALID_SELECTION', '유효한 Idempotency-Key가 필요합니다.')
    scope = request.method + ':' + request.url.path
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    await conn.execute(delete(keys).where(keys.c.user_id == uid, keys.c.expires_at < now()))
    row = (await conn.execute(select(keys).where(keys.c.user_id == uid, keys.c.scope == scope, keys.c.key == key))).mappings().first()
    if row and row['body_hash'] != fingerprint:
        fail(409, 'IDEMPOTENCY_CONFLICT', '같은 키로 다른 요청을 보낼 수 없습니다.')
    return row['response'] if row else None, dict(user_id=uid, scope=scope, key=key, body_hash=fingerprint)


async def remember(conn, values, response):
    await conn.execute(insert(keys).values(**values, response=response, expires_at=now()+timedelta(seconds=idempotency_ttl_seconds)))


def require(condition):
    if not condition:
        raise ValueError('invalid draft content')


def validate_draft(draft, uid, body, trip_id=None):
    try:
        version = body.draftVersion if body.draftId else body.editVersion
        require(str(draft.get('ownerId')) == str(uid) and draft.get('version') == version)
        require(draft.get('status') == ('success' if body.draftId else 'valid'))
        require(draft['expiresAt'].utcoffset() is not None and draft['expiresAt'] > now())
        require(draft.get('sourceTripId') == trip_id and draft.get('baseTripVersion') == body.baseTripVersion)
        content = draft['content']
        conditions = Conditions.model_validate(content['conditions'])
        days = content['days']
        require(content['destination']['id'] == conditions.destinationId)
        require(content['mapProvider'] == 'google' and content['transportMode'] == conditions.transportMode)
        require(len(days) == (conditions.endDate-conditions.startDate).days+1)
        require(not content.get('unmetConstraints'))
        compact = content.get('storage') == 'place_ids'
        seen = set()
        for index, day in enumerate(days):
            require(day['day'] == index+1 and day['date'] == (conditions.startDate+timedelta(days=index)).isoformat())
            items, legs = day['items'], day['legs']
            free_slots = day.get('freeSlots', [])
            require(isinstance(free_slots, list) and len(free_slots) <= 7 and
                    all(slot in ('breakfast', 'lunch', 'dinner', 'meal', 'activity') for slot in free_slots))
            require((items or (compact and free_slots)) and len(legs) == max(0, len(items)-1))
            for order, item in enumerate(items):
                require(item['id'] not in seen and item['order'] == order+1)
                seen.add(item['id'])
                place = item['place']
                if compact:
                    require(set(place) == {'providerPlaceId'} and place['providerPlaceId'])
                    require(time.fromisoformat(item['startTime']) < time.fromisoformat(item['endTime']))
                    continue
                require(place['provider'] and place['providerPlaceId'] and place['name'])
                require(datetime.fromisoformat(place['checkedAt']).utcoffset() is not None)
                require(math.isfinite(place['latitude']) and -90 <= place['latitude'] <= 90)
                require(math.isfinite(place['longitude']) and -180 <= place['longitude'] <= 180)
                require(re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', item['startTime']))
                require(re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', item['endTime']))
                require(time.fromisoformat(item['startTime']) < time.fromisoformat(item['endTime']))
            for index, leg in enumerate(legs):
                require(leg['fromItemId'] == items[index]['id'] and leg['toItemId'] == items[index+1]['id'])
                if compact:
                    require(leg['mode'] in GOOGLE_MODES)
                    require(leg.get('status') in (None, 'verified', 'unverified'))
                    if leg.get('status') == 'unverified':
                        require('durationMinutes' not in leg and 'distanceMeters' not in leg)
                    require(time.fromisoformat(items[index]['endTime']) <= time.fromisoformat(items[index+1]['startTime']))
                    continue
                require(leg['status'] == 'verified' and leg['mode'] in ('walking', 'transit', 'driving'))
                require(leg['provider'] and datetime.fromisoformat(leg['checkedAt']).utcoffset() is not None)
                require(math.isfinite(leg['durationMinutes']) and leg['durationMinutes'] >= 0)
                require(math.isfinite(leg['distanceMeters']) and leg['distanceMeters'] >= 0)
                depart = time.fromisoformat(items[index]['endTime'])
                arrive_by = time.fromisoformat(items[index+1]['startTime'])
                available = (arrive_by.hour - depart.hour) * 60 + arrive_by.minute - depart.minute
                require(leg['durationMinutes'] <= available)
        require(seen)
        # 바탕 지도 정보는 서버 목록에서 정규화한다. 외부 초안의 중심 좌표를 신뢰하지 않는다.
        destination = DESTINATIONS[conditions.destinationId]
        content = dict(content, destination={**{k: destination[k] for k in ('id','countryCode','timeZone','mapCenter','mapZoom')}, 'name': destination['label']})
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
        fail(409, 'INVALID_DRAFT', '초안의 여행 조건·장소·경로 근거를 확인해 주세요.')
    return content



@router.get('/planning-options')
async def planning(request: Request):
    await authenticate(request)
    return dict(options(), generationAvailable=bool(config.openai_key and config.maps_key))


def reservation_cost(model_id):
    return generation.cost(model_id, generation.MAX_INPUT, generation.MAX_OUTPUT) * generation.MAX_ATTEMPTS


async def generation_limit(conn, uid, stamp, reserved):
    today = stamp.astimezone(timezone(timedelta(hours=9))).replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    mine = jobs.c.user_id == uid
    daily, monthly, total, settled = (await conn.execute(select(
        func.count().filter(mine, jobs.c.created_at >= today),
        func.count().filter(mine),
        func.coalesce(func.sum(jobs.c.cost_krw), 0),
        func.coalesce(func.sum(jobs.c.cost_krw).filter(jobs.c.status != 'running'), 0),
    ).where(jobs.c.created_at >= month))).one()
    next_month = (month + timedelta(days=32)).replace(day=1).isoformat()
    if reserved > config.generation_budget_krw:
        return dict(code='BUDGET_EXHAUSTED', resetsAt=None), total
    if monthly >= 20:
        return dict(code='MONTHLY_LIMIT_REACHED', resetsAt=next_month), total
    if total + reserved > config.generation_budget_krw:
        # 진행 중인 작업의 예약 비용이 정산되면 월말 전에도 풀릴 수 있다.
        reset = next_month if settled + reserved > config.generation_budget_krw else None
        return dict(code='BUDGET_EXHAUSTED', resetsAt=reset), total
    if daily >= 5:
        return dict(code='DAILY_LIMIT_REACHED', resetsAt=(today + timedelta(days=1)).isoformat()), total
    return None, total


@router.get('/generation-limit')
async def read_generation_limit(request: Request, modelId: GenerationModel):
    uid = (await authenticate(request))['user_id']
    async with engine.connect() as conn:
        limit, _ = await generation_limit(conn, uid, now(), reservation_cost(modelId))
    return {'limit': limit}


async def limit_requests(request, uid, scope, per_user, per_ip):
    stamp = now()
    ip = request.client.host if request.client else 'unknown'
    limits = [('ip:'+hashlib.sha256(ip.encode()).hexdigest(), per_ip)]
    if uid:
        limits.append(('user:'+str(uid), per_user))
    async with engine.begin() as conn:
        await conn.execute(delete(counters).where(counters.c.window_start < stamp-timedelta(hours=1)))
        for identity, maximum in limits:
            expired = counters.c.window_start <= stamp-timedelta(minutes=1)
            statement = pg_insert(counters).values(key=scope+identity, window_start=stamp, count=1)
            row = (await conn.execute(statement.on_conflict_do_update(index_elements=[counters.c.key], set_={
                'window_start': case((expired, stamp), else_=counters.c.window_start),
                'count': case((expired, 1), else_=counters.c.count+1)
            }).returning(counters.c.count, counters.c.window_start))).first()
            if row[0] > maximum:
                retry = max(1, math.ceil((row.window_start+timedelta(minutes=1)-stamp).total_seconds()))
                raise HTTPException(429, dict(code='RATE_LIMITED', message='잠시 후 다시 시도해 주세요.'),
                                    headers={'Retry-After':str(retry)})


@router.post('/generations', status_code=202)
async def generate(body: Conditions, request: Request, tasks: BackgroundTasks):
    session = await authenticate(request, write=True)
    uid = session['user_id']
    await limit_requests(request, uid, 'generate', 3, 30)
    if body.transportMode != 'walking':
        fail(422, 'INVALID_SELECTION', '최초 생성은 도보 기준입니다.')
    async with engine.begin() as conn:
        await lock_user(conn, uid)
        if request.headers.get('idempotency-key'):
            cached, values = await replay(conn, request, uid, body.model_dump(mode='json'))
            if cached:
                return cached
        if body.sourceTripId:
            trip = await owned(conn, session['user_id'], body.sourceTripId)
            if trip['version'] != body.baseTripVersion:
                fail(409, 'VERSION_CONFLICT', '최신 일정을 확인해 주세요.')
        elif await count_trips(conn, session['user_id']) >= 3:
            fail(409, 'SAVED_TRIP_LIMIT_EXCEEDED', '저장 일정이 3개입니다. 기존 일정만 재생성할 수 있습니다.')
        if not request.headers.get('idempotency-key'):
            fail(422, 'INVALID_SELECTION', '요청 식별자가 필요합니다.')
        if not (config.openai_key and config.maps_key):
            fail(503, 'GENERATION_UNAVAILABLE', '일정 생성 서비스 설정을 확인해 주세요.')
        # Serialize admission across workers, but never hold the lock during paid calls.
        await conn.execute(select(func.pg_advisory_xact_lock(7021101)))
        stamp = now()
        await conn.execute(update(jobs).where(jobs.c.status == 'running',
            jobs.c.created_at < stamp-timedelta(minutes=11)).values(status='failed', error_code='GENERATION_FAILED'))
        fingerprint = hashlib.sha256(('prompt-v8:'+values['body_hash']).encode()).hexdigest()
        common = jobs.c.user_id == uid
        existing = await conn.scalar(select(jobs.c.id).where(common, jobs.c.fingerprint == fingerprint,
            jobs.c.version == 1, jobs.c.status == 'completed', jobs.c.expires_at > stamp))
        if existing:
            status = dict(generationId=existing, status='completed', draftId=existing)
            await remember(conn, values, status)
            return status
        if await conn.scalar(select(jobs.c.id).where(common, jobs.c.status == 'running').limit(1)):
            fail(429, 'GENERATION_IN_PROGRESS', '이미 생성 중입니다.')
        reserved = reservation_cost(body.modelId)
        limit, total = await generation_limit(conn, uid, stamp, reserved)
        if limit:
            raise HTTPException(429, {**limit, 'message': '생성 한도에 도달했습니다.', 'retryable': False})
        if total < 0.8*config.generation_budget_krw <= total+reserved:
            logging.getLogger(__name__).warning('Monthly generation budget reached 80 percent')
        job_id = 'gen_'+uuid4().hex
        await conn.execute(insert(jobs).values(id=job_id,user_id=uid,fingerprint=fingerprint,created_at=stamp,
            expires_at=stamp+timedelta(hours=1),status='running',cost_krw=reserved))
        status = dict(generationId=job_id, status='queued')
        await remember(conn, values, status)
    tasks.add_task(generation.execute, job_id, body)
    return status


@router.get('/generation-requests/{key}')
async def find_generation_request(key: str, request: Request):
    uid = (await authenticate(request))['user_id']
    async with engine.connect() as conn:
        accepted = await conn.scalar(select(keys.c.response).where(
            keys.c.user_id == uid, keys.c.scope == 'POST:/api/generations',
            keys.c.key == key, keys.c.expires_at > now()))
    if accepted is None:
        fail(404, 'GENERATION_REQUEST_NOT_FOUND', '확인할 수 있는 생성 요청이 없습니다.')
    return accepted


async def get_job(conn, uid, job_id, lock=False):
    query = select(jobs).where(jobs.c.id == job_id, jobs.c.user_id == uid)
    row = (await conn.execute(query.with_for_update() if lock else query)).mappings().first()
    if not row:
        fail(404, 'RESOURCE_NOT_FOUND', '작업을 찾을 수 없습니다.')
    return row


@router.get('/generations/{job_id}')
async def generation_status(job_id: str, request: Request):
    uid = (await authenticate(request))['user_id']
    async with engine.connect() as conn:
        row = await get_job(conn, uid, job_id)
    status, code = row['status'], row['error_code']
    if status == 'running' and now()-row['created_at'] > timedelta(minutes=11):
        status, code = 'failed', 'GENERATION_FAILED'
    progress = generation.active_progress.get(job_id) if status == 'running' else None
    if status == 'completed':
        progress = dict(stage='completed', percent=100)
    return dict(generationId=job_id,status=status,draftId=job_id if status=='completed' else None,
                progress=progress,
                error={'code':code, 'details':(row['content'] or {}).get('failure')} if code else None)


@router.get('/drafts/{draft_id}')
async def draft_detail(draft_id: str, request: Request, day: int = Query(1, ge=1, le=7)):
    uid = (await authenticate(request))['user_id']
    await limit_requests(request, uid, 'display', 30, 120)
    async with engine.connect() as conn:
        row = await get_job(conn, uid, draft_id)
    if row['status'] != 'completed' or row['expires_at'] <= now():
        fail(409, 'INVALID_DRAFT', '유효한 초안이 필요합니다.')
    return dict(await generation.display_day(row['content'], day), id=draft_id, version=row['version'], publishedPostId=None)


class LegSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['walking','transit','driving']


async def leg_record(request, doc_id, day, leg, draft, write):
    uid = (await authenticate(request, write=write))['user_id']
    await limit_requests(request, uid, 'legs', 30, 120)
    table = jobs if draft else trips
    owner = jobs.c.user_id if draft else trips.c.owner_id
    async with engine.connect() as conn:
        row = (await conn.execute(select(table).where(table.c.id == doc_id, owner == uid))).mappings().first()
    if row is None:
        fail(404,'RESOURCE_NOT_FOUND','일정을 찾을 수 없습니다.')
    if draft and (row['status'] != 'completed' or row['expires_at'] <= now()):
        fail(409,'INVALID_DRAFT','초안을 확인해 주세요.')
    if write:
        match_version(request,row['version'])
    content = row['content']
    if not 1 <= day <= len(content['days']) or not 1 <= leg <= len(content['days'][day-1]['legs']):
        fail(404,'RESOURCE_NOT_FOUND','이동 구간을 찾을 수 없습니다.')
    active_day = content['days'][day-1]
    left, right = active_day['items'][leg-1:leg+1]
    times = await generation.day_leg_times(content['destination']['timeZone'], active_day['date'], active_day['items'], [leg-1])
    depart, arrive = times[leg-1]
    return table, owner == uid, row, (left['place']['providerPlaceId'], right['place']['providerPlaceId'], depart, arrive)


@router.get('/drafts/{doc_id}/days/{day}/legs/{leg}')
@router.get('/trips/{doc_id}/days/{day}/legs/{leg}')
async def get_leg(doc_id: str, day: int, leg: int, request: Request):
    _, _, row, args = await leg_record(request, doc_id, day, leg, '/drafts/' in request.url.path, False)
    async with httpx.AsyncClient() as client:
        choices = await route_choices(client, config.maps_key, *args)
    return dict(options=choices, version=row['version'])


@router.put('/drafts/{doc_id}/days/{day}/legs/{leg}')
@router.put('/trips/{doc_id}/days/{day}/legs/{leg}')
async def choose_leg(doc_id: str, day: int, leg: int, body: LegSelection, request: Request):
    draft = '/drafts/' in request.url.path
    table, owner, row, args = await leg_record(request, doc_id, day, leg, draft, True)
    async with httpx.AsyncClient() as client:
        result = await route_option(client, config.maps_key, body.mode, *args)
    if result['status'] != 'verified':
        code = {'no_route':'ROUTE_UNAVAILABLE','time_conflict':'ROUTE_TIME_CONFLICT','lookup_failed':'EXTERNAL_DATA_UNAVAILABLE'}[result['status']]
        fail(502 if result['status']=='lookup_failed' else 409, code, '이 수단을 적용할 수 없습니다.')
    content = deepcopy(row['content'])
    stored_leg = content['days'][day-1]['legs'][leg-1]
    stored_leg['mode'] = body.mode
    if stored_leg.get('status') == 'unverified':
        del stored_leg['status']
    version = row['version']+1
    async with engine.begin() as conn:
        statement = update(table).where(table.c.id == doc_id, owner, table.c.version == row['version'])
        if draft:
            statement = statement.where(jobs.c.expires_at > now())
        if (await conn.execute(statement.values(content=content,version=version))).rowcount != 1:
            fail(409,'VERSION_CONFLICT','일정이 변경됐어요.')
    return dict(version=version, leg={**stored_leg, **result})


@router.get('/trips')
async def list_trips(request: Request):
    session = await authenticate(request)
    async with engine.connect() as conn:
        rows = (await conn.execute(select(trips, posts.c.id.label('post_id')).outerjoin(posts, posts.c.trip_id == trips.c.id)
            .where(trips.c.owner_id == session['user_id']).order_by(trips.c.created_at, trips.c.id))).mappings().all()
    return dict(items=[dict(id=r['id'], version=r['version'], destination=r['content']['destination'],
        destinationName=r['content']['destination']['name'], startDate=r['content']['conditions']['startDate'],
        endDate=r['content']['conditions']['endDate'], dayCount=len(r['content']['days']), publishedPostId=r['post_id']) for r in rows], capacity=capacity(len(rows)))


@router.get('/trips/{trip_id}')
async def trip_detail(trip_id: str, request: Request, day: int = Query(1, ge=1, le=7)):
    session = await authenticate(request)
    async with engine.begin() as conn:
        row = await owned(conn, session['user_id'], trip_id)
        post = await conn.scalar(select(posts.c.id).where(posts.c.trip_id == trip_id))
    if row['content'].get('storage') == 'place_ids':
        await limit_requests(request, session['user_id'], 'display', 30, 120)
    return dict(await generation.display_day(row['content'], day), id=trip_id, version=row['version'], publishedPostId=post)


@router.post('/trips', status_code=201)
async def create_trip(body: Save, request: Request, load=Depends(verified_drafts)):
    session = await authenticate(request, write=True)
    uid = session['user_id']
    if body.editDraftId or body.baseTripVersion is not None:
        fail(409, 'INVALID_DRAFT', '신규 생성 초안만 저장할 수 있습니다.')
    async with engine.begin() as conn:
        await lock_user(conn, uid)
        cached, values = await replay(conn, request, uid, body.model_dump())
        if cached:
            return cached
        count = await count_trips(conn, uid)
        if count >= 3:
            fail(409, 'SAVED_TRIP_LIMIT_EXCEEDED', '최대 3개까지 저장할 수 있습니다.')
        content = validate_draft(await load(conn, uid, body), uid, body)
        if await conn.scalar(select(trips.c.id).where(trips.c.owner_id == uid, trips.c.source_draft_id == body.draftId)):
            fail(409, 'INVALID_DRAFT', '이미 저장한 생성 결과입니다.')
        trip_id = 'trip_' + uuid4().hex
        await conn.execute(insert(trips).values(id=trip_id, owner_id=uid, content=content, source_draft_id=body.draftId))
        result = dict(id=trip_id, version=1, **capacity(count+1))
        await remember(conn, values, result)
    return result


@router.put('/trips/{trip_id}')
async def update_trip(trip_id: str, body: Save, request: Request, load=Depends(verified_drafts)):
    session = await authenticate(request, write=True)
    uid = session['user_id']
    async with engine.begin() as conn:
        await lock_user(conn, uid)
        cached, values = await replay(conn, request, uid, body.model_dump())
        if cached:
            return cached
        row = await owned(conn, uid, trip_id)
        match_version(request, row['version'])
        if body.baseTripVersion != row['version']:
            fail(409, 'VERSION_CONFLICT', '기준 버전이 다릅니다.')
        content = validate_draft(await load(conn, uid, body), uid, body, trip_id)
        await conn.execute(update(trips).where(trips.c.id == trip_id).values(content=content, version=row['version']+1, updated_at=now()))
        result = dict(id=trip_id, version=row['version']+1, **capacity(await count_trips(conn, uid)))
        await remember(conn, values, result)
    return result


@router.delete('/trips/{trip_id}', status_code=204)
async def delete_trip(trip_id: str, request: Request):
    session = await authenticate(request, write=True)
    async with engine.begin() as conn:
        await lock_user(conn, session['user_id'])
        row = await owned(conn, session['user_id'], trip_id)
        match_version(request, row['version'])
        await conn.execute(delete(trips).where(trips.c.id == trip_id))
    return Response(status_code=204)


@router.put('/users/me/nickname')
async def nickname(body: Nickname, request: Request):
    session = await authenticate(request, write=True)
    if not re.fullmatch(r'[가-힣A-Za-z0-9]{2,20}', body.nickname):
        fail(422, 'INVALID_NICKNAME', '공백 없이 한글·영문·숫자 2~20자를 입력해 주세요.')
    try:
        async with engine.begin() as conn:
            await conn.execute(update(users).where(users.c.id == session['user_id']).values(nickname=body.nickname))
    except IntegrityError:
        fail(409, 'NICKNAME_TAKEN', '이미 사용 중인 닉네임입니다.')
    return {'nickname': body.nickname}


def public_copy(content):
    dest = DESTINATIONS[content['conditions']['destinationId']]
    places = []
    for day in content['days']:
        for index, item in enumerate(day['items']):
            place = item['place']
            stop = dict(mapPlaceId='place_'+uuid4().hex, day=day['day'], order=index+1,
                        name=item.get('visitLabel') or place.get('name') or f'방문 장소 {index+1}',
                        visitTime=item['startTime'])
            if place.get('providerPlaceId'):
                stop['googlePlaceId'] = place['providerPlaceId']
            if item.get('hoursBasis') == 'unknown':
                stop['hoursBasis'] = 'unknown'
            if index < len(day['legs']):
                leg = day['legs'][index]
                stop['outgoingMode'] = leg['mode']
                if leg.get('status') == 'unverified':
                    stop['outgoingRouteUnverified'] = True
            places.append(stop)
    free_slots = {str(day['day']): day['freeSlots'] for day in content['days'] if day.get('freeSlots')}
    return dict(destinationName=dest['label'], destination={'id': dest['id']},
        dayCount=len(content['days']), theme=' · '.join(INTERESTS[i] for i in content['conditions']['interestIds']),
        mapProvider='google', places=places, **({'freeSlots': free_slots} if free_slots else {}))


@router.post('/trips/{trip_id}/publication', status_code=201)
async def publish(trip_id: str, request: Request):
    session = await authenticate(request, write=True)
    async with engine.begin() as conn:
        await lock_user(conn, session['user_id'])
        trip = await owned(conn, session['user_id'], trip_id)
        if not await conn.scalar(select(users.c.nickname).where(users.c.id == session['user_id'])):
            fail(422, 'INVALID_NICKNAME', '게시 전에 공개 닉네임을 정해 주세요.')
        if await conn.scalar(select(posts.c.id).where(posts.c.trip_id == trip_id)):
            fail(409, 'ALREADY_PUBLISHED', '이미 게시한 일정입니다.')
        post_id = 'post_'+uuid4().hex
        await conn.execute(insert(posts).values(id=post_id, trip_id=trip_id, owner_id=session['user_id'], content=public_copy(trip['content'])))
    return dict(postId=post_id)


@router.delete('/trips/{trip_id}/publication', status_code=204)
async def unpublish(trip_id: str, request: Request):
    session = await authenticate(request, write=True)
    async with engine.begin() as conn:
        await lock_user(conn, session['user_id'])
        await owned(conn, session['user_id'], trip_id)
        await conn.execute(delete(posts).where(posts.c.trip_id == trip_id))
    return Response(status_code=204)


async def read_posts(conn, uid, offset=0, post_id=None):
    counts = select(hearts.c.post_id, func.count().label('count')).group_by(hearts.c.post_id).subquery()
    count = func.coalesce(counts.c.count, 0)
    mine = select(hearts.c.post_id).where(hearts.c.post_id == posts.c.id, hearts.c.user_id == uid).exists() if uid else False
    query = select(posts, users.c.nickname, count.label('count'), mine.label('mine') if uid else literal(False).label('mine')).join(users, users.c.id == posts.c.owner_id).outerjoin(counts, counts.c.post_id == posts.c.id)
    if post_id:
        query = query.where(posts.c.id == post_id)
    else:
        query = query.order_by(count.desc(), posts.c.published_at, posts.c.id).offset(offset).limit(11)
    rows = (await conn.execute(query)).mappings().all()
    return [dict(**r['content'], id=r['id'], authorNickname=r['nickname'], publishedAt=r['published_at'].isoformat(), heartCount=r['count'], heartedByMe=r['mine']) for r in rows]


@router.get('/posts')
async def list_posts(request: Request, offset: int = Query(default=0, ge=0, le=100000)):
    session = await authenticate(request, optional=True)
    async with engine.connect() as conn:
        items = await read_posts(conn, session['user_id'] if session else None, offset)
    for item in items:
        item['places'] = []
        item.pop('freeSlots', None)
    return dict(items=items[:10], nextOffset=offset+10 if len(items)>10 else None)


@router.get('/posts/{post_id}')
async def post_detail(post_id: str, request: Request):
    session = await authenticate(request, optional=True)
    async with engine.connect() as conn:
        items = await read_posts(conn, session['user_id'] if session else None, post_id=post_id)
    if not items:
        fail(404, 'RESOURCE_NOT_FOUND', '게시물을 찾을 수 없습니다.')
    post = items[0]
    post['publicMapAvailable'] = bool(config.maps_key)
    for item in post['places']:
        # Old public snapshots can contain only a place ID or a name and coordinates.
        if 'providerPlaceId' in item:
            item['googlePlaceId'] = item.pop('providerPlaceId')
        item.setdefault('name', f"방문 장소 {item['order']}")
        item.pop('latitude', None)
        item.pop('longitude', None)
    return post


@router.get('/posts/{post_id}/map')
async def public_day_map(post_id: str, day: int = Query(ge=1, le=7)):
    unavailable = {'available': False}
    if not config.maps_key:
        return unavailable
    async with engine.connect() as conn:
        content = await conn.scalar(select(posts.c.content).where(posts.c.id == post_id))
        if content is None:
            fail(404, 'RESOURCE_NOT_FOUND', '게시물을 찾을 수 없습니다.')
        destination = DESTINATIONS.get(content.get('destination', {}).get('id'))
        stops = [p for p in content['places'] if p['day'] == day]
        ids = [p.get('googlePlaceId') or p.get('providerPlaceId') for p in stops]
        unique = list(dict.fromkeys(pid for pid in ids if pid))
        if not destination or not unique:
            return unavailable

    async with httpx.AsyncClient() as client:
        google = GooglePlaces(client, config.maps_key)
        async def location(pid):
            try:
                data = await google.request('GET', 'places/' + quote(pid, safe=''), 'location,attributions')
            except PlanningFailure:
                return None
            coords = data.get('location', {})
            if not all(isinstance(coords.get(k), (float, int)) and math.isfinite(coords[k])
                       for k in ('latitude', 'longitude')):
                return None
            return {**coords, 'attributions': data.get('attributions', [])}
        coordinates = dict(zip(unique, await asyncio.gather(*(location(pid) for pid in unique))))
    items = [dict(id=p['mapPlaceId'], order=i, place=dict(name=p.get('name') or f'방문 장소 {i}', **coordinates[pid]))
             for i, (p, pid) in enumerate(zip(stops, ids), 1) if coordinates.get(pid)]
    return dict(available=True, center=destination['mapCenter'], zoom=destination['mapZoom'], items=items)


@router.put('/posts/{post_id}/heart')
@router.delete('/posts/{post_id}/heart')
async def heart(post_id: str, request: Request):
    session = await authenticate(request, write=True)
    async with engine.begin() as conn:
        if not await conn.scalar(select(posts.c.id).where(posts.c.id == post_id).with_for_update()):
            fail(404, 'RESOURCE_NOT_FOUND', '게시물을 찾을 수 없습니다.')
        if request.method == 'PUT':
            await conn.execute(pg_insert(hearts).values(post_id=post_id, user_id=session['user_id']).on_conflict_do_nothing())
        else:
            await conn.execute(delete(hearts).where(hearts.c.post_id == post_id, hearts.c.user_id == session['user_id']))
        count = await conn.scalar(select(func.count()).select_from(hearts).where(hearts.c.post_id == post_id))
    return dict(heartCount=count, heartedByMe=request.method == 'PUT')
