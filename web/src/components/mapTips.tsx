import { useEffect, useRef } from 'react'
import type { Layer } from 'leaflet'
import { Control, DomEvent, DomUtil } from 'leaflet'
import { useMap } from 'react-leaflet'

type TipLayer = Layer & { closeTooltip?: () => void }

/** Only one tooltip at a time: hovering a shape closes any other shape's tooltip. */
export function oneTipAtATime(layer: Layer) {
  layer.on('mouseover', () => {
    const map = (layer as Layer & { _map?: { eachLayer: (fn: (l: TipLayer) => void) => void } })._map
    map?.eachLayer((other) => { if (other !== layer) other.closeTooltip?.() })
  })
  layer.on('click', () => (layer as TipLayer).closeTooltip?.())
}

/** Close every tooltip when the map pans or zooms (a re-fit moves shapes under a still cursor). */
export function CloseTipsOnMove() {
  const map = useMap()
  useEffect(() => {
    const close = () => map.eachLayer((l) => (l as TipLayer).closeTooltip?.())
    map.on('movestart zoomstart', close)
    return () => { map.off('movestart zoomstart', close) }
  }, [map])
  return null
}

const HOME_SVG = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 7.5L8 3l5.5 4.5"/><path d="M4 6.5V13h3v-3h2v3h3V6.5"/></svg>'

/** A home button above the zoom buttons: puts the map back to its default view (the caller decides what that is). */
export function HomeControl({ onHome, title }: { onHome: () => void; title: string }) {
  const map = useMap()
  const cb = useRef(onHome)
  cb.current = onHome
  useEffect(() => {
    const ctl = new Control({ position: 'bottomleft' })
    ctl.onAdd = () => {
      const div = DomUtil.create('div', 'leaflet-bar leaflet-control map-home')
      const a = DomUtil.create('a', '', div) as HTMLAnchorElement
      a.href = '#'
      a.title = title
      a.setAttribute('role', 'button')
      a.setAttribute('aria-label', title)
      a.innerHTML = HOME_SVG
      DomEvent.disableClickPropagation(div)
      DomEvent.on(a, 'click', (e) => { DomEvent.preventDefault(e); cb.current() })
      return div
    }
    ctl.addTo(map)
    return () => { ctl.remove() }
  }, [map, title])
  return null
}
