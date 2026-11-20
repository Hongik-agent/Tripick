import { Fragment, useEffect, useRef, useState } from "react"

import {
  api,
  ApiError,
  clearAuth,
  restoreAuth,
  type User,
  type Options,
  type Conditions,
  type Trip,
  type TripSummary,
  type Post,
  type Choice,
} from "./api"

import { sampleDistances, sampleModes, sampleStops } from "./sampleItinerary"

import GoogleMap from "./GoogleMap"

import WorldMap from "./WorldMap"

import { login } from "./auth"

const countryLabels: Record<string, string> = {
  KR: "한국",
  JP: "일본",
  CN: "중국",
  HK: "홍콩",
  TW: "대만",
  MO: "마카오",
  FR: "프랑스",
  IT: "이탈리아",
  ES: "스페인",
  GB: "영국",
  US: "미국",
  TH: "태국",
}

const mapProviders = [
  { id: "google", label: "구글맵", search: "https://www.google.com/maps/search/?api=1&query=" },
  { id: "naver", label: "네이버 지도", search: "https://map.naver.com/p/search/" },
  { id: "kakao", label: "카카오맵", search: "https://map.kakao.com/link/search/" },
]

function providersFor(countryCode?: string) {
  return countryCode === "KR" ? mapProviders : [mapProviders[0]]
}

const initial: Conditions = {
  optionsVersion: "v1",
  destinationId: "jp-tokyo",
  startDate: "",
  endDate: "",
  party: {
    sizeBand: "2",
    typeId: "friends",
    withChildren: false,
    withSeniors: false,
  },
  interestIds: ["food"],
  paceId: "relaxed",
  transportMode: "walking",
  mapProvider: "google",
}

