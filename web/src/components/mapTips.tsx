import { useEffect } from 'react'
import type { Layer } from 'leaflet'
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
