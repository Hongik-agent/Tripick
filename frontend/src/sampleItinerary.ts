export const sampleDistances = [153, 640, 320, 450, 240, 500]

export const sampleModes = [
  { label: "도보", icon: "🚶", minutes: [2, 9, 5, 6, 3, 7] },
  { label: "대중교통", icon: "🚇", minutes: [2, 6, 4, 5, 3, 5] },
  { label: "자동차", icon: "🚗", minutes: [1, 3, 2, 3, 2, 3] },
]

export function sampleStops(countryCode: string | undefined, day: number, days: number, pace: string) {
  const hongKong = countryCode === "HK" && day === 1
  const stops = [
    { name: hongKong ? "미드레벨 에스컬레이터" : `${day}일차 산책 코스`, visitTime: "10:00" },
    { name: hongKong ? "침차이키" : "점심 식당", visitTime: "12:00" },
    { name: hongKong ? "센트럴 마켓" : "전망 명소", visitTime: "14:00" },
  ]
  if (day > 1 && day < days) stops.unshift({ name: "아침 식당", visitTime: "08:00" })
  if (pace === "balanced" || pace === "packed") stops.push({ name: "전시관", visitTime: "15:30" })
  if (pace === "packed") stops.push({ name: "문화 거리", visitTime: "17:00" })
  stops.push({ name: "저녁 식당", visitTime: "18:30" })
  return stops.map((stop, i) => ({ ...stop, id: `sample-${day}-${i}` }))
}
