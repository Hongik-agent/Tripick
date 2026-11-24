export type Destination = {
  id: string
  label?: string
  name?: string
  countryCode?: string
  timeZone?: string
  mapCenter: { latitude: number; longitude: number }
  mapZoom: number
}

export type Choice = { id: string; label: string }

export type Options = {
  optionsVersion: string
  generationAvailable: boolean
  destinations: Destination[]
  companionTypes: Choice[]
  partySizes: Choice[]
  interests: Choice[]
  paces: Choice[]
  transportModes: Choice[]
}

export type Conditions = {
  modelId?: string
  optionsVersion: string
  destinationId: string
  startDate: string
  endDate: string
  party: {
    sizeBand: string
    typeId: string
  }
  interestIds: string[]
  paceId: string
  transportMode: string
  mapProvider: string
  sourceTripId?: string
  baseTripVersion?: number
}

export type Item = {
  id: string
  order: number
  place: { name: string; providerPlaceId?: string; latitude: number; longitude: number; attributions?: Attribution[] }
  hoursBasis?: string
  startTime: string
  endTime: string
}

export type Attribution = { provider?: string; providerUri?: string }
export type Leg = { mode: string; durationMinutes?: number; distanceMeters?: number; status: string }
export type Day = {
  day: number
  items: Item[]
  legs: Leg[]
  freeSlots?: ("breakfast" | "lunch" | "dinner" | "meal" | "activity")[]
}

export type TripSummary = {
  id: string
  version: number
  destination: Destination
  destinationName: string
  startDate: string
  endDate: string
  dayCount: number
  publishedPostId: string | null
}

export type Trip = {
  storage?: string
  id: string
  version: number
  destination: Destination
  conditions: Conditions
  days: Day[]
  publishedPostId: string | null
}

export type Post = {
  publicMapAvailable?: boolean
  storage?: string
  id: string
  authorNickname: string
  destinationName: string
  destination: Pick<Destination, "id">
  dayCount: number
  theme: string
  freeSlots?: Record<string, Day["freeSlots"]>
  places: {
    mapPlaceId: string
    day: number
    order: number
    name: string
    visitTime?: string
    hoursBasis?: string
    googlePlaceId?: string
    outgoingMode?: "walking" | "transit" | "driving"
    outgoingRouteUnverified?: boolean
  }[]
  heartCount: number
  heartedByMe: boolean
  publishedAt: string
}

export type User = { id: string; email: string | null; nickname: string | null }

export type GenerationLimit = {
  code: "DAILY_LIMIT_REACHED" | "MONTHLY_LIMIT_REACHED" | "BUDGET_EXHAUSTED"
  resetsAt: string | null
}

export function generationLimitMessage(limit: GenerationLimit) {
  const message = {
    DAILY_LIMIT_REACHED: "오늘의 일정 생성 횟수를 모두 사용했어요.",
    MONTHLY_LIMIT_REACHED: "이번 달의 일정 생성 횟수를 모두 사용했어요.",
    BUDGET_EXHAUSTED: "지금은 서비스의 일정 생성 한도에 도달했어요. 기존 일정은 계속 볼 수 있어요.",
  }[limit.code]
  if (!limit.resetsAt) return message
  const reset = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(limit.resetsAt))
  return `${message} ${reset}(한국 시간)부터 다시 만들 수 있어요.`
}

let csrfToken = ""

export function clearAuth() {
  csrfToken = ""
}

