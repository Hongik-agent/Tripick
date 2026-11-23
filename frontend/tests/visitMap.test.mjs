import assert from "node:assert/strict"
import test from "node:test"
import { approximateDistance, drawVisits } from "../src/visitMap.ts"

test("formats nearby visit distances from both coordinates in metres", () => {
  const start = { latitude: 33.25, longitude: 126.56 }
  assert.equal(approximateDistance(start, { ...start, longitude: 126.5686 }), "약 800m")
  assert.equal(approximateDistance(start, { ...start, latitude: 33.261 }), "약 1,220m")
  assert.equal(approximateDistance(start, start), "10m 이내")
  assert.equal(approximateDistance(start, undefined), undefined)
  assert.equal(approximateDistance({ ...start, latitude: null }, start), undefined)
  assert.equal(approximateDistance(start, { ...start, longitude: 181 }), undefined)
})

test("numbers visits in list order, links selections and removes the previous day", (t) => {
  const pane = { children: [], append(element) { this.children.push(element) } }
  const document = { createElement: () => ({
    children: [], style: {}, attributes: {},
    append(child) { this.children.push(child) },
    setAttribute(name, value) { this.attributes[name] = value },
    remove() { pane.children = pane.children.filter(child => child !== this) },
  }) }
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document")
  Object.defineProperty(globalThis, "document", { value: document, configurable: true })
  t.after(() => {
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument)
    else delete globalThis.document
  })
  const map = { fitBounds: t.mock.fn(), panTo: t.mock.fn(), setOptions: t.mock.fn() }
  const lines = []
  const maps = {
    OverlayView: class {
      static preventMapHitsAndGesturesFrom() {}
      getPanes() { return { overlayMouseTarget: pane } }
      setMap(map) { if (map) this.onAdd(); else this.onRemove() }
    },
    LatLng: class {},
    LatLngBounds: class { extend() {} },
    Polyline: class {
      constructor(options) { this.options = options; lines.push(this) }
      setMap(map) { this.options.map = map }
    },
  }
  const overview = { center: { lat: 37, lng: 127 }, zoom: 12 }
  const item = (id, latitude) => ({ id, place: { name: id, latitude, longitude: 127 } })
  const onMarkerClick = t.mock.fn()
  const visits = [item("hotel-am", 37.1), item("park", 37.2), item("hotel-pm", 37.1)]
  const first = drawVisits(maps, map, visits, overview, onMarkerClick)
  assert.equal(map.fitBounds.mock.callCount(), 1)
  assert.deepEqual(lines[0].options.path, visits.map(({ place }) => ({ lat: place.latitude, lng: 127 })))
  const [hotel, park] = pane.children
  assert.deepEqual(hotel.children.map(button => button.textContent), ["1", "3"])
  assert.equal(park.children[0].textContent, "2")
  hotel.children[1].onclick()
  assert.deepEqual(onMarkerClick.mock.calls[0].arguments, ["hotel-pm"])
  first.select("hotel-pm")
  first.select("park")
  assert.equal(park.children[0].attributes["aria-pressed"], "true")
  assert.equal(hotel.children[1].attributes["aria-pressed"], "false")
  assert.deepEqual(map.panTo.mock.calls.at(-1).arguments, [{ lat: 37.2, lng: 127 }])
  first.remove()
  assert.equal(lines[0].options.map, null)
  assert.deepEqual(pane.children, [])

  const second = drawVisits(maps, map, [item("museum", 37.3)], overview, onMarkerClick)
  assert.equal(pane.children[0].children[0].textContent, "1")
  assert.equal(pane.children[0].children[0].attributes["aria-pressed"], "false")
  assert.deepEqual(map.setOptions.mock.calls.at(-1).arguments[0].center, { lat: 37.3, lng: 127 })
  second.remove()
  drawVisits(maps, map, [], overview, onMarkerClick).remove()
  assert.deepEqual(map.setOptions.mock.calls.at(-1).arguments, [overview])
  assert.equal(lines.length, 1)
  const gap = drawVisits(maps, map, [
    { ...item("start", 37.1), order: 1 }, { ...item("end", 37.3), order: 3 },
  ], overview, onMarkerClick)
  assert.equal(pane.children[1].children[0].textContent, "3")
  assert.equal(lines.length, 1, "a missing second stop must break the line")
  gap.remove()
})
