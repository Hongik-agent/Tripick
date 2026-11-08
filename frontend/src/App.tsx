import { useEffect, useState } from "react"
import { supabase } from "./supabase"
import GoogleSeoulMap from "./GoogleSeoulMap"
import {
  COMMUNITY_KEY,
  CommunityCards,
  Heart,
  loadCommunity,
  type SharedTrip,
} from "./community"

const trips = [
  {
    city: "도쿄",
    country: "일본",
    en: "TOKYO, JAPAN",
    days: 3,
    theme: "도시 산책 · 맛집 탐방",
    image: "photo-1540959733332-eab4deabeeaf",
    tag: "가볍게 떠나는 도시 여행",
    x: 86,
    y: 37,
  },
  {
    city: "발리",
    country: "인도네시아",
    en: "BALI, INDONESIA",
    days: 4,
    theme: "자연과 휴식 · 감성 숙소",
    image: "photo-1537996194471-e657df975ab4",
    tag: "느리게, 나를 위한 시간",
    x: 81,
    y: 66,
  },
  {
    city: "파리",
    country: "프랑스",
    en: "PARIS, FRANCE",
    days: 5,
    theme: "예술과 문화 · 로컬 산책",
    image: "photo-1502602898657-3e91760cbb34",
    tag: "골목마다 새로운 설렘",
    x: 49,
    y: 29,
  },
  {
    city: "방콕",
    country: "태국",
    en: "BANGKOK, THAILAND",
    days: 3,
    theme: "미식 여행 · 야경",
    image: "photo-1508009603885-50cf7c579365",
    tag: "다채로운 순간을 만나는 곳",
    x: 77,
    y: 53,
  },
]
type Trip = typeof trips[number] & {
  id?: number
  places?: string[]
  map?: string
}
const initialPlaces = [
  "센소지",
  "나카미세도리",
  "스미다 공원",
  "도쿄 스카이트리",
]
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {name === "pin" ? (
        <>
          <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" />
          <circle cx="12" cy="10" r="2.5" />
        </>
      ) : name === "spark" ? (
        <>
          <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" />
          <path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6Z" />
        </>
      ) : name === "arrow" ? (
        <>
          <path d="M4 12h16m-6-6 6 6-6 6" />
        </>
      ) : name === "globe" ? (
        <>
          <circle cx="12" cy="12" r="9" />
          <ellipse cx="12" cy="12" rx="4" ry="9" />
          <path d="M3 12h18" />
        </>
      ) : name === "user" ? (
        <>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
        </>
      ) : (
        <>
          <path d="m5 5 14 14M19 5 5 19" />
        </>
      )}
    </svg>
  )
}
function WorldMap({
  onSelect,
  detail = false,
  savedTrips,
  loggedIn = false,
}: {
  onSelect: (t: Trip) => void
  detail?: boolean
  savedTrips?: Trip[]
  loggedIn?: boolean
}) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState(0)
  return (
    <div className={"world-map " + (detail ? "detail-map" : "")}>
      <div
        className="map-art"
        style={{ transform: `scale(${zoom}) translateX(${pan}px)` }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          e.currentTarget.dataset.x = String(e.clientX)
        }}
        onPointerUp={(e) => {
          const start = Number(e.currentTarget.dataset.x)
          if (Math.abs(e.clientX - start) > 20)
            setPan((p) =>
              Math.max(-90, Math.min(90, p + (e.clientX - start) / 4)),
            )
        }}
      >
        <svg
          viewBox="0 0 1000 440"
          className="continents"
          aria-label="체험용 세계 지도"
        >
          <defs>
            <pattern
              id="grid"
              width="44"
              height="44"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M44 0H0V44"
                fill="none"
                stroke="#b7d8d9"
                strokeWidth=".5"
              />
            </pattern>
          </defs>
          <rect width="1000" height="440" fill="url(#grid)" />
          <g
            fill="#f9faf0"
            stroke="#d9e1d3"
            strokeWidth="1.4"
            strokeLinejoin="round"
          >
            <path d="m74 87 39-28 46 7 30-20 79 9 15 31-26 24-35 3-9 31-31 11-16 43-29-5-13-30-28-10-10-30-21-8Z" />
            <path d="m172 197 26 4 16 30 31 15 14 31-13 32-11 53-25 36-14-42-7-43-24-34-7-40Z" />
            <path d="m288 30 39-13 29 10-12 38-27 24-22-20Z" />
            <path d="m444 98 24-22 29 8 6 21 26-9 27 22-22 25-32-2-24 19-28-14-21-26Z" />
            <path d="m453 159 35-13 48 12 29 42-16 45-23 31-16 37-24-21-9-44-28-29-15-35Z" />
            <path d="m528 80 34-30 52 10 29-20 57 13 38-9 52 23 54-6 55 31 37 31-16 31-51-3-26 27-21 46-26 11-27-30-28-5-23-24-40 1-16 30-20 5-17-35-27-21-44-6-29-21Z" />
            <path d="m655 193 27 7 13 35-17 21-14-33Z" />
            <path d="m734 221 18 7 11 29 23 8-5 11-35-9-19-28Z" />
            <path d="m850 163 7 17-12 26-9-8Z" />
            <path d="m792 306 39-26 41 6 29 31-3 35-39 8-23-19-39 2Z" />
            <path d="m918 356 12-16 8 12-14 19Z" />
            <path d="m546 288 9-12 4 27-9 11Z" />
          </g>
          <g stroke="#e5e9dc" fill="none">
            <path d="m115 111 76 6 43-22m-80 43 65 6m293-42 13 30m75-40 19 56m36-69 12 76m57-93 3 95m43-92 14 108m-243 13 60 8m-49 27 42 6" />
          </g>
        </svg>
        {(savedTrips ?? trips).map((t: Trip, i) => {
          const location = trips.find(
            (destination) => destination.city === t.city,
          )
          const position =
            t.city === "서울"
              ? { x: 84, y: 34 }
              : t.city === "제주"
                ? { x: 83, y: 39 }
                : (location ?? t)
          const duplicateOffset =
            (savedTrips ?? trips)
              .slice(0, i)
              .filter((item) => item.city === t.city).length * 15
          return (
            <button
              key={t.id ?? t.city}
              className={
                savedTrips ? "map-pin saved-map-pin" : "map-pin pin-" + i
              }
              style={{
                left: position.x + "%",
                top: Math.min(85, position.y + duplicateOffset) + "%",
              }}
              onPointerDown={
                savedTrips ? (e) => e.stopPropagation() : undefined
              }
              onClick={() => onSelect(t)}
              aria-label={`${t.city} ${t.days}일 ${
                savedTrips ? "저장 일정 열기" : "일정 예시 열기"
              }`}
            >
              <span className="pin-dot">
                <Icon name="pin" size={17} />
              </span>
              <span className="pin-label">
                {t.city}
                <small>
                  {t.days - 1}박 {t.days}일{savedTrips ? " · 내 일정" : ""}
                </small>
              </span>
            </button>
          )
        })}
        <span className="ocean o1">ATLANTIC OCEAN</span>
        <span className="ocean o2">PACIFIC OCEAN</span>
        <span className="map-city">서울 · SEOUL</span>
      </div>
      <span className="map-caption">
        <span className="live-dot" />{" "}
        {detail
          ? "번호 핀으로 오늘의 동선을 확인하세요"
          : savedTrips
            ? !loggedIn
              ? "로그인하면 저장한 여행 일정이 지도에 표시돼요"
              : savedTrips.length
                ? `저장한 일정 ${savedTrips.length}개 · 핀을 눌러 확인하세요`
                : "아직 저장한 일정이 없어요. 나만의 여행을 저장해 보세요"
            : "어디로 떠나고 싶으세요? 핀을 눌러 둘러보세요"}
      </span>
      <div className="map-controls">
        <button
          aria-label="확대"
          onClick={() => setZoom((z) => Math.min(1.8, z + 0.2))}
        >
          +
        </button>
        <button
          aria-label="축소"
          onClick={() => setZoom((z) => Math.max(1, z - 0.2))}
        >
          −
        </button>
      </div>
      <span className="map-credit">TRIPICK EXPLORER · 모의 지도</span>
    </div>
  )
}
const createInitialConditions = () => ({
  destination: "도쿄",
  date: "",
  endDate: "",
  duration: "3일",
  company: "친구와",
  withChildren: false,
  withSeniors: false,
  taste: ["맛집 탐방"] as string[],
  density: "여유롭게",
  map: "구글맵",
})

