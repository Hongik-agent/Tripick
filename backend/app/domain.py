import hashlib
import json
import re
import math
from datetime import timedelta, datetime, time
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError
from sqlalchemy import select, insert, update, delete, func, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from .auth import authenticate, now
from .config import idempotency_ttl_seconds
from .db import engine
from .errors import fail
from .models import users, trips, posts, post_hearts as hearts, idempotency_keys as keys
from .planning import Conditions, options, DESTINATIONS, INTERESTS

router = APIRouter(prefix='/api')


async def verified_drafts():
    # 실제 생성/편집 검증 저장소는 AI 단계에서 연결한다. 운영에서는 신뢰 초안이 없다.
    # 테스트는 이 dependency만 교체하며 클라이언트 검증 플래그를 신뢰하지 않는다.
    async def load(*args):
        fail(409, 'INVALID_DRAFT', '검증된 생성 결과가 필요합니다.')
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
        seen = set()
        for index, day in enumerate(days):
            require(day['day'] == index+1 and day['date'] == (conditions.startDate+timedelta(days=index)).isoformat())
            items, legs = day['items'], day['legs']
            require(items and len(legs) == len(items)-1)
            for order, item in enumerate(items):
                require(item['id'] not in seen and item['order'] == order+1)
                seen.add(item['id'])
                place = item['place']
                require(place['provider'] and place['providerPlaceId'] and place['name'])
                require(datetime.fromisoformat(place['checkedAt']).utcoffset() is not None)
                require(math.isfinite(place['latitude']) and -90 <= place['latitude'] <= 90)
                require(math.isfinite(place['longitude']) and -180 <= place['longitude'] <= 180)
                require(re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', item['startTime']))
                require(re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', item['endTime']))
                require(time.fromisoformat(item['startTime']) < time.fromisoformat(item['endTime']))
            for index, leg in enumerate(legs):
                require(leg['fromItemId'] == items[index]['id'] and leg['toItemId'] == items[index+1]['id'])
                require(leg['status'] == 'verified' and leg['mode'] == conditions.transportMode)
                require(leg['provider'] and datetime.fromisoformat(leg['checkedAt']).utcoffset() is not None)
                require(math.isfinite(leg['durationMinutes']) and leg['durationMinutes'] >= 0)
                require(math.isfinite(leg['distanceMeters']) and leg['distanceMeters'] >= 0)
        # 바탕 지도 정보는 서버 목록에서 정규화한다. 외부 초안의 중심 좌표를 신뢰하지 않는다.
        destination = DESTINATIONS[conditions.destinationId]
        content = dict(content, destination={**{k: destination[k] for k in ('id','countryCode','timeZone','mapCenter','mapZoom')}, 'name': destination['label']})
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
        fail(409, 'INVALID_DRAFT', '초안의 여행 조건·장소·경로 근거를 확인해 주세요.')
    return content



@router.get('/planning-options')
async def planning(request: Request):
    await authenticate(request)
    return options()


@router.post('/generations')
async def generate(body: Conditions, request: Request):
    session = await authenticate(request, write=True)
    async with engine.begin() as conn:
        await lock_user(conn, session['user_id'])
        if body.sourceTripId:
            trip = await owned(conn, session['user_id'], body.sourceTripId)
            if trip['version'] != body.baseTripVersion:
                fail(409, 'VERSION_CONFLICT', '최신 일정을 확인해 주세요.')
        elif await count_trips(conn, session['user_id']) >= 3:
            fail(409, 'SAVED_TRIP_LIMIT_EXCEEDED', '저장 일정이 3개입니다. 기존 일정만 재생성할 수 있습니다.')
    fail(503, 'GENERATION_UNAVAILABLE', '실제 장소와 경로를 검증하는 일정 생성을 준비 중입니다.')


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
async def trip_detail(trip_id: str, request: Request):
    session = await authenticate(request)
    async with engine.begin() as conn:
        row = await owned(conn, session['user_id'], trip_id)
        post = await conn.scalar(select(posts.c.id).where(posts.c.trip_id == trip_id))
    return dict(**row['content'], id=trip_id, version=row['version'], publishedPostId=post)


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
    return dict(destinationName=dest['label'], destination={k: dest[k] for k in ('id','mapCenter','mapZoom')},
        dayCount=len(content['days']), theme=' · '.join(INTERESTS[i] for i in content['conditions']['interestIds']),
        mapProvider='google', places=[dict(mapPlaceId='place_'+uuid4().hex, day=d['day'], order=index+1,
            **{k: item['place'][k] for k in ('name','latitude','longitude')})
            for d in content['days'] for index, item in enumerate(d['items'])])


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
    return dict(items=items[:10], nextOffset=offset+10 if len(items)>10 else None)


@router.get('/posts/{post_id}')
async def post_detail(post_id: str, request: Request):
    session = await authenticate(request, optional=True)
    async with engine.connect() as conn:
        items = await read_posts(conn, session['user_id'] if session else None, post_id=post_id)
    if not items:
        fail(404, 'RESOURCE_NOT_FOUND', '게시물을 찾을 수 없습니다.')
    return items[0]


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
