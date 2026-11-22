import { useEffect, useMemo, useState, type RefObject } from "react"
import { api, type Destination } from "./api"
import type { MapVisit } from "./visitMap"

type DayMap = { available: true; center: Destination["mapCenter"]; zoom: number; items: MapVisit[] }
type Result = DayMap | { available: false }

export function usePublicDayMap(postId: string | undefined, day: number, panel: RefObject<HTMLElement | null>) {
  const [visiblePost, setVisiblePost] = useState("")
  const cache = useMemo(() => ({
    requests: new Map<number, Promise<Result>>(), days: new Map<number, Result>(),
  }), [postId])
  const [, refresh] = useState(0)
  useEffect(() => {
    if (!postId || !panel.current) return
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      setVisiblePost(postId)
      observer.disconnect()
    })
    observer.observe(panel.current)
    return () => { observer.disconnect(); setVisiblePost("") }
  }, [postId, panel])

  useEffect(() => {
    if (!postId || visiblePost !== postId || cache.days.has(day)) return
    let active = true
    let request = cache.requests.get(day)
    if (!request) {
      request = api<Result>(`/posts/${encodeURIComponent(postId)}/map?day=${day}`)
        .catch((): Result => ({ available: false }))
        .then(result => { cache.days.set(day, result); return result })
      cache.requests.set(day, request)
    }
    request.then(() => { if (active) refresh(n => n + 1) })
    return () => { active = false }
  }, [cache, postId, day, visiblePost])

  const result = cache.days.get(day)
  const overview = Array.from(cache.days.values()).find((r): r is DayMap => r.available && r.items.length > 0)
  return { result, overview }
}