export default function App() {
  const [activePlace, setActivePlace] = useState<number | null>(null)
  const focusPlace = (index: number) => {
    setActivePlace(index)
    if (window.matchMedia("(max-width:600px)").matches) setTab("지도")
  }
  const routePoint = (index: number) => ({
    x: 90 + (index % 4) * 100,
    y: 120 + Math.floor(index / 4) * 110 + (index % 2) * 65,
  })

  const [page, setPage] = useState("home"),
    [modal, setModal] = useState(""),
    [account, setAccount] = useState(""),
    [accountName, setAccountName] = useState(""),
    [selected, setSelected] = useState<Trip>(trips[0]),
    [saved, setSaved] = useState<Trip[]>([]),
    [day, setDay] = useState(1),
    [tab, setTab] = useState("일정"),
    [editing, setEditing] = useState(false),
    [places, setPlaces] = useState(initialPlaces),
    [draft, setDraft] = useState(initialPlaces),
    [step, setStep] = useState(0),
    [toast, setToast] = useState(""),
    [fail, setFail] = useState(false),
    [form, setForm] = useState(createInitialConditions)
  const [posts, setPosts] = useState<SharedTrip[]>(loadCommunity)
  const [loginReturn, setLoginReturn] = useState("form")
  const [loginBusy, setLoginBusy] = useState(false)
  const routePlaces = editing ? draft : places
  const notify = (s: string) => {
    setToast(s)
    setTimeout(() => setToast(""), 3000)
  }
  const go = (p: string) => {
    setPage(p)
    window.scrollTo(0, 0)
  }
  useEffect(() => {
    if (!supabase) return

    let active = true
    let request = 0
    // Supabase가 최초 세션과 OAuth 리디렉션 결과를 모두 이 이벤트로 전달합니다.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      const currentRequest = ++request
      const user = session?.user
      if (!user) {
        setAccount("")
        setAccountName("")
        setSaved([])
        return
      }

      // 서버가 Supabase 토큰을 검증하고 사용자 행을 저장한 뒤 로그인 상태를 반영합니다.
      void fetch("/api/users/me", {
        method: "PUT",
        headers: { Authorization: `Bearer ${session.access_token}` },
      }).then(async (response) => {
        if (!response.ok) throw new Error(`사용자 동기화 실패: ${response.status}`)
        const account = await response.json()
        if (account.id !== user.id) throw new Error("사용자 ID 불일치")
        if (!active || currentRequest !== request) return
        setAccount(user.id)
        setAccountName(user.user_metadata?.full_name ?? user.email ?? "여행자")
        try {
          // 개인 일정은 이번 단계에서 서버로 이전하지 않습니다.
          setSaved(JSON.parse(localStorage.getItem("tripick-" + user.id) || "[]"))
        } catch {
          setSaved([])
        }
        // OAuth는 페이지를 떠났다 돌아오므로 로그인 전 목적지를 세션에 보관합니다.
        const destination = sessionStorage.getItem("tripick-login-return")
        if (destination) {
          sessionStorage.removeItem("tripick-login-return")
          setModal("")
          if (destination === "form") resetConditions()
          go(destination)
        }
      }).catch((error) => {
        if (!active || currentRequest !== request) return
        console.error("사용자 동기화 실패", error)
        setAccount("")
        setAccountName("")
        setSaved([])
        notify("로그인 정보를 서버에 저장하지 못했어요. 다시 시도해 주세요")
      })
    })
    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])
  const resetConditions = () => {
    setForm(createInitialConditions())
    setStep(0)
    setFail(false)
  }
  const begin = () => {
    setLoginReturn("form")
    if (account) {
      resetConditions()
      go("form")
    } else {
      setModal("login")
    }
  }
  const login = async () => {
    if (!supabase) {
      notify("로그인을 사용할 수 없습니다. 잠시 후 다시 시도해 주세요")
      return
    }
    setLoginBusy(true)
    // 현재 페이지로 돌아오게 설정합니다. 이 URL을 Supabase Redirect URLs에 등록해야 합니다.
    sessionStorage.setItem("tripick-login-return", loginReturn)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin + window.location.pathname,
          // Google 세션이 남아 있어도 계정을 다시 선택하게 합니다.
          queryParams: { prompt: "select_account" },
        },
      })
      if (error) throw error
    } catch (error) {
      sessionStorage.removeItem("tripick-login-return")
      console.error("Google 로그인 시작 실패", error)
      notify("로그인을 완료하지 못했어요. 다시 시도해 주세요")
    } finally {
      setLoginBusy(false)
    }
  }
  const logout = async () => {
    if (!supabase) return
    const { error } = await supabase.auth.signOut({ scope: "local" })
    if (error) {
      console.error("로그아웃 실패", error)
      notify("로그아웃하지 못했어요. 다시 시도해 주세요")
      return
    }
    setModal("")
    go("home")
  }
  const persist = (items: Trip[]) => {
    setSaved(items)
    localStorage.setItem("tripick-" + account, JSON.stringify(items))
  }
  const open = (t: Trip, example = true) => {
    setSelected(t)
    setDay(1)
    setActivePlace(null)
    setPlaces(t.places || initialPlaces)
    setEditing(false)
    go(example ? "example" : "savedDetail")
  }
  const generate = () => {
    go("loading")
    setTimeout(() => {
      if (fail) {
        go("failure")
        return
      }
      setSelected({
        ...(trips.find((t) => t.city === form.destination) || trips[0]),
        city: form.destination,
        days: parseInt(form.duration),
        map: form.map,
      })
      setPlaces(initialPlaces)
      setDay(1)
      setActivePlace(null)
      go("result")
    }, 1600)
  }
  const save = () => {
    if (!account) {
      setModal("expired")
      return
    }
    if (saved.length >= 3) {
      setModal("limit")
      return
    }
    const t = { ...selected, places, id: Date.now() }
    persist([...saved, t])
    setSelected(t)
    go("savedDetail")
    notify("내 일정에 저장했어요")
  }
  const updatePosts = (next: SharedTrip[]) => {
    try {
      localStorage.setItem(COMMUNITY_KEY, JSON.stringify(next))
      setPosts(next)
      return true
    } catch {
      notify("브라우저 저장 공간을 확인해 주세요")
      return false
    }
  }
  const requireCommunityLogin = () => {
    setLoginReturn("home")
    setModal("login")
  }
  const toggleHeart = (id: number) => {
    if (!account) {
      requireCommunityLogin()
      return
    }
    updatePosts(
      posts.map((post) =>
        post.id === id
          ? {
              ...post,
              likedBy: post.likedBy.includes(account)
                ? post.likedBy.filter((user) => user !== account)
                : [...post.likedBy, account],
            }
          : post,
      ),
    )
  }
  const publishedPost = posts.find(
    (post) => post.owner === account && post.sourceId === selected.id,
  )
  const publishTrip = () => {
    if (!account) {
      requireCommunityLogin()
      return
    }
    if (!selected.id || !saved.some((trip) => trip.id === selected.id)) {
      notify("저장한 일정만 게시할 수 있어요")
      return
    }
    if (publishedPost) {
      setModal("unpublish")
      return
    }
    const timestamp = Date.now()
    const post: SharedTrip = {
      ...selected,
      id: timestamp,
      sourceId: selected.id,
      owner: account,
      publishedAt: timestamp,
      likedBy: [],
      places: [...places],
    }
    if (updatePosts([...posts, post])) notify("인기 일정 영역에 게시했어요")
  }
  const openCommunity = (post: SharedTrip) => {
    setSelected(post)
    setPlaces(post.places || initialPlaces)
    setDay(1)
    setActivePlace(null)
    setEditing(false)
    go("community")
  }
  const choice = (key: keyof typeof form, values: string[]) => (
    <div className="choices">
      {values.map((v) => (
        <button
          key={v}
          className={form[key] === v ? "chosen" : ""}
          onClick={() => setForm({ ...form, [key]: v })}
        >
          {v}
        </button>
      ))}
    </div>
  )
  return (
    <div className="app">
      <header>
        <a className="logo" onClick={() => go("home")}>
          <span className="logo-mark">
            <Icon name="pin" size={23} />
          </span>
          tripick<span className="logo-period">.</span>
        </a>
        <nav>
          <button
            className={page === "home" ? "nav-active" : ""}
            onClick={() => go("home")}
          >
            여행 둘러보기
          </button>
          <button onClick={begin}>
            AI 일정 만들기 <span className="tiny-new">AI</span>
          </button>
          <button onClick={() => {
            if (account) go("saved")
            else {
              setLoginReturn("saved")
              setModal("login")
            }
          }}>
            내 일정
          </button>
        </nav>
        <button
          className="login-btn"
          onClick={() => {
            if (account) setModal("account")
            else {
              setLoginReturn("home")
              setModal("login")
            }
          }}
        >
          <Icon name="user" size={16} />
          {account ? "여행자님" : "로그인"}
        </button>
      </header>
      {page === "home" ? (
        <>
          <section className="intro">
            <span className="eyebrow">
              <span className="live-dot" /> YOUR NEXT JOURNEY, PICKED FOR YOU
            </span>
            <h1>
              지도로 둘러보고,
              <br className="mobile-break" /> <span>내 취향으로 떠나세요.</span>
            </h1>
            <p>
              어디로 갈지만 정하세요. 설레는 여행의 시작부터 동선까지, 트리픽이
              함께할게요.
            </p>
          </section>
          <main
            className="home-main"
            style={{ paddingBottom: "clamp(40px, 5vw, 64px)" }}
          >
            <WorldMap
              savedTrips={account ? saved : []}
              loggedIn={Boolean(account)}
              onSelect={(t) => open(t, false)}
            />
            <section className="create-banner">
              <div className="banner-icon">
                <Icon name="spark" size={27} />
              </div>
              <div>
                <h2>여행 계획, 이제 고민 대신 설렘으로</h2>
                <p>
                  몇 가지 취향만 알려주면 AI가 나만의 여행 일정을 만들어 드려요.
                </p>
              </div>
              <button className="primary home-create-shimmer" onClick={begin}>
                <Icon name="spark" size={17} /> AI 일정 생성하기{" "}
                <Icon name="arrow" size={17} />
              </button>
            </section>
            <section className="discover">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">A LITTLE INSPIRATION</span>
                  <h2>
                    여행자들의 인기 일정{" "}
                    <span className="heading-spark">✧</span>
                  </h2>
                  <p>하트로 발견하는 여행자의 여정</p>
                </div>
                <span className="example-info">
                  로그인 없이 자유롭게 둘러보세요{" "}
                  <Icon name="arrow" size={16} />
                </span>
              </div>
              <CommunityCards
                posts={posts}
                account={account}
                onOpen={openCommunity}
                onHeart={toggleHeart}
              />
              <p className="community-disclaimer">
                모의 커뮤니티 · 현재 브라우저 안에서만 게시와 하트가 보관됩니다.
              </p>
            </section>
          </main>
        </>
      ) : page === "form" ? (
        <main className="flow">
          <button className="back" onClick={() => go("home")}>
            ← 여행 둘러보기
          </button>
          <span className="eyebrow">MAKE IT YOURS</span>
          <h1>어떤 여행을 꿈꾸세요?</h1>
          <p>취향을 알려주시면, 잘 맞는 여정을 준비할게요.</p>
          <div className="steps tripick-step-glow">
            {["여행지", "날짜·기간", "동행·인원", "취향·밀도", "지도·요약"].map(
              (v, i) => (
                <button
                  className={step === i ? "active" : ""}
                  onClick={() => setStep(i)}
                  key={v}
                >
                  {i + 1}
                  <span>{v}</span>
                </button>
              ),
            )}
          </div>
          <section className="form-panel">
            <h2>
              {
                [
                  "어디로 떠날까요?",
                  "언제, 얼마나 떠날까요?",
                  "누구와 함께하나요?",
                  "나에게 맞는 여행 스타일",
                  "준비가 모두 끝났어요",
                ][step]
              }
            </h2>
            {step === 0 ? (
              <>
                <label>국가·지역별 추천 도시</label>
                <p className="mb-4 text-xs leading-6 text-[#879481]">
                  국가·지역을 펼쳐 여행하고 싶은 도시 한 곳을 선택해 주세요.
                </p>
                <div className="mb-4 flex items-center gap-2 rounded-lg bg-[#edf5ec] px-4 py-3 text-xs text-[#277f68]">
                  <Icon name="pin" size={16} />
                  선택한 여행지 <strong>{form.destination}</strong>
                </div>
                <div className="space-y-3">
                  {[
                    {
                      region: "일본",
                      cities: [
                        "도쿄",
                        "오사카",
                        "삿포로",
                        "교토",
                        "후쿠오카",
                        "오키나와",
                      ],
                    },
                    {
                      region: "중국",
                      cities: ["베이징", "상하이", "충칭", "청두", "칭다오"],
                    },
                    {
                      region: "홍콩·대만·마카오",
                      cities: [
                        "홍콩",
                        "타이베이",
                        "가오슝",
                        "타이중",
                        "마카오",
                      ],
                    },
                    {
                      region: "한국",
                      cities: [
                        "서울",
                        "제주",
                        "인천",
                        "강릉",
                        "속초",
                        "여수",
                        "부산",
                        "경주",
                        "전주",
                      ],
                    },
                    {
                      region: "유럽 · 프랑스",
                      cities: ["파리", "니스", "리옹"],
                    },
                    {
                      region: "유럽 · 이탈리아",
                      cities: ["로마", "피렌체", "베네치아", "밀라노"],
                    },
                    {
                      region: "유럽 · 스페인",
                      cities: ["바르셀로나", "마드리드", "세비야"],
                    },
                    {
                      region: "유럽 · 영국",
                      cities: ["런던", "에든버러", "맨체스터"],
                    },
                    {
                      region: "미국",
                      cities: [
                        "뉴욕",
                        "로스앤젤레스",
                        "샌프란시스코",
                        "라스베이거스",
                        "호놀룰루",
                      ],
                    },
                    { region: "태국", cities: ["방콕", "치앙마이", "푸껫"] },
                    {
                      region: "인도네시아",
                      cities: ["발리", "자카르타", "욕야카르타"],
                    },
                  ].map((group) => (
                    <details
                      key={group.region}
                      open={group.cities.includes(form.destination)}
                      className="rounded-xl border border-[#e0e8dc] bg-white"
                    >
                      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-[#46654f]">
                        <span>
                          {group.region}
                          <span className="ml-2 font-normal text-[#96a28d]">
                            {group.cities.length}곳
                          </span>
                        </span>
                        <span className="text-[#2b8d76]">
                          {group.cities.includes(form.destination)
                            ? form.destination
                            : "도시 보기"}{" "}
                          <span aria-hidden="true">⌄</span>
                        </span>
                      </summary>
                      <div
                        className="choices border-t border-[#edf1e9] p-4"
                        role="group"
                        aria-label={group.region + " 추천 도시"}
                      >
                        {group.cities.map((city) => (
                          <button
                            key={city}
                            aria-pressed={form.destination === city}
                            className={
                              form.destination === city ? "chosen" : ""
                            }
                            onClick={() =>
                              setForm({
                                ...form,
                                destination: city,
                                map: "구글맵",
                              })
                            }
                          >
                            {city}
                          </button>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              </>
            ) : step === 1 ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="min-w-0">
                    <label htmlFor="departure-date">출발일 *</label>
                    <input
                      id="departure-date"
                      type="date"
                      required
                      style={{ minWidth: 0, width: "100%" }}
                      value={form.date}
                      onChange={(e) => {
                        const date = e.target.value
                        const endDate =
                          form.endDate && date && form.endDate >= date
                            ? form.endDate
                            : ""
                        setForm({
                          ...form,
                          date,
                          endDate,
                          duration:
                            date && endDate
                              ? `${Math.round((Date.parse(endDate) - Date.parse(date)) / 86400000) + 1}일`
                              : form.duration,
                        })
                      }}
                    />
                  </div>
                  <div className="min-w-0">
                    <label htmlFor="arrival-date">도착일 *</label>
                    <input
                      id="arrival-date"
                      type="date"
                      required
                      min={form.date || undefined}
                      disabled={!form.date}
                      style={{ minWidth: 0, width: "100%" }}
                      value={form.endDate}
                      onChange={(e) => {
                        const endDate = e.target.value
                        if (endDate && endDate < form.date) {
                          notify("도착일은 출발일 이후로 선택해 주세요")
                          return
                        }
                        setForm({
                          ...form,
                          endDate,
                          duration: endDate
                            ? `${Math.round((Date.parse(endDate) - Date.parse(form.date)) / 86400000) + 1}일`
                            : form.duration,
                        })
                      }}
                    />
                  </div>
                </div>
                <label>여행 기간</label>
                <div
                  className="rounded-lg bg-[#f1f6ed] px-4 py-3 text-xs text-[#68806b]"
                  role="status"
                >
                  {form.date && form.endDate
                    ? `${Math.max(0, parseInt(form.duration) - 1)}박 ${form.duration}`
                    : "출발일과 도착일을 선택하면 자동으로 계산돼요."}
                </div>
              </>
            ) : step === 2 ? (
              <>
                <label>동행</label>
                {choice("company", ["혼자", "친구와", "연인과", "가족과"])}
                <label>인원</label>
                <select>
                  <option>2명</option>
                  <option>1명</option>
                  <option>3명</option>
                  <option>4명 이상</option>
                </select>
                <fieldset className="mt-6">
                  <legend className="text-xs text-[#758579]">
                    함께하는 분을 알려주세요{" "}
                    <span className="text-[10px] text-[#9ba694]">
                      선택 · 중복 가능
                    </span>
                  </legend>
                  <p className="mt-2 text-[11px] leading-6 text-[#899681]">
                    동행자의 나이와 체력을 고려한 여행을 준비해요.
                  </p>
                  <div className="mt-3 space-y-3">
                    {([
                      {
                        key: "withChildren",
                        title: "아이와 함께해요",
                        description: "짧은 이동과 중간중간 쉬어가는 여행",
                      },
                      {
                        key: "withSeniors",
                        title: "고령의 동행자가 있어요",
                        description: "걷는 부담은 줄이고, 휴식은 넉넉하게",
                      },
                    ] as const).map((option) => (
                      <label
                        key={option.key}
                        style={{ display: "flex", margin: 0 }}
                        className="min-h-16 cursor-pointer items-center gap-3 rounded-xl border border-[#dfe8da] bg-[#fafcf7] px-4 py-3"
                      >
                        <input
                          type="checkbox"
                          checked={form[option.key]}
                          onChange={(e) =>
                            setForm({ ...form, [option.key]: e.target.checked })
                          }
                          className="h-5 w-5 shrink-0 accent-[#248b79]"
                        />
                        <span>
                          <span className="block text-xs font-medium text-[#48664e]">
                            {option.title}
                          </span>
                          <span className="mt-1 block text-[10px] leading-5 text-[#8a9780]">
                            {option.description}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </>
            ) : step === 3 ? (
              <>
                <label id="taste-label">가장 기대되는 순간</label>
                <p
                  id="taste-hint"
                  className="mb-3 text-[11px] leading-6 text-[#899681]"
                >
                  중복 선택 가능 · 마음에 드는 항목을 모두 골라도 좋아요.
                </p>
                <div
                  className="choices"
                  role="group"
                  aria-labelledby="taste-label"
                  aria-describedby="taste-hint"
                >
                  {[
                    "맛집 탐방",
                    "자연과 휴식",
                    "예술과 문화",
                    "쇼핑",
                    "액티비티",
                    "현지문화",
                  ].map((taste) => (
                    <button
                      key={taste}
                      type="button"
                      className={form.taste.includes(taste) ? "chosen" : ""}
                      aria-pressed={form.taste.includes(taste)}
                      onClick={() =>
                        setForm((previous) => ({
                          ...previous,
                          taste: previous.taste.includes(taste)
                            ? previous.taste.filter((value) => value !== taste)
                            : [...previous.taste, taste],
                        }))
                      }
                    >
                      {taste}
                    </button>
                  ))}
                </div>
                <label>일정 밀도</label>
                {choice("density", ["여유롭게", "알차게", "빼곡하게"])}
              </>
            ) : (
              <>
                <label>사용할 지도</label>
                {choice(
                  "map",
                  [
                    "서울",
                    "제주",
                    "인천",
                    "강릉",
                    "속초",
                    "여수",
                    "부산",
                    "경주",
                    "전주",
                  ].includes(form.destination)
                    ? ["네이버 지도", "카카오맵", "구글맵"]
                    : ["구글맵"],
                )}
                <div className="summary">
                  {form.destination} · {form.date || "출발일 미선택"} ~{" "}
                  {form.endDate || "도착일 미선택"} · {form.duration}
                  <br />
                  {form.company}
                  {form.withChildren ? " · 아이 동반" : ""}
                  {form.withSeniors ? " · 고령 동행자 동반" : ""} ·{" "}
                  {form.taste.length ? form.taste.join(" · ") : "취향 미선택"} ·{" "}
                  {form.density}
                </div>
                <label className="test-check">
                  <input
                    type="checkbox"
                    checked={fail}
                    onChange={(e) => setFail(e.target.checked)}
                  />{" "}
                  생성 실패 상태 체험
                </label>
              </>
            )}
            <div className="form-actions">
              {step > 0 && (
                <button className="secondary" onClick={() => setStep(step - 1)}>
                  이전
                </button>
              )}
              <button
                className="primary"
                onClick={() => {
                  if (
                    (step === 1 || step === 4) &&
                    (!form.date || !form.endDate || form.endDate < form.date)
                  ) {
                    setStep(1)
                    notify(
                      !form.date
                        ? "출발일을 선택해 주세요"
                        : !form.endDate
                          ? "도착일을 선택해 주세요"
                          : "도착일은 출발일 이후로 선택해 주세요",
                    )
                    return
                  }
                  if (step === 4) {
                    generate()
                  } else setStep(step + 1)
                }}
              >
                {step === 4 ? "AI 일정 생성하기" : "다음으로"}{" "}
                <Icon name="arrow" size={17} />
              </button>
            </div>
          </section>
        </main>
      ) : page === "loading" || page === "failure" ? (
        <main className="state-panel">
          <div className={page === "loading" ? "spinner" : "state-icon"}>
            <Icon name="spark" size={38} />
          </div>
          <h1>
            {page === "loading"
              ? "설렘을 일정으로 만드는 중"
              : "일정을 만들지 못했어요"}
          </h1>
          <p>
            {page === "loading"
              ? "장소와 방문 시간, 이동 동선을 꼼꼼히 살피고 있어요."
              : "선택한 조건은 그대로예요. 잠시 후 다시 시도해 주세요."}
          </p>
          {page === "failure" && (
            <button
              className="primary"
              onClick={() => {
                setFail(false)
                go("form")
                setStep(4)
              }}
            >
              조건 확인하고 다시 시도
            </button>
          )}
        </main>
      ) : page === "saved" ? (
        <main className="content">
          <span className="eyebrow">YOUR TRAVEL COLLECTION</span>
          <h1>
            내 여행 일정 <span className="count">{saved.length}/3</span>
          </h1>
          <p>설레는 다음 여행이 이곳에 모여 있어요.</p>
          {saved.length ? (
            <div className="cards saved-cards">
              {saved.map((t) => (
                <button
                  className="trip-card"
                  key={t.id}
                  onClick={() => open(t, false)}
                >
                  <img
                    className="saved-photo"
                    src={`https://images.unsplash.com/${t.image}?auto=format&fit=crop&w=600&q=80`}
                    alt={t.city}
                  />
                  <div className="card-body">
                    <span className="country">저장한 일정 · {t.days}일</span>
                    <h3>
                      {t.city}
                      <Icon name="arrow" />
                    </h3>
                    <p>{t.theme}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty">
              <Icon name="globe" size={40} />
              <h2>아직 저장한 일정이 없어요</h2>
              <p>나만의 첫 여행을 만들어 보세요.</p>
            </div>
          )}
          <button className="primary" onClick={begin}>
            <Icon name="spark" /> 새로운 AI 일정 만들기
          </button>
        </main>
      ) : (
        <main className="content result">
          <button
            className="back"
            onClick={() => go(page === "savedDetail" ? "saved" : "home")}
          >
            ← {page === "savedDetail" ? "내 일정" : "여행 둘러보기"}
          </button>
          <span className="eyebrow">
            {page === "community"
              ? "TRAVEL COMMUNITY · 게시된 일정"
              : page === "example"
                ? "ITINERARY PREVIEW · 일정 예시"
                : page === "savedDetail"
                  ? "MY SAVED TRIP · 저장한 일정"
                  : "YOUR AI ITINERARY · 생성 완료"}
          </span>
          <h1>
            {selected.city}, 나만의 속도로 만나는 {selected.days}일
          </h1>
          <p>
            {selected.country} · {selected.days - 1}박 {selected.days}일 ·{" "}
            {selected.theme}
          </p>
          <div className="result-top">
            <div className="day-tabs">
              {Array.from({ length: selected.days }, (_, i) => (
                <button
                  className={day === i + 1 ? "chosen" : ""}
                  onClick={() => {
                    setDay(i + 1)
                    setActivePlace(null)
                  }}
                  key={i}
                >
                  Day {i + 1}
                </button>
              ))}
            </div>
            <span className="read-only">
              {editing
                ? "장소를 자유롭게 수정하세요"
                : "읽기 전용 · " +
                  (page === "example"
                    ? "미리 준비한 여행 예시"
                    : "저장 후 편집할 수 있어요")}
            </span>
          </div>
          <div className="mobile-tabs">
            {["일정", "지도"].map((v) => (
              <button
                className={tab === v ? "chosen" : ""}
                onClick={() => setTab(v)}
                key={v}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="result-grid">
            <section
              className={"timeline " + (tab !== "일정" ? "mobile-hide" : "")}
            >
              <h2>
                Day {day} <span>도시의 매력을 만나는 하루</span>
              </h2>
              {(editing ? draft : places).map((p, i) => (
                <article
                  className={
                    "place" + (activePlace === i ? " place-focused" : "")
                  }
                  key={i}
                  onClick={(e) => {
                    if (!(e.target as HTMLElement).closest("a,button"))
                      focusPlace(i)
                  }}
                >
                  <button
                    type="button"
                    className="place-number"
                    aria-label={`${i + 1}번 장소 지도에서 중심 보기`}
                    aria-pressed={activePlace === i}
                    onClick={() => focusPlace(i)}
                  >
                    {i + 1}
                  </button>
                  <div>
                    <span className="place-time">
                      {9 + i * 2}:00 – {10 + i * 2}:30
                    </span>
                    <h3>
                      {selected.city === "도쿄"
                        ? p
                        : [
                            `${selected.city} 로컬 거리`,
                            "중앙 마켓",
                            "시티 공원",
                            "전망 명소",
                          ][i % 4]}
                    </h3>
                    <p>
                      {selected.city} 중심가 · 예시 주소 {i + 1}
                    </p>
                    <p className="reason">
                      {
                        [
                          "여행의 시작은 이곳에서, 현지의 일상을 느껴보세요.",
                          "지역의 맛과 이야기를 만나는 여유로운 시간.",
                          "산책하며 잠시 쉬어가기 좋은 장소예요.",
                          "도시를 한눈에 담으며 하루를 마무리해요.",
                        ][i % 4]
                      }
                    </p>
                    <small>영업 09:00–18:00 · 출처: 모의 여행 데이터</small>
                    {(() => {
                      const provider = selected.map || "구글맵"
                      const placeName =
                        selected.city === "도쿄"
                          ? p
                          : [
                              `${selected.city} 로컬 거리`,
                              "중앙 마켓",
                              "시티 공원",
                              "전망 명소",
                            ][i % 4]
                      const query = encodeURIComponent(
                        `${selected.city} ${placeName}`,
                      )
                      const href =
                        provider === "네이버 지도"
                          ? `https://map.naver.com/p/search/${query}`
                          : provider === "카카오맵"
                            ? `https://map.kakao.com/?q=${query}`
                            : `https://www.google.com/maps/search/?api=1&query=${query}`
                      return (
                        <div className="mt-3">
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-[#d8e8dc] bg-[#f2f8f0] px-3 py-2 text-[11px] font-medium text-[#27836c] transition-colors hover:bg-[#e6f2e6]"
                            aria-label={`${placeName} ${provider}로 연결하기 · 새 창 열림`}
                          >
                            <Icon name="pin" size={15} />
                            지도로 연결하기
                            <Icon name="arrow" size={14} />
                          </a>
                          <span className="ml-2 text-[9px] text-[#93a18b]">
                            {provider} · 장소 검색
                          </span>
                        </div>
                      )
                    })()}
                    {editing && (
                      <div className="edit-tools">
                        <button
                          onClick={() =>
                            setDraft(draft.filter((_, n) => n !== i))
                          }
                        >
                          삭제
                        </button>
                        <button
                          disabled={i === 0}
                          onClick={() => {
                            const a = [...draft]
                            ;[a[i - 1], a[i]] = [a[i], a[i - 1]]
                            setDraft(a)
                          }}
                        >
                          ↑ 순서 변경
                        </button>
                      </div>
                    )}
                    {i < (editing ? draft : places).length - 1 && (
                      <div className="travel-time">
                        도보 약 {8 + i * 3}분 · {0.5 + i * 0.2}km
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {editing && (
                <button
                  className="secondary"
                  onClick={() => setDraft([...draft, "새로운 추천 장소"])}
                >
                  + 장소 추가
                </button>
              )}
            </section>
            <section
              className={"route-map " + (tab !== "지도" ? "mobile-hide" : "")}
            >
              {selected.city === "서울" && selected.map === "구글맵" ? (
                <GoogleSeoulMap />
              ) : (
                <div className="focused-route-map">
                <div className="route-map-title">
                  <span>DAY {day} ROUTE</span>
                  <strong>{selected.city} · 모의 동선 지도</strong>
                </div>
                <svg
                  viewBox="0 0 500 450"
                  className="route-canvas"
                  aria-label="장소 번호별 모의 동선 지도"
                >
                  <defs>
                    <pattern
                      id="route-streets"
                      width="65"
                      height="65"
                      patternUnits="userSpaceOnUse"
                    >
                      <rect width="65" height="65" fill="#edf3e8" />
                      <rect
                        x="7"
                        y="7"
                        width="49"
                        height="49"
                        rx="7"
                        fill="#e2ebda"
                      />
                      <path
                        d="M0 0H65M0 0V65"
                        stroke="#fffdf5"
                        strokeWidth="9"
                      />
                    </pattern>
                  </defs>
                  <g
                    className="route-camera"
                    style={{
                      transform:
                        activePlace === null
                          ? "translate(0px, 0px)"
                          : `translate(250px, 225px) scale(1.25) translate(${-routePoint(activePlace).x}px, ${-routePoint(activePlace).y}px)`,
                    }}
                  >
                    <rect
                      x="-1000"
                      y="-1000"
                      width="2500"
                      height="2500"
                      fill="url(#route-streets)"
                    />
                    <path
                      d="M-100 350Q140 190 200 330T650 250"
                      stroke="#c1e1df"
                      strokeWidth="48"
                      fill="none"
                    />
                    <polyline
                      points={routePlaces
                        .map((_, i) => `${routePoint(i).x},${routePoint(i).y}`)
                        .join(" ")}
                      fill="none"
                      stroke="#439b86"
                      strokeWidth="4"
                      strokeDasharray="8 6"
                    />
                    {routePlaces.map((_, i) => (
                      <g
                        key={i}
                        className="route-place-pin"
                        role="button"
                        tabIndex={0}
                        aria-label={`${i + 1}번 장소 선택하고 지도 중심으로 보기`}
                        aria-pressed={activePlace === i}
                        onClick={() => focusPlace(i)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault()
                            focusPlace(i)
                          }
                        }}
                        transform={`translate(${routePoint(i).x} ${routePoint(i).y})`}
                      >
                        <circle
                          r={activePlace === i ? 29 : 22}
                          fill={activePlace === i ? "#eab16d" : "#ffffff"}
                          opacity=".6"
                        />
                        <circle
                          r="17"
                          fill={activePlace === i ? "#dd9151" : "#2d927d"}
                          stroke="white"
                          strokeWidth="3"
                        />
                        <text
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="white"
                          fontSize="12"
                          fontWeight="700"
                        >
                          {i + 1}
                        </text>
                      </g>
                    ))}
                  </g>
                </svg>
                <button
                  className="route-overview"
                  onClick={() => setActivePlace(null)}
                  aria-label="선택 해제하고 전체 동선 보기"
                >
                  전체 보기
                </button>
                <div className="route-focus-caption" role="status">
                  {activePlace !== null && routePlaces[activePlace] ? (
                    <>
                      <strong>
                        {activePlace + 1}번 ·{" "}
                        {selected.city === "도쿄"
                          ? routePlaces[activePlace]
                          : [
                              `${selected.city} 로컬 거리`,
                              "중앙 마켓",
                              "시티 공원",
                              "전망 명소",
                            ][activePlace % 4]}
                      </strong>
                      <span>선택한 장소를 중심으로 보고 있어요</span>
                    </>
                  ) : (
                    <>
                      <strong>오늘의 전체 동선</strong>
                      <span>일정 카드나 번호를 눌러 장소를 자세히 보세요</span>
                    </>
                  )}
                  <small>
                    모의 위치 · 실제 경로와 위치는 지도로 연결하기에서
                    확인하세요.
                  </small>
                </div>
                </div>
              )}
            </section>
          </div>
          <div className="result-actions">
            {page === "community" ? (
              <>
                <button className="primary" onClick={begin}>
                  내 취향으로 AI 일정 생성하기
                </button>
                <button
                  className="secondary"
                  onClick={() => toggleHeart(selected.id!)}
                >
                  <Heart
                    filled={posts
                      .find((post) => post.id === selected.id)
                      ?.likedBy.includes(account)}
                  />{" "}
                  하트{" "}
                  {posts.find((post) => post.id === selected.id)?.likedBy
                    .length || 0}
                </button>
              </>
            ) : page === "example" ? (
              <button className="primary" onClick={begin}>
                <Icon name="spark" />내 취향으로 AI 일정 생성하기
              </button>
            ) : page === "result" ? (
              <>
                <button className="primary" onClick={save}>
                  내 일정으로 저장
                </button>
                <button className="secondary" onClick={generate}>
                  재생성
                </button>
                <button className="text-btn" onClick={() => go("form")}>
                  조건 다시 선택
                </button>
              </>
            ) : editing ? (
              <>
                <button
                  className="primary"
                  onClick={() => {
                    setPlaces(draft)
                    persist(
                      saved.map((t) =>
                        t.id === selected.id ? { ...t, places: draft } : t,
                      ),
                    )
                    setSelected({ ...selected, places: draft })
                    setEditing(false)
                    notify("변경 사항을 저장했어요")
                  }}
                  disabled={!draft.length}
                >
                  변경 저장
                </button>
                <button
                  className="secondary"
                  onClick={() =>
                    notify("변경된 순서로 이동 시간을 재계산했어요")
                  }
                >
                  동선 재계산
                </button>
                <button className="text-btn" onClick={() => setEditing(false)}>
                  취소
                </button>
              </>
            ) : (
              <>
                <button
                  className="primary"
                  onClick={() => {
                    setDraft(places)
                    setEditing(true)
                  }}
                >
                  일정 편집
                </button>
                <button className="secondary" onClick={publishTrip}>
                  {publishedPost ? "게시 취소" : "일정 게시하기"}
                </button>
                <button
                  className="secondary danger"
                  onClick={() => setModal("delete")}
                >
                  일정 전체 삭제
                </button>
              </>
            )}
          </div>
        </main>
      )}
      <footer>
        <a className="logo" onClick={() => go("home")}>
          tripick<span className="logo-period">.</span>
        </a>
        <p>취향을 담은 여행, 트리픽과 함께.</p>
        <span>© 2025 Tripick. All journeys start with a pick.</span>
        <small>모의 서비스 · 실제 예약 및 지도 연동 없음</small>
      </footer>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal("")}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              aria-label="닫기"
              onClick={() => setModal("")}
            >
              <Icon name="close" />
            </button>
            <div className="modal-symbol">
              <Icon name="spark" size={30} />
            </div>
            {modal === "login" || modal === "expired" ? (
              <>
                <h2>
                  {modal === "expired"
                    ? "세션이 만료되었어요"
                    : "여행의 시작, 트리픽"}
                </h2>
                <p>나만의 여행 일정을 만들려면 로그인해 주세요.</p>
                <button className="google" onClick={login} disabled={loginBusy}>
                  구글로 계속하기
                </button>
                <small>구글 계정으로 안전하게 로그인합니다.</small>
              </>
            ) : modal === "limit" ? (
              <>
                <h2>여행 일정이 가득 찼어요</h2>
                <p>
                  최대 3개까지 저장할 수 있어요.
                  <br />
                  기존 일정을 삭제하면 새 일정을 저장할 수 있어요.
                </p>
                <button
                  className="primary"
                  onClick={() => {
                    setModal("")
                    go("saved")
                  }}
                >
                  내 일정 관리하기 · 3/3
                </button>
              </>
            ) : modal === "unpublish" ? (
              <>
                <h2>게시를 취소할까요?</h2>
                <p>
                  인기 일정 목록과 받은 하트가 삭제돼요.
                  <br />
                  개인 저장 일정은 그대로 유지됩니다.
                </p>
                <button
                  className="primary"
                  onClick={() => {
                    if (
                      updatePosts(
                        posts.filter((post) => post.id !== publishedPost?.id),
                      )
                    ) {
                      setModal("")
                      notify("게시를 취소했어요")
                    }
                  }}
                >
                  게시 취소하기
                </button>
              </>
            ) : modal === "delete" ? (
              <>
                <h2>이 일정을 삭제할까요?</h2>
                <p>
                  삭제한 일정은 복구할 수 없어요.
                  <br />
                  삭제 후 새로운 일정을 저장할 수 있어요.
                  <br />이 일정의 게시물과 하트도 함께 삭제됩니다.
                </p>
                <button
                  className="primary"
                  onClick={() => {
                    if (
                      !updatePosts(
                        posts.filter(
                          (post) =>
                            !(
                              post.owner === account &&
                              post.sourceId === selected.id
                            ),
                        ),
                      )
                    )
                      return
                    persist(saved.filter((t) => t.id !== selected.id))
                    setModal("")
                    go("saved")
                    notify("일정을 삭제했어요")
                  }}
                >
                  삭제하기
                </button>
              </>
            ) : (
              <>
                <h2>{accountName}님</h2>
                <p>저장한 일정 {saved.length}/3 · 이 브라우저에 보관됩니다.</p>
                <button
                  className="secondary"
                  onClick={logout}
                >
                  로그아웃
                </button>
              </>
            )}
            <button
              className="text-btn close-text"
              onClick={() => setModal("")}
            >
              닫기
            </button>
          </section>
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  )
}
