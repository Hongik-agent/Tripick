"""Domestic area and place suggestions used when TourAPI has no matching candidates."""

# Named sites from the domestic-visitor samples in the Busan (2024) and Incheon (2016) surveys.
# "기장 해안 카페" in the Busan survey is an area/category, not a single venue.
DOMESTIC_SURVEY_PLACES = {
    'kr-busan': ('국제시장', '해운대해수욕장', '오륙도'),
    'kr-incheon': ('인천차이나타운', '월미공원', '소래포구'),
}

# Within a destination, list measured examples first and use official tourism selections for coverage.
DOMESTIC_CANDIDATES = {
    'kr-seoul': [
        ('용산/국립중앙박물관', {'culture'}),
        ('종로/광장시장', {'food', 'shopping', 'local_culture'}),
        ('성수/서울숲', {'nature'}),
        ('잠실/롯데월드', {'activity'}),
        ('서촌/서촌마을', {'culture', 'local_culture'}),
    ],
    'kr-jeju': [
        ('성산/성산일출봉', {'nature', 'activity'}),
        ('제주시내/동문재래시장', {'food', 'shopping', 'local_culture'}),
        ('함덕/함덕해수욕장', {'nature', 'activity'}),
        ('안덕/방주교회', {'culture', 'local_culture'}),
        ('제주시내/우진해장국', {'food'}),
        ('한림/협재해수욕장', {'nature', 'activity'}),
        ('서귀포시내/매일올레시장', {'food', 'shopping', 'local_culture'}),
        ('한림/금능해수욕장', {'nature', 'activity'}),
        ('애월/곽지해수욕장', {'nature', 'activity'}),
        ('서귀포시내/천지연폭포', {'nature'}),
        ('서귀포시내/정방폭포', {'nature'}),
    ],
    'kr-incheon': [
        ('개항장/인천차이나타운', {'food', 'culture', 'local_culture'}),
        ('월미도/월미공원', {'nature', 'activity'}),
        ('논현동/소래포구', {'food', 'local_culture'}),
        ('송도/센트럴파크', {'nature', 'activity'}),
        ('신포동/신포국제시장', {'food', 'shopping', 'local_culture'}),
    ],
    'kr-gangneung': [
        ('정동진/정동심곡 바다부채길', {'nature', 'activity'}),
        ('죽헌동/오죽헌', {'culture', 'local_culture'}),
        ('안목/강릉커피거리', {'food'}),
        ('주문진/주문진수산시장', {'food', 'shopping', 'local_culture'}),
    ],
    'kr-sokcho': [
        ('중앙동/속초관광수산시장', {'food', 'shopping', 'local_culture'}),
        ('설악동/설악산국립공원', {'nature', 'activity'}),
        ('청호동/아바이마을', {'food', 'culture', 'local_culture'}),
        ('영랑호/범바위', {'nature'}),
    ],
    'kr-yeosu': [
        ('수정동/오동도', {'nature', 'activity'}),
        ('구항/진남관', {'culture', 'local_culture'}),
        ('교동/여수수산시장', {'food', 'shopping', 'local_culture'}),
        ('돌산/여수해상케이블카', {'activity'}),
    ],
    'kr-busan': [
        ('남포동/국제시장', {'food', 'shopping', 'local_culture'}),
        ('해운대/해운대해수욕장', {'nature', 'activity'}),
        ('용호동/오륙도', {'nature'}),
        ('광안리/광안리해변', {'nature', 'activity'}),
        ('감천/감천문화마을', {'culture', 'local_culture'}),
        ('남포동/자갈치시장', {'food', 'shopping', 'local_culture'}),
        ('영도/태종대유원지', {'nature'}),
    ],
    'kr-gyeongju': [
        ('황남동/황리단길', {'food', 'shopping', 'local_culture'}),
        ('황남동/대릉원', {'culture', 'local_culture'}),
        ('보문/보문호반길', {'nature', 'activity'}),
        ('불국동/불국사', {'culture'}),
    ],
    'kr-jeonju': [
        ('교동/전주한옥마을', {'culture', 'local_culture', 'activity'}),
        ('풍남문/남부시장', {'food', 'shopping', 'local_culture'}),
        ('한옥마을/경기전', {'culture', 'local_culture'}),
        ('한옥마을/오목대', {'nature', 'activity'}),
    ],
}


def domestic_hints(destination_id, interests):
    places = [place for place, tags in DOMESTIC_CANDIDATES.get(destination_id, ())
              if tags.intersection(interests)]
    return places[:6]