function Choices({
  label,
  values,
  value,
  onChange,
}: {
  label: string
  values: Choice[]
  value: string
  onChange: (id: string) => void
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      <div className="choices">
        {values.map((v) => (
          <button
            type="button"
            key={v.id}
            className={value === v.id ? "chosen" : ""}
            aria-pressed={value === v.id}
            onClick={() => onChange(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export default function App() {
  const [page, setPage] = useState("home")

  const [user, setUser] = useState<User | null>(null)

  const [authReady, setAuthReady] = useState(false)

  const [saved, setSaved] = useState<TripSummary[]>([])

  const [posts, setPosts] = useState<Post[]>([])

  const [nextOffset, setNextOffset] = useState<number | null>(null)

  const [options, setOptions] = useState<Options | null>(null)

  const [form, setForm] = useState<Conditions>(initial)

  const [step, setStep] = useState(0)

  const [trip, setTrip] = useState<Trip | null>(null)

  const [post, setPost] = useState<Post | null>(null)

  const [day, setDay] = useState(1)

  const [selectedModes, setSelectedModes] = useState<Record<string, number>>({})

  const [legIndex, setLegIndex] = useState(0)

  const legDialog = useRef<HTMLDialogElement>(null)

  const [modal, setModal] = useState("")

  const [returnTo, setReturnTo] = useState("home")

  const [nickname, setNickname] = useState("")

  const [busy, setBusy] = useState(false)

  const [error, setError] = useState("")

  const [notice, setNotice] = useState("")

  const busyRef = useRef(false)

  const sessionEpoch = useRef(0)

  const go = (value: string) => {
    setPage(value)
    setError("")
    window.scrollTo(0, 0)
  }

  const perform = async (action: () => Promise<void>) => {
    if (busyRef.current) return

    busyRef.current = true
    setBusy(true)
    setError("")
    setNotice("")

    try {
      await action()
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청을 완료하지 못했어요.")
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const refreshSaved = async () => {
    const epoch = sessionEpoch.current

    const result = await api<{ items: TripSummary[] }>("/trips")

    if (epoch === sessionEpoch.current) setSaved(result.items)
  }

  const refreshPosts = async (offset = 0) => {
    const result = await api<{ items: Post[]; nextOffset: number | null }>(
      "/posts?offset=" + offset,
      {},
      true,
    )

    setPosts((old) =>
      offset
        ? [
            ...old,
            ...result.items.filter(
              (item) => !old.some((p) => p.id === item.id),
            ),
          ]
        : result.items,
    )

    setNextOffset(result.nextOffset)
  }

  useEffect(() => {
    let active = true

    const expired = () => {
      sessionEpoch.current++

      clearAuth()
      setUser(null)
      setSaved([])
      setOptions(null)
      setTrip(null)

      setPosts((old) => old.map((p) => ({ ...p, heartedByMe: false })))

      setPost((p) => (p ? { ...p, heartedByMe: false } : null))
    }

    window.addEventListener("tripick-auth-expired", expired)

    void (async () => {
      try {
        const callbackParams = new URLSearchParams(location.search)

        if (
          callbackParams.has("authError") ||
          callbackParams.has("code") ||
          callbackParams.has("error")
        ) {
          setError("로그인을 완료하지 못했어요. 다시 로그인해 주세요.")
          history.replaceState(null, "", location.pathname)
        }

        const profile = await restoreAuth()

        if (!active) return

        setUser(profile)
        setNickname(profile.nickname ?? "")

        await refreshSaved()

        const params = new URLSearchParams(location.search)

        const view = params.get("view")

        if (view && ["home", "saved", "form"].includes(view)) {
          setPage(view)

          if (view === "form")
            setOptions(await api<Options>("/planning-options"))

          history.replaceState(null, "", location.pathname)
        }
      } catch (e) {
        if (active && !(e instanceof ApiError && e.status === 401))
          setError(e instanceof Error ? e.message : "로그인 상태 확인 실패")
      } finally {
        if (active) {
          setAuthReady(true)

          try {
            await refreshPosts()
          } catch (e) {
            setError(e instanceof Error ? e.message : "게시물 조회 실패")
          }
        }
      }
    })()

    return () => {
      active = false
      window.removeEventListener("tripick-auth-expired", expired)
    }
  }, [])

  const requireLogin = (target: string) => {
    setReturnTo(target)
    setModal("login")
  }

  const begin = () => {
    if (!user) return requireLogin("form")

    if (saved.length >= 3) {
      setNotice(
        "저장한 일정이 3개입니다. 내 일정에서 기존 일정을 재생성해 주세요.",
      )
      return
    }

    void perform(async () => {
      setOptions(await api<Options>("/planning-options"))
      setForm(initial)
      setStep(0)
      go("form")
    })
  }

  const openTrip = (id: string) =>
    void perform(async () => {
      const result = await api<Trip>("/trips/" + id)
      setTrip(result)
      setPost(null)
      setDay(1)
      go("detail")
    })

  const openPost = (id: string) =>
    void perform(async () => {
      const result = await api<Post>("/posts/" + id, {}, true)
      setPost(result)
      setTrip(null)
      setDay(1)
      go("community")
    })

  const toggleHeart = (value: Post) => {
    if (!user) return requireLogin("home")

    void perform(async () => {
      const result = await api<{ heartCount: number; heartedByMe: boolean }>(
        "/posts/" + value.id + "/heart",
        { method: value.heartedByMe ? "DELETE" : "PUT" },
      )

      setPost((old) => (old?.id === value.id ? { ...old, ...result } : old))

      await refreshPosts()
    })
  }

  const publish = () =>
    void perform(async () => {
      if (!trip) return

      if (!user?.nickname) {
        setModal("account")
        setNotice("게시 전에 공개 닉네임을 정해 주세요.")
        return
      }

      if (trip.publishedPostId) {
        await api("/trips/" + trip.id + "/publication", { method: "DELETE" })

        setTrip({ ...trip, publishedPostId: null })
      } else {
        const result = await api<{ postId: string }>(
          "/trips/" + trip.id + "/publication",
          { method: "POST" },
        )

        setTrip({ ...trip, publishedPostId: result.postId })
      }

      await refreshSaved()
      await refreshPosts()
    })

  const duration =
    form.startDate && form.endDate
      ? Math.round(
          (Date.parse(form.endDate) - Date.parse(form.startDate)) / 86400000,
        ) + 1
      : 0

  const destination = options?.destinations.find(
    (d) => d.id === form.destinationId,
  )

  const sample = page === "sample"

  const detailDestination = sample
    ? destination
    : (trip?.destination ?? post?.destination)

  const detailLabel = sample
    ? (destination?.label ?? "")
    : (trip?.destination.name ?? post?.destinationName ?? "")

  const providerId = sample ? form.mapProvider : trip?.conditions.mapProvider
  const provider = providersFor(detailDestination?.countryCode).find((p) => p.id === providerId) ?? mapProviders[0]

  const detailDays = sample
    ? duration
    : (trip?.days.length ?? post?.dayCount ?? 0)

  const items = sample
    ? sampleStops(destination?.countryCode, day)
    : (trip?.days

        .find((d) => d.day === day)

        ?.items.map((i) => ({
          ...i.place,
          id: i.id,
          visitTime: i.startTime,
        })) ??
      post?.places.filter((p) => p.day === day) ??
      [])

  const updateForm = (key: keyof Conditions, value: string) =>
    setForm((f) => ({ ...f, [key]: value }))

  return (
    <div className="app">
      <header>
        <button
          className="logo"
          onClick={() => go("home")}
          aria-label="트리픽 홈"
        >
          <img className="logo-mark" src="/tripick.svg" alt="" />
          Tripick
          <span className="logo-period">.</span>
        </button>
        <nav>
          <button
            className={page === "home" ? "nav-active" : ""}
            onClick={() => go("home")}
          >
            여행 둘러보기
          </button>
          <button onClick={begin} disabled={busy}>
            AI 일정 만들기 <span className="tiny-new">AI</span>
          </button>
          <button
            onClick={() =>
              user
                ? void perform(async () => {
                    await refreshSaved()
                    go("saved")
                  })
                : requireLogin("saved")
            }
          >
            내 일정
          </button>
        </nav>
        <button
          className="login-btn"
          disabled={!authReady}
          onClick={() => (user ? setModal("account") : requireLogin("home"))}
        >
          {user
            ? (user.nickname ?? "내 계정")
            : authReady
              ? "로그인"
              : "확인 중"}
        </button>
      </header>
      <div className="status-messages" aria-live="polite">
        {error && (
          <p role="alert" className="error-message">
            {error}{" "}
            <button onClick={() => setError("")} aria-label="오류 안내 닫기">
              ×
            </button>
          </p>
        )}
        {notice && <p>{notice}</p>}
      </div>
      {page === "home" ? (
        <>
          <section className="intro">
            <span className="eyebrow">YOUR NEXT JOURNEY, PICKED FOR YOU</span>
            <h1>
              지도로 둘러보고,
              <br className="mobile-break" /> <span>내 취향으로 떠나세요.</span>
            </h1>
            <p>설레는 여행의 시작, 트리픽과 함께 계획해 보세요.</p>
          </section>
          <main className="home-main">
            <WorldMap trips={saved} loggedIn={!!user} onSelect={openTrip} />
            <section className="create-banner">
              <div>
                <h2>여행 계획, 이제 고민 대신 설렘으로</h2>
                <p>여행 조건을 골라 보세요. 샘플 일정으로 미리 볼 수 있어요.</p>
              </div>
              <button className="primary" disabled={busy} onClick={begin}>
                여행 조건 선택하기 →
              </button>
            </section>
            <section className="discover">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">A LITTLE INSPIRATION</span>
                  <h2>여행자들의 인기 일정 ✧</h2>
                  <p>하트로 발견하는 여행자의 여정</p>
                </div>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void perform(() => refreshPosts())}
                >
                  새로고침
                </button>
              </div>
              {!posts.length ? (
                <div className="community-empty">
                  <h3>첫 번째 여행 이야기를 기다리고 있어요</h3>
                  <p>검증된 저장 일정의 공개 사본이 표시됩니다.</p>
                </div>
              ) : (
                <div className="cards">
                  {posts.map((p) => (
                    <article className="trip-card community-card" key={p.id}>
                      <button
                        className="community-open"
                        onClick={() => openPost(p.id)}
                      >
                        <div className="card-body">
                          <span className="country">{p.dayCount}일 여행</span>
                          <h3>{p.destinationName}</h3>
                          <p>{p.theme}</p>
                        </div>
                      </button>
                      <div className="community-meta">
                        <span>
                          {p.authorNickname} ·{" "}
                          {new Date(p.publishedAt).toLocaleDateString("ko-KR")}
                        </span>
                        <button
                          className={
                            "heart-button" + (p.heartedByMe ? " liked" : "")
                          }
                          disabled={busy}
                          aria-label={`${p.destinationName} 하트 ${
                            p.heartedByMe ? "취소" : "추가"
                          }`}
                          aria-pressed={p.heartedByMe}
                          onClick={() => toggleHeart(p)}
                        >
                          ♥ {p.heartCount}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
              {nextOffset !== null && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void perform(() => refreshPosts(nextOffset))}
                >
                  10개 더 보기
                </button>
              )}
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
          <p>여행 기간은 최대 7일입니다.</p>
          {!options ? (
            <p>여행 선택지를 불러오지 못했습니다. 다시 로그인해 주세요.</p>
          ) : (
            <>
              <div className="steps">
                {[
                  "여행지",
                  "날짜·기간",
                  "동행·인원",
                  "취향·밀도",
                  "지도·요약",
                ].map((label, i) => (
                  <button
                    key={label}
                    className={step === i ? "active" : ""}
                    onClick={() => setStep(i)}
                  >
                    {i + 1}
                    <span>{label}</span>
                  </button>
                ))}
              </div>
              <section
                className={
                  step === 4 ? "form-panel review-panel" : "form-panel"
                }
              >
                {step === 0 ? (
                  <>
                    <h2>어디로 떠날까요?</h2>
                    <p>한 일정에는 여행지 한 곳을 선택해 주세요.</p>
                    {Array.from(
                      new Set(options.destinations.map((d) => d.countryCode)),
                    ).map((country) => (
                      <details
                        key={country}
                        open={destination?.countryCode === country}
                      >
                        <summary>
                          {countryLabels[country ?? ""] ?? country}
                        </summary>
                        <div className="choices">
                          {options.destinations
                            .filter((d) => d.countryCode === country)
                            .map((d) => (
                              <button
                                key={d.id}
                                className={
                                  form.destinationId === d.id ? "chosen" : ""
                                }
                                aria-pressed={form.destinationId === d.id}
                                onClick={() =>
                                  setForm((f) => ({ ...f, destinationId: d.id, mapProvider: d.countryCode === "KR" ? f.mapProvider : "google" }))
                                }
                              >
                                {d.label}
                              </button>
                            ))}
                        </div>
                      </details>
                    ))}
                  </>
                ) : step === 1 ? (
                  <>
                    <h2>언제 떠날까요?</h2>
                    <label htmlFor="start-date">출발일</label>
                    <input
                      id="start-date"
                      type="date"
                      value={form.startDate}
                      onChange={(e) => updateForm("startDate", e.target.value)}
                    />
                    <label htmlFor="end-date">도착일</label>
                    <input
                      id="end-date"
                      type="date"
                      min={form.startDate}
                      value={form.endDate}
                      onChange={(e) => updateForm("endDate", e.target.value)}
                    />
                    <p>
                      {duration >= 1 && duration <= 7
                        ? `${duration}일 여행`
                        : "출발일과 도착일을 포함해 1~7일로 선택해 주세요."}
                    </p>
                  </>
                ) : step === 2 ? (
                  <>
                    <h2>누구와 함께하나요?</h2>
                    <Choices
                      label="동행"
                      values={options.companionTypes}
                      value={form.party.typeId}
                      onChange={(v) =>
                        setForm((f) => ({
                          ...f,
                          party: {
                            ...f.party,
                            typeId: v,
                            sizeBand: v === "solo" ? "1" : f.party.sizeBand,
                          },
                        }))
                      }
                    />
                    <Choices
                      label="동행 인원"
                      values={options.partySizes}
                      value={form.party.sizeBand}
                      onChange={(v) =>
                        setForm((f) => ({
                          ...f,
                          party: {
                            ...f.party,
                            sizeBand: v,
                            typeId:
                              v !== "1" && f.party.typeId === "solo"
                                ? "friends"
                                : f.party.typeId,
                          },
                        }))
                      }
                    />
                    <label>
                      <input
                        type="checkbox"
                        checked={form.party.withChildren}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            party: {
                              ...form.party,
                              withChildren: e.target.checked,
                            },
                          })
                        }
                      />{" "}
                      아이와 함께
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={form.party.withSeniors}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            party: {
                              ...form.party,
                              withSeniors: e.target.checked,
                            },
                          })
                        }
                      />{" "}
                      고령자와 함께
                    </label>
                  </>
                ) : step === 3 ? (
                  <>
                    <h2>나에게 맞는 여행 스타일</h2>
                    <fieldset>
                      <legend>취향 (하나 이상)</legend>
                      <div className="choices">
                        {options.interests.map((v) => (
                          <button
                            key={v.id}
                            className={
                              form.interestIds.includes(v.id) ? "chosen" : ""
                            }
                            aria-pressed={form.interestIds.includes(v.id)}
                            onClick={() =>
                              setForm((f) => ({
                                ...f,
                                interestIds: f.interestIds.includes(v.id)
                                  ? f.interestIds.filter((i) => i !== v.id)
                                  : [...f.interestIds, v.id],
                              }))
                            }
                          >
                            {v.label}
                          </button>
                        ))}
                      </div>
                    </fieldset>
                    <Choices
                      label="여행 밀도"
                      values={options.paces}
                      value={form.paceId}
                      onChange={(v) => updateForm("paceId", v)}
                    />
                  </>
                ) : (
                  <>
                    <h2>여행 조건을 확인해 주세요</h2>
                    <p className="summary">
                      {destination?.label} ·{" "}
                      {duration > 0 ? duration : "미선택"}일 ·{" "}
                      {
                        options.partySizes.find(
                          (p) => p.id === form.party.sizeBand,
                        )?.label
                      }
                    </p>
                    <div className="choices">
                      {providersFor(destination?.countryCode).map((p) => (
                        <button key={p.id}
                          className={form.mapProvider === p.id ? "chosen" : ""}
                          aria-pressed={form.mapProvider === p.id}
                          onClick={() => updateForm("mapProvider", p.id)}>
                          <span aria-hidden="true">🗺️</span> {p.label}
                        </button>
                      ))}
                    </div>
                    <p>
                      샘플 일정으로 방문 순서와 구간별 이동수단을 확인해 보세요.
                    </p>
                    <button
                      className="primary"
                      disabled={
                        !destination ||
                        duration < 1 ||
                        duration > 7 ||
                        !form.interestIds.length
                      }
                      onClick={() => {
                        setSelectedModes({})

                        setDay(1)

                        go("sample")
                      }}
                    >
                      샘플 일정 만들기
                    </button>
                  </>
                )}
              </section>
              <div className="form-actions">
                {step > 0 && (
                  <button
                    className="secondary"
                    onClick={() => setStep(step - 1)}
                  >
                    이전
                  </button>
                )}
                {step < 4 && (
                  <button
                    className="primary"
                    disabled={step === 1 && (duration < 1 || duration > 7)}
                    onClick={() => setStep(step + 1)}
                  >
                    다음 →
                  </button>
                )}
              </div>
            </>
          )}
        </main>
      ) : page === "saved" ? (
        <main className="content">
          <h1>
            내 여행 일정 <span className="count">{saved.length}/3</span>
          </h1>
          <p>같은 계정으로 로그인하면 다른 기기에서도 확인할 수 있습니다.</p>
          <div className="cards saved-cards">
            {saved.map((t) => (
              <button
                className="trip-card"
                key={t.id}
                onClick={() => openTrip(t.id)}
              >
                <div className="card-body">
                  <h3>{t.destinationName}</h3>
                  <p>
                    {t.startDate} ~ {t.endDate}
                  </p>
                  <p>
                    {t.dayCount}일 ·{" "}
                    {t.publishedPostId ? "게시 중" : "나만의 일정"}
                  </p>
                </div>
              </button>
            ))}
          </div>
          {!saved.length && (
            <p className="community-empty">저장한 일정이 없습니다.</p>
          )}
          <button className="primary" onClick={begin}>
            여행 조건 선택하기
          </button>
        </main>
      ) : (sample || page === "detail" || page === "community") &&
        detailDestination ? (
        <main className="content">
          <button
            className="back"
            onClick={() => go(sample ? "form" : trip ? "saved" : "home")}
          >
            ← {sample ? "여행 조건으로" : "목록으로"}
          </button>
          <span className="eyebrow">
            {sample ? "샘플 일정" : trip ? "MY TRIP" : "TRAVEL STORY"}
          </span>
          <h1>
            {detailLabel}, {detailDays}일의 여행
          </h1>
          {sample ? (
            <p>
              {form.startDate} ~ {form.endDate} · 장소와 이동 시간·거리는
              예시입니다.
            </p>
          ) : trip ? (
            <p>
              {trip.conditions.startDate} ~ {trip.conditions.endDate}
            </p>
          ) : (
            <p>
              {post?.authorNickname} · {post?.theme}
            </p>
          )}
          <div className="result-top">
            <div className="day-tabs">
              {Array.from({ length: detailDays }, (_, i) => (
                <button
                  key={i}
                  className={day === i + 1 ? "chosen" : ""}
                  onClick={() => setDay(i + 1)}
                >
                  DAY {i + 1}
                </button>
              ))}
            </div>
          </div>
          <div className="result-grid">
            <section className="timeline">
              <h2>방문 장소</h2>
              {items.map((item, i) => {
                const mode = sampleModes[selectedModes[day + "-" + i] ?? 0]
                return (
                <Fragment key={"id" in item ? item.id : item.mapPlaceId}>
                  <article className="place">
                    <span className="place-number">{i + 1}</span>
                    <div>
                      <h3>{item.name}</h3>
                      {"visitTime" in item && <p>{item.visitTime}</p>}
                    </div>
                  </article>
                  <div className="place-actions">
                    {sample && i < items.length - 1 && (
                      <button className="leg-button" onClick={() => {
                        setLegIndex(i)
                        legDialog.current?.showModal()
                      }}>
                        <span aria-hidden="true">{mode.icon}</span> {mode.label} · {mode.minutes[i]}분 · {sampleDistances[i]}m ›
                      </button>
                    )}
                    <a className="place-map-link"
                      href={provider.search + encodeURIComponent(detailLabel + " " + item.name)}
                      target="_blank" rel="noopener noreferrer"
                      aria-label={provider.label + "에서 " + item.name + " 검색 (새 창)"}>
                      <span aria-hidden="true">🗺️</span> {provider.label}
                    </a>
                  </div>
                </Fragment>
                )
              })}
              {!items.length && <p>방문 장소가 없습니다.</p>}
            </section>
            <section className="route-map">
              <GoogleMap
                center={detailDestination.mapCenter}
                zoom={detailDestination.mapZoom}
                label={detailLabel}
              />
            </section>
          </div>
          {sample && (
            <dialog
              ref={legDialog}
              className="leg-dialog"
              aria-labelledby="leg-title"
            >
              <form method="dialog">
                <button className="close" aria-label="닫기">
                  ×
                </button>
              </form>
              <h2 id="leg-title">이 구간 이동수단</h2>
              <p>
                {items[legIndex]?.name} → {items[legIndex + 1]?.name} ·{" "}
                {sampleDistances[legIndex]}m
              </p>
              {sampleModes.map((mode, index) => (
                <button
                  key={mode.label}
                  className="leg-option"
                  aria-pressed={
                    (selectedModes[day + "-" + legIndex] ?? 0) === index
                  }
                  onClick={() => {
                    setSelectedModes((old) => ({
                      ...old,
                      [day + "-" + legIndex]: index,
                    }))

                    legDialog.current?.close()
                  }}
                >
                  <span><span aria-hidden="true">{mode.icon}</span> {mode.label}</span>
                  <span>{mode.minutes[legIndex]}분</span>
                </button>
              ))}
            </dialog>
          )}
          <p className="migration-notice">
            실제 장소 마커와 경로 표시는 후속 단계에서 제공됩니다.
          </p>
          <div className="result-actions">
            {sample ? null : trip ? (
              <>
                <button className="primary" disabled={busy} onClick={publish}>
                  {trip.publishedPostId ? "게시 취소" : "일정 게시하기"}
                </button>
                <button
                  className="secondary"
                  disabled
                  title="실제 장소·경로 검증 연동 후 제공"
                >
                  편집·재생성 준비 중
                </button>
                <button className="text-btn" onClick={() => setModal("delete")}>
                  일정 삭제
                </button>
              </>
            ) : (
              post && (
                <button
                  className="primary"
                  disabled={busy}
                  aria-pressed={post.heartedByMe}
                  onClick={() => toggleHeart(post)}
                >
                  ♥ {post.heartCount}{" "}
                  {post.heartedByMe ? "하트 취소" : "하트 보내기"}
                </button>
              )
            )}
          </div>
        </main>
      ) : (
        <main className="content">
          <p>로그인 상태를 확인해 주세요.</p>
          <button className="primary" onClick={() => requireLogin("saved")}>
            로그인
          </button>
        </main>
      )}
      <footer>
        <span className="logo">Tripick.</span>
        <span>나의 취향으로 채우는 여행</span>
        <small>지도 중심 좌표: GeoNames · NGA · UNT</small>
      </footer>
      {modal && (
        <div className="modal-backdrop" onClick={() => !busy && setModal("")}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close"
              aria-label="닫기"
              disabled={busy}
              onClick={() => setModal("")}
            >
              ×
            </button>
            {modal === "login" ? (
              <>
                <h2 id="modal-title">여행을 시작해 볼까요?</h2>
                <p>로그인하면 나만의 일정을 관리할 수 있어요.</p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => void perform(() => login("google", returnTo))}
                >
                  Google로 로그인
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void perform(() => login("kakao", returnTo))}
                >
                  Kakao로 로그인
                </button>
              </>
            ) : modal === "account" ? (
              <>
                <h2 id="modal-title">내 계정</h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    void perform(async () => {
                      const result = await api<{ nickname: string }>(
                        "/users/me/nickname",
                        { method: "PUT", body: JSON.stringify({ nickname }) },
                      )
                      setUser((u) =>
                        u ? { ...u, nickname: result.nickname } : u,
                      )
                      await refreshPosts()
                      setNotice("공개 닉네임을 저장했어요.")
                      setModal("")
                    })
                  }}
                >
                  <label htmlFor="nickname">공개 닉네임</label>
                  <input
                    id="nickname"
                    value={nickname}
                    onChange={(e) => setNickname(e.target.value)}
                    minLength={2}
                    maxLength={20}
                    pattern="[가-힣A-Za-z0-9]{2,20}"
                    required
                  />
                  <p>공백 없이 한글·영문·숫자 2~20자. 대소문자를 구분합니다.</p>
                  <button className="primary" disabled={busy}>
                    닉네임 저장
                  </button>
                </form>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      await api("/auth/logout", { method: "POST" })
                      window.dispatchEvent(new Event("tripick-auth-expired"))
                      setModal("")
                      go("home")
                      await refreshPosts()
                    })
                  }
                >
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <h2 id="modal-title">일정을 삭제할까요?</h2>
                <p>연결된 게시물과 하트도 함께 삭제됩니다.</p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      if (!trip) return
                      await api("/trips/" + trip.id, {
                        method: "DELETE",
                        headers: { "If-Match": String(trip.version) },
                      })
                      setTrip(null)
                      setModal("")
                      go("saved")
                      await refreshSaved()
                      await refreshPosts()
                    })
                  }
                >
                  삭제하기
                </button>
              </>
            )}
            {error && (
              <p role="alert" className="error-message">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