const alertMessages: Record<string, string> = {
  AUTH_REQUIRED: "로그인 후 다시 시도해 주세요.",
  CSRF_FAILED: "화면을 새로고침한 뒤 다시 시도해 주세요.",
  UNSUPPORTED_PROVIDER: "지원하는 로그인 방법을 선택해 주세요.",
  RESOURCE_NOT_FOUND: "요청한 일정이나 게시물을 찾을 수 없어요. 목록을 확인해 주세요.",
  SAVED_TRIP_LIMIT_EXCEEDED: "일정은 최대 3개까지 저장할 수 있어요. 내 일정에서 기존 일정을 확인해 주세요.",
  VERSION_CONFLICT: "일정이 변경됐어요. 최신 일정을 확인한 뒤 다시 시도해 주세요.",
  INVALID_DRAFT: "이 일정은 저장할 수 없어요. 검증이 끝난 일정을 다시 확인해 주세요.",
  NICKNAME_TAKEN: "이미 사용 중인 닉네임이에요. 다른 이름을 입력해 주세요.",
  INVALID_NICKNAME: "공백 없이 한글·영문·숫자 2~20자로 공개 닉네임을 정해 주세요.",
  ALREADY_PUBLISHED: "이미 게시한 일정이에요. 게시 목록을 확인해 주세요.",
  IDEMPOTENCY_CONFLICT: "이전 요청과 내용이 달라졌어요. 현재 내용을 확인하고 다시 시도해 주세요.",
  INVALID_SELECTION: "입력한 조건을 확인해 주세요.",
  UNSUPPORTED_TRANSPORT: "이 구간에서는 해당 이동수단을 이용할 수 없어요.",
  ROUTE_UNAVAILABLE: "두 방문지 사이의 경로를 확인할 수 없어요.",
  ROUTE_TIME_CONFLICT: "이 수단으로는 다음 방문 시간에 맞춰 도착하기 어려워요.",
  GENERATION_UNAVAILABLE: "지금은 일정을 만들 수 없어요. 잠시 후 다시 시도해 주세요.",
  GENERATION_FAILED: "일정 생성이 중단됐어요. 잠시 후 다시 시도해 주세요.",
  GENERATION_STATUS_TIMEOUT: "일정 생성 상태를 아직 확인하지 못했어요. 같은 조건으로 다시 눌러 결과를 확인해 주세요.",
  GENERATION_REQUEST_NOT_FOUND: "확인할 수 있는 생성 요청이 없어요. 여행 조건 화면에서 다시 시도해 주세요.",
  VERIFICATION_FAILED: "방문 시간과 동선을 확인할 수 없어 일정을 완성하지 못했어요.",
  RATE_LIMITED: "요청이 많아요. 잠시 후 다시 시도해 주세요.",
  GENERATION_IN_PROGRESS: "이미 일정을 생성하고 있어요. 진행 중인 작업이 끝날 때까지 기다려 주세요.",
  DAILY_LIMIT_REACHED: "오늘 만들 수 있는 일정을 모두 생성했어요. 한국 시간 기준 내일 다시 이용해 주세요.",
  MONTHLY_LIMIT_REACHED: "이번 달에 만들 수 있는 일정을 모두 생성했어요. 다음 달에 다시 이용해 주세요.",
  BUDGET_EXHAUSTED: "이번 달에는 새 일정을 생성할 수 없어요. 기존 일정은 계속 볼 수 있어요.",
  PAYLOAD_TOO_LARGE: "요청 내용이 너무 커요. 여행 조건을 확인하고 다시 시도해 주세요.",
  EXTERNAL_DATA_UNAVAILABLE: "외부 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
  DATABASE_UNAVAILABLE: "저장소에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
  NETWORK_UNAVAILABLE: "서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.",
  REQUEST_FAILED: "요청을 완료하지 못했어요. 잠시 후 다시 시도해 주세요.",
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public generationLimit?: GenerationLimit,
  ) {
    super(Object.prototype.hasOwnProperty.call(alertMessages, code) ? alertMessages[code] : alertMessages.REQUEST_FAILED)
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retryPublic = false,
): Promise<T> {
  const headers = new Headers(init.headers)

  if (init.body) headers.set("Content-Type", "application/json")

  if (init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", csrfToken)

  let response: Response

  try {
    response = await fetch("/api" + path, {
      ...init,
      headers,
      credentials: "include",
    })
  } catch {
    throw new ApiError(0, "NETWORK_UNAVAILABLE")
  }

  if (!response.ok) {
    if (response.status === 401) {
      clearAuth()

      window.dispatchEvent(new Event("tripick-auth-expired"))

      if (retryPublic) return api<T>(path, init, false)
    }

    const body = await response.json().catch(() => ({}))

    const code = typeof body?.error?.code === "string" ? body.error.code : "REQUEST_FAILED"
    const quotaError = response.status === 429 && ["DAILY_LIMIT_REACHED", "MONTHLY_LIMIT_REACHED", "BUDGET_EXHAUSTED"].includes(code)
    throw new ApiError(response.status, code, quotaError ? { code, resetsAt: body.error.resetsAt ?? null } : undefined)
  }

  return response.status === 204 ? undefined as T : response.json()
}

export async function restoreAuth() {
  const value = await api<{ user: User; csrfToken: string }>("/auth/me")

  csrfToken = value.csrfToken

  return value.user
}

type Generation = {
  generationId: string
  status: "queued" | "running" | "completed" | "failed"
  draftId?: string
  error?: { code: string; details?: FailureDetails | null }
  progress?: GenerationProgress | null
}

export type GenerationProgress = {
  stage: "submitting" | "recovering" | "queued" | "running" | "planning" | "checking" | "scheduling" | "verifying" | "repairing" | "completed"
  percent?: number
  day?: number
}

type FailureDetails = { reason?: string; day?: number; slot?: string }

export class GenerationFailed extends ApiError {
  constructor(code: string, details?: FailureDetails | null) {
    super(0, code)
    if (!details || !["VERIFICATION_FAILED", "ROUTE_UNAVAILABLE"].includes(code)) return
    const { day, slot, reason } = details
    const prefix = typeof day === "number" && Number.isInteger(day) && day >= 1 && day <= 7 ? day + "일차 " : ""
    const meal = slot === "breakfast" ? "아침" : slot === "lunch" ? "점심" : slot === "dinner" ? "저녁" : ""
    const stop = meal ? meal + " 식당" : slot === "meal" ? "식당" : "방문지"
    if (reason === "no_visits") {
      this.message = "이번 여행에 넣을 수 있는 방문지를 찾지 못했어요. 다른 날짜나 취향으로 다시 시도해 주세요."
    } else if (reason === "hours_unknown" || reason === "closed") {
      this.message = meal ? `${prefix}${meal}에 영업을 확인할 수 있는 식당을 찾지 못했어요.`
        : `${prefix}방문 시간에 영업을 확인할 수 있는 ${slot === "meal" ? "식당을" : "방문지를"} 찾지 못했어요.`
    } else if (reason === "visit_window" || reason === "time_conflict") {
      this.message = `${prefix}${stop}의 영업시간과 이동시간을 함께 맞출 수 없었어요.`
    } else if (reason === "no_walk") {
      this.message = `${prefix}${stop}까지 이어지는 도보 경로를 확인하지 못했어요.`
    } else if (reason === "place_missing" || reason === "no_alternative") {
      this.message = `${prefix}${stop} 자리에 넣을 다른 장소를 확인하지 못했어요.`
    } else if (reason === "candidate_count" || reason === "day_count" || reason === "visit_times") {
      this.message = `${prefix}방문 순서와 시간을 완성하지 못했어요. 다시 시도해 주세요.`
    }
  }
}

export async function generateDraft(conditions: Conditions, key: string, signal: AbortSignal,
  onProgress?: (progress: GenerationProgress) => void, recoverOnly = false) {
  let job = recoverOnly
    ? await api<Generation>("/generation-requests/" + encodeURIComponent(key), { signal })
    : await api<Generation>("/generations", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(conditions),
      signal,
    })
  const deadline = Date.now() + 12 * 60_000
  let lastProgress: GenerationProgress = { stage: "running" }
  while (job.status === "queued" || job.status === "running") {
    signal.throwIfAborted()
    lastProgress = job.progress ?? lastProgress
    onProgress?.(job.status === "queued" ? { stage: "queued", percent: 0 } : lastProgress)
    if (Date.now() >= deadline) throw new ApiError(0, "GENERATION_STATUS_TIMEOUT")
    await new Promise(resolve => setTimeout(resolve, 2000))
    signal.throwIfAborted()
    job = await api<Generation>("/generations/" + job.generationId, { signal })
  }
  if (job.status !== "completed" || !job.draftId)
    throw new GenerationFailed(job.error?.code ?? "GENERATION_FAILED", job.error?.details)
  signal.throwIfAborted()
  onProgress?.({ stage: "completed", percent: 100 })
  return api<Trip>("/drafts/" + job.draftId, { signal })
}
