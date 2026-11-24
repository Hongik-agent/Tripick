import assert from "node:assert/strict"
import test from "node:test"
import { generateDraft, GenerationFailed, generationLimitMessage } from "../src/api.ts"

const conditions = {
  modelId: "gpt-6.1-terra", destinationId: "kr-jeju", optionsVersion: "v1",
  startDate: "2027-01-10", endDate: "2027-01-13", party: { typeId: "solo", sizeBand: "1" },
  interestIds: ["food"], paceId: "relaxed", transportMode: "walking", mapProvider: "google",
}

test("a quota rejection carries the same reset time as the preflight notice", async (t) => {
  const limit = { code: "MONTHLY_LIMIT_REACHED", resetsAt: "2026-12-31T15:00:00Z" }
  t.mock.method(globalThis, "fetch", async () => Response.json({ error: limit }, { status: 429 }))
  await assert.rejects(generateDraft(conditions, "request1", new AbortController().signal), err => {
    assert.deepEqual(err.generationLimit, limit)
    assert.match(generationLimitMessage(err.generationLimit), /이번 달.*1월 1일.*00:00\(한국 시간\)/)
    return true
  })
})

test("submits the selected conditions once and opens the completed draft", async (t) => {
  const draft = { id: "draft1", days: [{ day: 1, items: [{ id: "visit1" }] }] }
  const responses = [
    { generationId: "job1", status: "queued" },
    { generationId: "job1", status: "running", progress: { stage: "checking", percent: 30, day: 3 } },
    { generationId: "job1", status: "running", progress: null },
    { generationId: "job1", status: "completed", draftId: draft.id },
    draft,
  ]
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json(responses.shift()))
  const progress = []
  assert.deepEqual(await generateDraft(conditions, "request1", new AbortController().signal, p => progress.push(p)), draft)
  assert.deepEqual(progress, [
    { stage: "queued", percent: 0 }, { stage: "checking", percent: 30, day: 3 },
    { stage: "checking", percent: 30, day: 3 }, { stage: "completed", percent: 100 },
  ])
  assert.deepEqual(fetch.mock.calls.map(({ arguments: [path] }) => path), [
    "/api/generations", "/api/generations/job1", "/api/generations/job1", "/api/generations/job1", "/api/drafts/draft1",
  ])
  const [, request] = fetch.mock.calls[0].arguments
  assert.equal(request.method, "POST")
  assert.equal(request.headers.get("Idempotency-Key"), "request1")
  assert.deepEqual(JSON.parse(request.body), conditions)
})

test("checking a lost response retrieves the original draft without submitting again", async (t) => {
  const signal = new AbortController().signal
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("offline") })
  await assert.rejects(generateDraft(conditions, "request1", signal), { code: "NETWORK_UNAVAILABLE" })
  const results = [{ generationId: "job1", status: "completed", draftId: "draft1" }, { id: "draft1" }]
  fetch.mock.mockImplementation(async () => Response.json(results.shift()))
  assert.deepEqual(await generateDraft(conditions, "request1", signal, undefined, true), { id: "draft1" })
  assert.deepEqual(fetch.mock.calls.map(({ arguments: [path, init] }) => [init.method ?? "GET", path]), [
    ["POST", "/api/generations"], ["GET", "/api/generation-requests/request1"], ["GET", "/api/drafts/draft1"],
  ])
})

test("a failed verification surfaces its Korean alert and never opens a draft", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({
    generationId: "job1", status: "failed", error: { code: "VERIFICATION_FAILED",
      details: { reason: "no_visits" } },
  }))
  await assert.rejects(generateDraft(conditions, "request1", new AbortController().signal),
    (err) => err instanceof GenerationFailed &&
      err.message === "이번 여행에 넣을 수 있는 방문지를 찾지 못했어요. 다른 날짜나 취향으로 다시 시도해 주세요.")
  assert.equal(fetch.mock.callCount(), 1)
})
