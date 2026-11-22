import { useEffect, useRef, useState } from "react"
import { drawVisits, type MapsApi, type MapVisit } from "./visitMap"

type MapsWindow = Window & {
  google?: { maps?: MapsApi }
  gm_authFailure?: () => void
  tripickMapsReady?: () => void
}

let mapsPromise: Promise<MapsApi> | undefined
let mapsAuthFailed = false

function loadGoogleMaps(key: string) {
  if (mapsAuthFailed)
    return Promise.reject(new Error("Google 지도 인증에 실패했습니다."))
  if (mapsPromise) return mapsPromise
  const mapsWindow = window as MapsWindow
  if (mapsWindow.google?.maps?.Map)
    return Promise.resolve(mapsWindow.google.maps)

  mapsPromise = new Promise<MapsApi>((resolve, reject) => {
    const script = document.createElement("script")
    const timeout = window.setTimeout(() => fail(), 15000)
    const fail = () => {
      window.clearTimeout(timeout)
      mapsPromise = undefined
      script.remove()
      window.dispatchEvent(new Event("tripick-maps-error"))
      reject(new Error("Google 지도를 불러오지 못했습니다."))
    }
    mapsWindow.gm_authFailure = () => {
      mapsAuthFailed = true
      fail()
    }
    mapsWindow.tripickMapsReady = () => {
      window.clearTimeout(timeout)
      const maps = mapsWindow.google?.maps
      if (maps?.Map) resolve(maps)
      else fail()
    }
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&callback=tripickMapsReady`
    script.async = true
    script.onerror = fail
    document.head.append(script)
  })
  return mapsPromise
}

export default function GoogleMap({
  center,
  zoom,
  label,
  items,
  selection,
  onSelect,
  onUnavailable,
}: {
  center: { latitude: number; longitude: number }
  zoom: number
  label: string
  items: MapVisit[]
  selection: { id: string } | null
  onSelect: (id: string) => void
  onUnavailable?: () => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState("")
  const [view, setView] = useState<{ maps: MapsApi; map: InstanceType<MapsApi["Map"]> } | null>(null)
  const layer = useRef<ReturnType<typeof drawVisits> | null>(null)
  useEffect(() => { if (error) onUnavailable?.() }, [error, onUnavailable])

  useEffect(() => {
    setError("")
    if (
      !Number.isFinite(center.latitude) ||
      !Number.isFinite(center.longitude)
    ) {
      setError("여행지 중심 좌표가 없습니다.")
      return
    }
    const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY
    if (!key) {
      setError("Google 지도 API 키가 설정되지 않았습니다.")
      return
    }

    let active = true
    const showError = () =>
      active && setError("Google 지도를 불러오지 못했습니다.")
    window.addEventListener("tripick-maps-error", showError)
    loadGoogleMaps(key)
      .then((maps) => {
        if (active && container.current) {
          const map = new maps.Map(container.current, {
            center: { lat: center.latitude, lng: center.longitude },
            zoom,
          })
          setView({ maps, map })
        }
      })
      .catch(showError)

    return () => {
      active = false
      window.removeEventListener("tripick-maps-error", showError)
    }
  }, [center.latitude, center.longitude, zoom])

  useEffect(() => {
    if (!view || error) return
    layer.current = drawVisits(view.maps, view.map, items, {
      center: { lat: center.latitude, lng: center.longitude }, zoom,
    }, onSelect)
    return () => {
      layer.current?.remove()
      layer.current = null
    }
  }, [view, error, items, center.latitude, center.longitude, zoom, onSelect])

  useEffect(() => {
    layer.current?.select(selection?.id)
  }, [selection, view, items])

  return error ? (
    <div
      className="grid h-full min-h-[470px] place-items-center p-6 text-center text-sm text-red-700"
      role="alert"
    >
      {error}
    </div>
  ) : (
    <div
      ref={container}
      className="visit-map-canvas"
      aria-label={`${label} 중심 Google 지도`}
    />
  )
}
