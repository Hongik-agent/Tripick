import type { Item } from "./api"

type Point = { lat: number; lng: number }
type MapOptions = { center: Point; zoom: number }
type Bounds = { extend(point: Point): void }
type VisitMap = {
  setOptions(options: MapOptions): void
  fitBounds(bounds: Bounds, padding: number): void
  panTo(point: Point): void
}

type Overlay = {
  setMap(map: VisitMap | null): void
  getPanes(): { overlayMouseTarget: HTMLElement } | null
  getProjection(): { fromLatLngToDivPixel(position: object): { x: number; y: number } | null }
}

export type MapsApi = {
  Map: new (element: HTMLElement, options: MapOptions) => VisitMap
  LatLngBounds: new () => Bounds
  LatLng: new (lat: number, lng: number) => object
  OverlayView: (new () => Overlay) & { preventMapHitsAndGesturesFrom(element: HTMLElement): void }
  Polyline: new (options: {
    map: VisitMap; path: Point[]; strokeColor: string; strokeWeight: number; clickable: boolean
  }) => { setMap(map: VisitMap | null): void }
}

export function drawVisits(maps: MapsApi, map: VisitMap, items: Item[], overview: MapOptions,
  onSelect: (id: string) => void) {
  const path: Point[] = []
  const groups = new Map<string, { point: Point; pins: HTMLDivElement }>()
  const visits = new Map<string, { button: HTMLButtonElement; point: Point }>()
  items.forEach(({ id, place }, index) => {
    const point = { lat: place.latitude, lng: place.longitude }
    if (!Number.isFinite(point.lat) || !Number.isFinite(point.lng)) return
    path.push(point)
    const key = `${point.lat},${point.lng}`
    let group = groups.get(key)
    if (!group) {
      group = { point, pins: document.createElement("div") }
      group.pins.className = "visit-pins"
      groups.set(key, group)
    }
    const button = document.createElement("button")
    button.type = "button"
    button.textContent = String(index + 1)
    button.setAttribute("aria-label", `${index + 1}. ${place.name}`)
    button.setAttribute("aria-pressed", "false")
    button.onclick = () => onSelect(id)
    group.pins.append(button)
    visits.set(id, { button, point })
  })

  const overlays = Array.from(groups.values(), ({ point, pins }) => {
    const position = new maps.LatLng(point.lat, point.lng)
    const overlay = new class extends maps.OverlayView {
      onAdd() {
        this.getPanes()?.overlayMouseTarget.append(pins)
        maps.OverlayView.preventMapHitsAndGesturesFrom(pins)
      }
      draw() {
        const pixel = this.getProjection().fromLatLngToDivPixel(position)
        if (pixel) {
          pins.style.left = pixel.x + "px"
          pins.style.top = pixel.y + "px"
        }
      }
      onRemove() { pins.remove() }
    }()
    overlay.setMap(map)
    return overlay
  })
  const line = path.length > 1 ? new maps.Polyline({
    map, path, strokeColor: "#21796e", strokeWeight: 3, clickable: false,
  }) : null
  if (groups.size > 1) {
    const bounds = new maps.LatLngBounds()
    path.forEach(point => bounds.extend(point))
    map.fitBounds(bounds, 48)
  } else {
    map.setOptions({ ...overview, center: path[0] ?? overview.center })
  }

  return {
    select(id?: string) {
      visits.forEach(({ button }, visitId) => {
        button.setAttribute("aria-pressed", String(visitId === id))
      })
      const visit = id && visits.get(id)
      if (visit) map.panTo(visit.point)
    },
    remove() {
      overlays.forEach(overlay => overlay.setMap(null))
      line?.setMap(null)
    },
  }
}
