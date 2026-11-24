import { useCallback, useEffect, useRef, useState } from "react"
import { api, type GenerationLimit } from "./api"

export function useGenerationLimit(modelId?: string) {
  // undefined는 최초 조회 중, null은 서버에 생성 요청을 보낼 수 있는 상태다.
  const [limit, setLimit] = useState<GenerationLimit | null>()
  const request = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    if (!modelId) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    try {
      const { limit } = await api<{ limit: GenerationLimit | null }>(
        "/generation-limit?modelId=" + encodeURIComponent(modelId),
        { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]) },
      )
      if (!controller.signal.aborted) setLimit(limit)
    } catch {
      // 안내 조회 실패는 생성 요청을 막지 않는다. 접수 시 서버가 다시 검사한다.
      if (!controller.signal.aborted) setLimit(null)
    }
  }, [modelId])

  useEffect(() => {
    setLimit(undefined)
    if (!modelId) return
    void refresh()
    return () => request.current?.abort()
  }, [modelId, refresh])

  useEffect(() => {
    if (!modelId || !limit) return
    // 월 제한은 브라우저 타이머의 최장 지연(약 25일)을 넘을 수 있다.
    const delay = limit.resetsAt ? Math.min(2_147_483_647, Math.max(1000, Date.parse(limit.resetsAt) - Date.now())) : 60_000
    const timer = window.setTimeout(refresh, delay)
    return () => window.clearTimeout(timer)
  }, [modelId, limit, refresh])

  function applyLimit(limit: GenerationLimit) {
    request.current?.abort()
    setLimit(limit)
  }

  return { limit, refresh, applyLimit }
}
