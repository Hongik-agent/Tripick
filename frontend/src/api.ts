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
    withChildren: boolean
    withSeniors: boolean
  }
  interestIds: string[]
  paceId: string
  transportMode: string
  mapProvider: string
}

export type Item = {
  id: string
  order: number
  place: { name: string; latitude: number; longitude: number }
  startTime: string
  endTime: string
}

export type Day = {
  day: number
  items: Item[]
  legs: { durationMinutes: number; distanceMeters: number; status: string }[]
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
  id: string
  version: number
  destination: Destination
  conditions: Conditions
  days: Day[]
  publishedPostId: string | null
}

export type Post = {
  id: string
  authorNickname: string
  destinationName: string
  destination: Destination
  dayCount: number
  theme: string
  places: {
    mapPlaceId: string
    day: number
    order: number
    name: string
    latitude: number
    longitude: number
  }[]
  heartCount: number
  heartedByMe: boolean
  publishedAt: string
}

export type User = { id: string; email: string | null; nickname: string | null }

let csrfToken = ""

export function clearAuth() {
  csrfToken = ""
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
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
    throw new Error(
      "서버에 연결하지 못했어요. 입력 내용은 그대로 남아 있습니다.",
    )
  }

  if (!response.ok) {
    if (response.status === 401) {
      clearAuth()

      window.dispatchEvent(new Event("tripick-auth-expired"))

      if (retryPublic) return api<T>(path, init, false)
    }

    const body = await response.json().catch(() => ({}))

    throw new ApiError(
      response.status,
      body.error?.code ?? "REQUEST_FAILED",
      body.error?.message ?? "요청을 완료하지 못했어요.",
    )
  }

  return response.status === 204 ? undefined as T : response.json()
}

export async function restoreAuth() {
  const value = await api<{ user: User; csrfToken: string }>("/auth/me")

  csrfToken = value.csrfToken

  return value.user
}
