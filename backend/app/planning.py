from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# GeoNames 등 검토 좌표의 출처/라이선스는 docs/specs/06-implementation.md 참조.
# 지도 바탕의 중심점이며 실제 방문 장소/경로의 검증 근거가 아니다.
ROWS = [
('kr-seoul','서울','KR','Asia/Seoul',37.566,126.978,11),
('kr-jeju','제주','KR','Asia/Seoul',33.4016667,126.5461111,9),
('kr-incheon','인천','KR','Asia/Seoul',37.456,126.705,11),
('kr-gangneung','강릉','KR','Asia/Seoul',37.752657,128.872392,11),
('kr-sokcho','속초','KR','Asia/Seoul',38.20701,128.59181,11),
('kr-yeosu','여수','KR','Asia/Seoul',34.760622,127.66215,11),
('kr-busan','부산','KR','Asia/Seoul',35.102,129.030,11),
('kr-gyeongju','경주','KR','Asia/Seoul',35.84278,129.21167,11),
('kr-jeonju','전주','KR','Asia/Seoul',35.82483,127.14796,11),
('jp-tokyo','도쿄','JP','Asia/Tokyo',35.690,139.692,11),
('jp-osaka','오사카','JP','Asia/Tokyo',34.694,135.501,11),
('jp-sapporo','삿포로','JP','Asia/Tokyo',43.067,141.350,11),
('jp-kyoto','교토','JP','Asia/Tokyo',35.021,135.754,11),
('jp-fukuoka','후쿠오카','JP','Asia/Tokyo',33.600,130.417,11),
('jp-okinawa','오키나와','JP','Asia/Tokyo',26.50687,127.94581,9),
('cn-beijing','베이징','CN','Asia/Shanghai',39.907,116.397,11),
('cn-shanghai','상하이','CN','Asia/Shanghai',31.222,121.458,11),
('cn-chongqing','충칭','CN','Asia/Shanghai',29.560,106.558,11),
('cn-chengdu','청두','CN','Asia/Shanghai',30.667,104.067,11),
('cn-qingdao','칭다오','CN','Asia/Shanghai',36.06488,120.38042,11),
('hk-hong-kong','홍콩','HK','Asia/Hong_Kong',22.27832,114.17469,11),
('tw-taipei','타이베이','TW','Asia/Taipei',25.053,121.526,11),
('tw-kaohsiung','가오슝','TW','Asia/Taipei',22.616,120.313,11),
('tw-taichung','타이중','TW','Asia/Taipei',24.147,120.684,11),
('mo-macau','마카오','MO','Asia/Macau',22.20056,113.54611,11),
('fr-paris','파리','FR','Europe/Paris',48.853,2.349,11),
('fr-nice','니스','FR','Europe/Paris',43.703,7.266,11),
('fr-lyon','리옹','FR','Europe/Paris',45.749,4.848,11),
('it-rome','로마','IT','Europe/Rome',41.892,12.511,11),
('it-florence','피렌체','IT','Europe/Rome',43.779,11.246,11),
('it-venice','베네치아','IT','Europe/Rome',45.437134,12.332650,11),
('it-milan','밀라노','IT','Europe/Rome',45.464,9.190,11),
('es-barcelona','바르셀로나','ES','Europe/Madrid',41.389,2.159,11),
('es-madrid','마드리드','ES','Europe/Madrid',40.417,-3.703,11),
('es-seville','세비야','ES','Europe/Madrid',37.383,-5.973,11),
('gb-london','런던','GB','Europe/London',51.509,-0.126,11),
('gb-edinburgh','에든버러','GB','Europe/London',55.952,-3.196,11),
('gb-manchester','맨체스터','GB','Europe/London',53.481,-2.237,11),
('us-new-york','뉴욕','US','America/New_York',40.714,-74.006,11),
('us-los-angeles','로스앤젤레스','US','America/Los_Angeles',34.052,-118.244,11),
('us-san-francisco','샌프란시스코','US','America/Los_Angeles',37.77493,-122.41942,11),
('us-las-vegas','라스베이거스','US','America/Los_Angeles',36.17497,-115.13722,11),
('us-honolulu','호놀룰루','US','Pacific/Honolulu',21.30694,-157.85833,11),
('th-bangkok','방콕','TH','Asia/Bangkok',13.75398,100.50144,11),
('th-chiang-mai','치앙마이','TH','Asia/Bangkok',18.79038,98.98468,11),
('th-phuket','푸껫','TH','Asia/Bangkok',7.89059,98.39810,11),
('id-bali','발리','ID','Asia/Makassar',-8.33333,115.00000,9),
('id-jakarta','자카르타','ID','Asia/Jakarta',-6.215,106.845,11),
('id-yogyakarta','욕야카르타','ID','Asia/Jakarta',-7.80139,110.36472,11),
]
DESTINATIONS = {r[0]: dict(id=r[0], label=r[1], countryCode=r[2], timeZone=r[3],
    mapCenter=dict(latitude=r[4], longitude=r[5]), mapZoom=r[6], mapProviders=['google'],
    transportModes=[]) for r in ROWS}
