import type { Feature } from 'geojson'
import type { GeoJSON as LeafletGeoJSON, Layer, PathOptions } from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import { geoJSON as leafletGeoJSON } from 'leaflet'
import { GeoJSON, MapContainer, Pane, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import type { FieldFeature, FieldsResponse, Pred } from '../api'
import { classColor, num } from '../format'

const CENTER: [number, number] = [39.03, -76.9]
const ESRI_IMAGERY = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const ESRI_ATTRIBUTION = 'Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community'

interface Props {
  fields: FieldsResponse | null
  preds: Map<number, Pred>
  selectedId: number | null
  onSelect: (id: number) => void
  error: Error | null
}

function styleFor(f: FieldFeature, preds: Map<number, Pred>): PathOptions {
  const pred = preds.get(f.properties.OBJECTID)
  const label = f.properties.label
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

function tooltipHtml(f: FieldFeature, preds: Map<number, Pred>) {
  const p = preds.get(f.properties.OBJECTID)
  const label = f.properties.label ?? 'unlabeled'
  const call = p ? (p.p_silage == null ? p.class : `${p.class} · P(silage) ${num(p.p_silage)}`) : '—'
  return `<strong>Field ${f.properties.OBJECTID}</strong><br/>Label: ${label}<br/>Predicted: ${call}`
}

export function MapView({ fields, preds, selectedId, onSelect, error }: Props) {
  const geoRef = useRef<LeafletGeoJSON | null>(null)
  const predsRef = useRef(preds)
  const onSelectRef = useRef(onSelect)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  // Restyle in place when predictions change (as-of slider) instead of rebuilding the layer.
  useEffect(() => {
    predsRef.current = preds
    geoRef.current?.setStyle((f) => styleFor(f as FieldFeature, preds))
  }, [preds])

  const selected = useMemo(
    () => fields?.features.find((f) => f.properties.OBJECTID === selectedId) ?? null,
    [fields, selectedId],
  )

  const onEachFeature = (feature: Feature, layer: Layer) => {
    const f = feature as FieldFeature
    layer.on('click', () => onSelectRef.current(f.properties.OBJECTID))
    layer.bindTooltip(() => tooltipHtml(f, predsRef.current), { sticky: true, className: 'field-tip', direction: 'top', offset: [0, -8] })
  }

  return (
    <section className="map-wrap" aria-label="Map of BARC fields">
      <MapContainer center={CENTER} zoom={13} zoomSnap={0.25} zoomControl={false} className="map" attributionControl>
        <TileLayer url={ESRI_IMAGERY} attribution={ESRI_ATTRIBUTION} maxZoom={19} />
        <ZoomControl position="topright" />
        <FitToFields fields={fields} />
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
            key={fields.features.length}
            ref={geoRef}
            data={fields}
            style={(f) => styleFor(f as FieldFeature, predsRef.current)}
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

/** Frame the map on the fields so they fill the view instead of floating in a zoomed-out city. */
function FitToFields({ fields }: { fields: FieldsResponse | null }) {
  const map = useMap()
  const n = fields?.features.length ?? 0
  useEffect(() => {
    if (!fields || !n) return
    const b = leafletGeoJSON(fields).getBounds()
    if (!b.isValid()) return
    const phone = window.innerWidth <= 900
    map.invalidateSize()
    map.fitBounds(b, phone ? { padding: [12, 12] } : { paddingTopLeft: [40, 460], paddingBottomRight: [480, 80] })
  }, [map, n]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}
