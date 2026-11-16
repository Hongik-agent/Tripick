import { useState } from "react"

import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
} from "react-simple-maps"

import type { TripSummary } from "./api"

export default function WorldMap({
  trips,
  onSelect,
  loggedIn,
}: {
  trips: TripSummary[]
  onSelect: (id: string) => void
  loggedIn: boolean
}) {
  const [position, setPosition] = useState<{
    coordinates: [number, number]
    zoom: number
  }>({ coordinates: [0, 0], zoom: 1 })

  const zoom = position.zoom

  const setZoom = (value: (z: number) => number) =>
    setPosition((p) => ({ ...p, zoom: value(p.zoom) }))

  return (
    <div className="world-map">
      <ComposableMap
        width={1000}
        height={440}
        projection="geoEqualEarth"
        projectionConfig={{ scale: 160 }}
        style={{ width: "100%", height: "100%" }}
        aria-label="저장한 여행 일정 세계지도"
      >
        <ZoomableGroup
          center={position.coordinates}
          zoom={zoom}
          minZoom={1}
          maxZoom={5}
          onMoveEnd={(p) =>
            setPosition({
              coordinates: p.coordinates ?? position.coordinates,
              zoom: p.zoom ?? 1,
            })
          }
        >
          <Geographies geography="/maps/countries-110m.json">
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  tabIndex={-1}
                  aria-hidden="true"
                  fill="#f9faf0"
                  stroke="#c7d8cd"
                  strokeWidth={0.5}
                />
              ))
            }
          </Geographies>
          {trips.map((trip, index) => (
            <Marker
              key={trip.id}
              coordinates={[
                trip.destination.mapCenter.longitude,
                trip.destination.mapCenter.latitude,
              ]}
            >
              <g
                role="button"
                tabIndex={0}
                aria-label={`${trip.destinationName} 저장 일정 열기`}
                onClick={() => onSelect(trip.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    onSelect(trip.id)
                  }
                }}
                style={{ cursor: "pointer" }}
              >
                <circle
                  r={7 / zoom}
                  fill="#248d7e"
                  stroke="white"
                  strokeWidth={2 / zoom}
                />
                <text
                  y={(-12 - index * 12) / zoom}
                  textAnchor="middle"
                  fontSize={12 / zoom}
                  fill="#264d42"
                  stroke="white"
                  strokeWidth={2 / zoom}
                  paintOrder="stroke"
                >
                  {trip.destinationName}
                </text>
              </g>
            </Marker>
          ))}
        </ZoomableGroup>
      </ComposableMap>
      <span className="map-caption">
        {loggedIn
          ? trips.length
            ? `저장한 일정 ${trips.length}개 · 핀을 눌러 확인하세요`
            : "아직 저장한 일정이 없어요"
          : "로그인하면 저장한 여행 일정이 지도에 표시돼요"}
      </span>
      <div className="map-controls">
        <button
          aria-label="세계지도 확대"
          onClick={() => setZoom((z) => Math.min(5, z + 0.5))}
        >
          +
        </button>
        <button
          aria-label="세계지도 축소"
          onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
        >
          −
        </button>
      </div>
      <span className="map-credit">Natural Earth · world-atlas</span>
    </div>
  )
}