# 기존 저장 일정의 조회·게시에는 좌표가 필요하므로 선택 대상에서만 제외한다.
RETIRED_DESTINATION_IDS = {'id-bali', 'id-jakarta', 'id-yogyakarta', 'gb-edinburgh',
    'es-seville', 'fr-lyon', 'tw-taichung'}
INTERESTS = dict(food='맛집 탐방', nature='자연과 휴식', culture='예술과 문화', shopping='쇼핑', activity='액티비티', local_culture='현지문화')


def options():
    choices = lambda values: [dict(id=k, label=v) for k, v in values.items()]
    return dict(optionsVersion='v1', maxTripDays=7, generationAvailable=False,
        destinations=[d for key, d in DESTINATIONS.items() if key not in RETIRED_DESTINATION_IDS],
        companionTypes=choices(dict(solo='혼자', friends='친구와', partner='연인과', family='가족과')),
        partySizes=choices({'1':'1명','2':'2명','3':'3명','4':'4명','5_plus':'5명 이상'}),
        interests=choices(INTERESTS), paces=choices(dict(relaxed='여유롭게 (2곳)', balanced='알차게 (3곳)', packed='빼곡하게 (4곳)')),
        transportModes=choices(dict(walking='도보', transit='대중교통', driving='자차')))


class Party(BaseModel):
    model_config = ConfigDict(extra='forbid')
    typeId: Literal['solo','friends','partner','family']
    sizeBand: Literal['1','2','3','4','5_plus']


GenerationModel = Literal['gpt-6-luna', 'gpt-6.1-terra']


class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    modelId: GenerationModel = 'gpt-6-luna'
    optionsVersion: Literal['v1'] = 'v1'
    destinationId: str
    startDate: date
    endDate: date
    party: Party
    interestIds: list[Literal['food','nature','culture','shopping','activity','local_culture']] = Field(min_length=1, max_length=6)
    paceId: Literal['relaxed','balanced','packed']
    transportMode: Literal['walking','transit','driving']
    mapProvider: Literal['google']
    sourceTripId: str | None = None
    baseTripVersion: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def valid(self):
        if self.destinationId not in DESTINATIONS or self.destinationId in RETIRED_DESTINATION_IDS or not 0 <= (self.endDate-self.startDate).days < 7:
            raise ValueError('허용 여행지와 1~7일 여행 기간을 확인해 주세요.')
        if self.party.typeId == 'solo' and self.party.sizeBand != '1':
            raise ValueError('혼자 여행은 1명만 선택할 수 있습니다.')
        if bool(self.sourceTripId) != (self.baseTripVersion is not None):
            raise ValueError('재생성 대상과 버전이 함께 필요합니다.')
        return self
