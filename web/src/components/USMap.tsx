import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { Layer, PathOptions } from 'leaflet'
import { geoJSON as leafletGeoJSON } from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import { GeoJSON, MapContainer, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import { CloseTipsOnMove, oneTipAtATime } from './mapTips'
import type { Crop, StateRow } from './forecastTypes'
import { errorColor, fmtAcres, fmtPct } from './forecastFormat'

type StatesFC = FeatureCollection<Geometry, { name: string; fips: string }>

const BASE_DARK = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const BASE_LIGHT = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const ATTRIBUTION = 'Basemap &copy; Esri. State boundaries: US Census Bureau via us-atlas.'
// Contiguous US; Alaska and Hawaii grow little corn and none is scored.
const CONUS: [[number, number], [number, number]] = [[24.4, -124.8], [49.4, -66.9]]

interface Props {
  shapes: StatesFC | null
  rows: Map<string, StateRow>
  crop: Crop
  selected: string | null
  onSelect: (state: string) => void
  dark: boolean
  layoutKey: string
}

export function USMap({ shapes, rows, crop, selected, onSelect, dark, layoutKey }: Props) {
  const rowsRef = useRef(rows)
  const cropRef = useRef(crop)
  const selectRef = useRef(onSelect)
  rowsRef.current = rows
  cropRef.current = crop
  selectRef.current = onSelect

  const style = (f?: Feature): PathOptions => {
    const name = (f?.properties as { name?: string } | undefined)?.name ?? ''
    const cell = rowsRef.current.get(name)?.[cropRef.current]
    const scored = cell?.nass != null && cell.err != null
    return {
      fillColor: scored ? errorColor(cell!.err!) : '#6b7a74',
      fillOpacity: scored ? 0.78 : 0.18,
      color: name === selected ? '#ffffff' : 'rgba(255,255,255,0.55)',
      weight: name === selected ? 3 : 0.8,
    }
  }

  const onEachFeature = (f: Feature, layer: Layer) => {
    const name = (f.properties as { name: string }).name
    layer.on('click', () => selectRef.current(name))
    oneTipAtATime(layer)
    layer.bindTooltip(() => {
      const cell = rowsRef.current.get(name)?.[cropRef.current]
      const title = name.charAt(0) + name.slice(1).toLowerCase()
      if (!cell) return `<strong>${title}</strong><br/>No ${cropRef.current} estimate`
      const nass = cell.nass == null ? 'no NASS 2025 row' : `NASS ${fmtAcres(cell.nass)}`
      return `<strong>${title}</strong><br/>Ours ${fmtAcres(cell.est)} · ${nass}${cell.err == null ? '' : `<br/>Error ${fmtPct(cell.err)}`}`
    }, { sticky: true, className: 'field-tip', direction: 'top', offset: [0, -8] })
  }

  // restyle in place when the crop or selection changes
  const layerRef = useRef<ReturnType<typeof leafletGeoJSON> | null>(null)
  useEffect(() => {
    layerRef.current?.setStyle((f) => style(f as Feature))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crop, selected, rows])

  const key = useMemo(() => (shapes ? shapes.features.length : 0), [shapes])

  return (
    <section className="map-wrap" aria-label="Map of 2025 estimate error by state">
      <MapContainer bounds={CONUS} zoomSnap={0.25} zoomControl={false} className="map" attributionControl scrollWheelZoom>
        <TileLayer key={dark ? 'dark' : 'light'} url={dark ? BASE_DARK : BASE_LIGHT} attribution={ATTRIBUTION} maxZoom={10} />
        <ZoomControl position="bottomleft" />
        <CloseTipsOnMove />
        <FitUS layoutKey={layoutKey} />
        {shapes && <GeoJSON key={key} ref={(l) => { layerRef.current = l }} data={shapes} style={(f) => style(f as Feature)} onEachFeature={onEachFeature} />}
      </MapContainer>
    </section>
  )
}

/** Frame the contiguous US in the part of the map that no panel covers (same idea as the BARC map). */
function FitUS({ layoutKey }: { layoutKey: string }) {
  const map = useMap()
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      map.invalidateSize()
      const box = map.getContainer().getBoundingClientRect()
      if (window.innerWidth <= 900) {
        map.fitBounds(CONUS, { padding: [8, 8] })
        return
      }
      const rect = (sel: string) => document.querySelector(sel)?.getBoundingClientRect()
      const right = ['.rail', '.sheet', '.drawer'].map(rect).filter((r): r is DOMRect => !!r && r.width > 0)
      const freeRight = right.length ? Math.min(...right.map((r) => r.left)) : box.right
      const tops = ['.topbar', '.lead', '.subbar'].map(rect).filter((r): r is DOMRect => !!r && r.left < freeRight)
      const freeTop = tops.length ? Math.max(...tops.map((r) => r.bottom)) : box.top
      const key = rect('.mapkey')
      const freeBottom = key && key.left < freeRight ? key.top : box.bottom
      map.fitBounds(CONUS, {
        paddingTopLeft: [24, freeTop - box.top + 16],
        paddingBottomRight: [box.right - freeRight + 24, box.bottom - freeBottom + 16],
      })
    })
    return () => cancelAnimationFrame(raf)
  }, [map, layoutKey])
  return null
}
