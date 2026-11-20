export const sampleDistances = [153, 640]

export const sampleModes = [
  { label: "도보", icon: "🚶", minutes: [2, 9] },
  { label: "대중교통", icon: "🚇", minutes: [2, 6] },
  { label: "자동차", icon: "🚗", minutes: [1, 3] },
]

export function sampleStops(countryCode: string | undefined, day: number) {
  const sampleNames =
    countryCode === "HK" && day === 1
      ? ["미드레벨 에스컬레이터", "침차이키", "센트럴 마켓"]
      : [`${day}일차 산책 코스`, "현지 식당", "전망 명소"]

  return sampleNames.map((name, i) => ({
        id: `sample-${day}-${i}`,
        name,
        visitTime: ["10:00", "12:00", "14:00"][i],
      }))
}
