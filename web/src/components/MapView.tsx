import type { Feature } from 'geojson'
import type { GeoJSON as LeafletGeoJSON, Layer, PathOptions } from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { geoJSON as leafletGeoJSON } from 'leaflet'
import { GeoJSON, MapContainer, Pane, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import { CloseTipsOnMove, HomeControl, oneTipAtATime } from './mapTips'
import type { FieldFeature, FieldLandcover, FieldsResponse, Pred, UnlabeledCallView } from '../api'
import { cdlText, classColor, noCallReason, num } from '../format'
import { fieldLayerKey } from '../adapter'

const CENTER: [number, number] = [39.03, -76.9]
const ESRI_IMAGERY = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const ESRI_ATTRIBUTION = 'Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community'

interface Props {
  fields: FieldsResponse | null
  preds: Map<number, Pred>
  /** season-end model calls on fields with no BARC label (CDL corn); drawn apart from labeled fields */
  unlabeled: Map<number, UnlabeledCallView>
  /** USDA Cropland Data Layer cover per field (land cover, not a label); shown in the tooltip */
  cover: Map<number, FieldLandcover>
  /** the selected date is Nov 30 (season-end calls on unlabeled corn fields exist only then) */
  seasonEnd: boolean
  selectedId: number | null
  onSelect: (id: number) => void
  error: Error | null
  /** changes whenever the panels over the map change, so the map re-frames the fields */
  layoutKey: string
}

function styleFor(f: FieldFeature, preds: Map<number, Pred>, unlabeled: Map<number, UnlabeledCallView>): PathOptions {
  const pred = preds.get(f.properties.OBJECTID)
  const label = f.properties.label
  const call = !label && !pred ? unlabeled.get(f.properties.OBJECTID) : undefined
  if (call) {
    // A model call with no label to check it against: light fill, dotted outline in the call's color.
    return { fillColor: classColor(call.label), fillOpacity: 0.3, color: classColor(call.label), weight: 2.25, opacity: 0.95, dashArray: '1 6', lineCap: 'round' }
  }
  const decided = pred?.class === 'Grain' || pred?.class === 'Silage'
  return {
    fillColor: classColor(pred?.class),
    fillOpacity: decided ? 0.62 : 0.32,
    color: label ? classColor(label) : '#ffffff',
    weight: label ? 3.5 : 1.25,
    opacity: label ? 1 : 0.75,
    dashArray: pred?.abstain ? '7 6' : undefined,
  }
}

function tooltipHtml(f: FieldFeature, preds: Map<number, Pred>, unlabeled: Map<number, UnlabeledCallView>, cover: Map<number, FieldLandcover>, seasonEnd: boolean) {
  const p = preds.get(f.properties.OBJECTID)
  const label = f.properties.label ?? 'none'
  const lc = cover.get(f.properties.OBJECTID)
  const land = lc ? `<br/><span class="field-tip__cdl">Land cover: ${cdlText(lc)}, USDA Cropland Data Layer</span>` : ''
  const u = !f.properties.label && !p ? unlabeled.get(f.properties.OBJECTID) : undefined
  if (u) return `<strong>Field ${f.properties.OBJECTID}</strong><br/>BARC label: none${land}<br/>Model call, no label: ${u.label} · P(silage) ${num(u.p_silage)}<br/><em>Season end; nothing to check it against</em>`
  const call = p ? (p.p_silage == null ? p.class : `${p.class} · P(silage) ${num(p.p_silage)}`) : (!f.properties.label ? noCallReason(lc, seasonEnd)?.short : undefined) ?? 'No call'
  return `<strong>Field ${f.properties.OBJECTID}</strong><br/>BARC label: ${label}<br/>Model: ${call}${land}`
}

export function MapView({ fields, preds, unlabeled, cover, seasonEnd, selectedId, onSelect, error, layoutKey }: Props) {
  const [home, setHome] = useState(0)  // bumped by the home button to re-fit the default view
  const geoRef = useRef<LeafletGeoJSON | null>(null)
  const predsRef = useRef(preds)
  const unlabeledRef = useRef(unlabeled)
  const coverRef = useRef(cover)
  const seasonEndRef = useRef(seasonEnd)
  useEffect(() => { coverRef.current = cover; seasonEndRef.current = seasonEnd }, [cover, seasonEnd])
  const onSelectRef = useRef(onSelect)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  // Restyle in place when predictions change (as-of slider) instead of rebuilding the layer.
  useEffect(() => {
    predsRef.current = preds
    unlabeledRef.current = unlabeled
    geoRef.current?.setStyle((f) => styleFor(f as FieldFeature, preds, unlabeled))
  }, [preds, unlabeled])

  const selected = useMemo(
    () => fields?.features.find((f) => f.properties.OBJECTID === selectedId) ?? null,
    [fields, selectedId],
  )

  const onEachFeature = (feature: Feature, layer: Layer) => {
    const f = feature as FieldFeature
    layer.on('click', () => onSelectRef.current(f.properties.OBJECTID))
    oneTipAtATime(layer)
    layer.bindTooltip(() => tooltipHtml(f, predsRef.current, unlabeledRef.current, coverRef.current, seasonEndRef.current), { sticky: true, className: 'field-tip', direction: 'top', offset: [0, -8] })
  }

  return (
    <section className="map-wrap" aria-label="Map of BARC fields">
      <MapContainer center={CENTER} zoom={13} zoomSnap={0.25} zoomControl={false} className="map" attributionControl>
        <TileLayer url={ESRI_IMAGERY} attribution={ESRI_ATTRIBUTION} maxZoom={19} />
        <ZoomControl position="bottomleft" />
        <CloseTipsOnMove />
        <HomeControl title="Reset view: all BARC fields" onHome={() => setHome((h) => h + 1)} />
        <FitToFields fields={fields} layoutKey={`${layoutKey}-${home}`} />
        <Pane name="halo" style={{ zIndex: 395 }}>
          {selected && (
            <GeoJSON
              key={`halo-${selected.properties.OBJECTID}`}
              data={selected}
              interactive={false}
              style={{ color: '#ffffff', weight: 10, opacity: 0.95, fill: false }}
            />
          )}
        </Pane>
        {fields && (
          <GeoJSON
            key={fieldLayerKey(fields)}
            ref={geoRef}
            data={fields}
            style={(f) => styleFor(f as FieldFeature, predsRef.current, unlabeledRef.current)}
            onEachFeature={onEachFeature}
          />
        )}
      </MapContainer>

      {error && (
        <div className="map-card map-error" role="alert">
          <strong>Can't load fields.</strong> {error.message}
        </div>
      )}
    </section>
  )
}

/**
 * Frame the fields in the part of the map no panel covers. Measures the panels that are open
 * (top bar, summary, right rail / sheet / drawer, map key) and re-fits whenever `layoutKey` changes.
 */
function FitToFields({ fields, layoutKey }: { fields: FieldsResponse | null; layoutKey: string }) {
  const map = useMap()
  const n = fields?.features.length ?? 0
  useEffect(() => {
    if (!fields || !n) return
    const b = leafletGeoJSON(fields).getBounds()
    if (!b.isValid()) return
    const fit = () => {
      map.invalidateSize()
      const box = map.getContainer().getBoundingClientRect()
      if (window.innerWidth <= 900) {
        map.fitBounds(b, { padding: [12, 12] })
        return
      }
      const rect = (sel: string) => document.querySelector(sel)?.getBoundingClientRect()
      const rightPanels = ['.rail', '.sheet', '.drawer'].map(rect).filter((r): r is DOMRect => !!r)
      const freeRight = rightPanels.length ? Math.min(...rightPanels.map((r) => r.left)) : box.right
      const tops = ['.topbar', '.lead'].map(rect).filter((r): r is DOMRect => !!r && r.left < freeRight)
      const freeTop = tops.length ? Math.max(...tops.map((r) => r.bottom)) : box.top
      const key = rect('.mapkey')
      const freeBottom = key && key.left < freeRight ? key.top : box.bottom
      const pad = 24
      map.fitBounds(b, {
        paddingTopLeft: [pad, freeTop - box.top + pad],
        paddingBottomRight: [box.right - freeRight + pad, box.bottom - freeBottom + pad],
        animate: true,
      })
    }
    const raf = requestAnimationFrame(fit)
    let timer = 0
    const onResize = () => { window.clearTimeout(timer); timer = window.setTimeout(fit, 200) }
    window.addEventListener('resize', onResize)
    return () => { cancelAnimationFrame(raf); window.clearTimeout(timer); window.removeEventListener('resize', onResize) }
  }, [map, n, layoutKey]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}
