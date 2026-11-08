import { useEffect, useRef, useState } from "react"

type GoogleMap = new (
  element: HTMLElement,
  options: { center: { lat: number; lng: number }; zoom: number },
) => object

type MapsWindow = Window & {
  google?: { maps?: { Map: GoogleMap } }
  gm_authFailure?: () => void
  tripickMapsReady?: () => void
}

let mapsPromise: Promise<GoogleMap> | undefined
let mapsAuthFailed = false

function loadGoogleMaps(key: string) {
  if (mapsAuthFailed) return Promise.reject(new Error("Google 지도 인증에 실패했습니다."))
  if (mapsPromise) return mapsPromise
  const mapsWindow = window as MapsWindow
  if (mapsWindow.google?.maps?.Map) return Promise.resolve(mapsWindow.google.maps.Map)

  mapsPromise = new Promise<GoogleMap>((resolve, reject) => {
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
      const Map = mapsWindow.google?.maps?.Map
      if (Map) resolve(Map)
      else fail()
    }
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&callback=tripickMapsReady`
    script.async = true
    script.onerror = fail
    document.head.append(script)
  })
  return mapsPromise
}

export default function GoogleSeoulMap() {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY
    if (!key) {
      setError("Google 지도 API 키가 설정되지 않았습니다.")
      return
    }

    let active = true
    const showError = () => active && setError("Google 지도를 불러오지 못했습니다.")
    window.addEventListener("tripick-maps-error", showError)
    loadGoogleMaps(key)
      .then((Map) => {
        if (active && container.current) {
          new Map(container.current, {
            center: { lat: 37.5665, lng: 126.978 },
            zoom: 12,
          })
        }
      })
      .catch(showError)

    return () => {
      active = false
      window.removeEventListener("tripick-maps-error", showError)
    }
  }, [])

  return error ? (
    <div className="grid h-full min-h-[470px] place-items-center p-6 text-center text-sm text-red-700" role="alert">
      {error}
    </div>
  ) : (
    <div ref={container} className="h-full min-h-[470px] w-full" aria-label="서울 중심 Google 지도" />
  )
}
