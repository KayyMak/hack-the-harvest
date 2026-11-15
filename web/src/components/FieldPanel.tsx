import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, parseTopFeatures } from '../api'
import type { FieldFeature, FieldLandcover, Pred, UnlabeledCallView } from '../api'
import { cdlText, classColor, featureName, noCallReason, monthOf, num, shortDate, toTime } from '../format'
import { useAsync } from '../hooks'
import { DATA, useTheme } from '../theme'
import { ChartTip, type TipProps, xTitle, yTitle } from './charts'
import { Pending } from './Pending'

export interface Shortcut {
  title: string
  ids: number[]
}

interface Props {
  shortcuts?: Shortcut[]
  onSelect?: (id: number) => void
  field: FieldFeature | null
  pred: Pred | undefined
  year: number
  asOf: string
  stub: boolean
  /** hide the before/after image block when no chips exist for this data */
  showChips?: boolean
  /** season-end model call on a field with no BARC label (CDL corn); shown apart from the prediction */
  unlabeledCall?: UnlabeledCallView
  /** USDA Cropland Data Layer cover for this field-year: land cover, never a BARC label */
  cover?: FieldLandcover
}

export function FieldPanel({ field, pred, year, asOf, stub, showChips = true, shortcuts = [], onSelect, unlabeledCall, cover }: Props) {
  if (!field) {
    return (
      <div className="empty">
        <div className="empty__art" aria-hidden>
          <span style={{ background: DATA.grain }} />
          <span style={{ background: DATA.silage }} />
        </div>
        <h3>Pick a field on the map</h3>
        <p>You'll see its greenness over the season, before/after imagery, and why the model called it silage or grain.</p>
        {shortcuts
          .filter((s) => s.ids.length)
          .map((s) => (
            <div key={s.title} className="shortcuts">
              <div className="eyebrow">{s.title}</div>
              <div className="shortcuts__row">
                {s.ids.map((id) => (
                  <button key={id} className="chip-btn" onClick={() => onSelect?.(id)}>
                    Field {id}
                  </button>
                ))}
              </div>
            </div>
          ))}
      </div>
    )
  }
  return <FieldDetail key={`${field.properties.OBJECTID}-${year}`} field={field} pred={pred} year={year} asOf={asOf} stub={stub} showChips={showChips} unlabeledCall={unlabeledCall} cover={cover} />
}

function FieldDetail({ field, pred, year, asOf, stub, showChips, unlabeledCall, cover }: Props & { field: FieldFeature }) {
  // Chips are picked from the full season; before Nov 30 they could show the future.
  const seasonEnd = asOf === `${year}-11-30`
  const id = field.properties.OBJECTID
  const label = field.properties.label
  const series = useAsync(() => api.series(id, year), [id, year])
  const decided = pred?.class === 'Grain' || pred?.class === 'Silage'
  const verdict = !label || !decided ? null : pred?.class === label
  // No label, no held-out prediction and no season-end call: say why from the Cropland Data Layer.
  const noCall = !label && !pred && !unlabeledCall
  const reason = noCall ? noCallReason(cover, seasonEnd) : null
  const missingLooks = `No clear satellite looks saved for this field in ${year}.`

  return (
    <div className="field">
      <header className="field__head">
        <div>
          <div className="eyebrow">Field · {year}</div>
          <h2 className="field__title">
            {id}
            {field.properties.ACRES != null && <span className="field__acres">{field.properties.ACRES} ac</span>}
          </h2>
        </div>
        <div className="field__badges">
          <Badge kicker="BARC label" text={label ?? 'Unlabeled'} color={label ? classColor(label) : undefined} outline />
          <Badge kicker={`Model · ${shortDate(asOf)}`} text={pred?.class === 'Pending' ? 'Pending (NA)' : pred?.class === 'Insufficient' ? 'Abstained (X)' : (pred?.class ?? (unlabeledCall && !label ? `${unlabeledCall.label} (no label)` : 'No call'))} color={decided ? classColor(pred?.class) : unlabeledCall && !label && !pred ? classColor(unlabeledCall.label) : undefined} />
          {verdict != null && <span className={`verdict ${verdict ? 'verdict--ok' : 'verdict--bad'}`}>{verdict ? '✓ Match' : '✗ Mismatch'}</span>}
        </div>
      </header>

      {reason ? (
        <section className="pbar pbar--empty nocall" aria-label="No model call">
          <div className="pbar__value">No call</div>
          <p>
            <span className="tag tag--cdl" title="USDA Cropland Data Layer: satellite land cover, not a BARC label or a model call">USDA Cropland Data Layer {year}</span> {reason.text}
          </p>
          <p className="muted small">BARC has no label for this field-year. The Cropland Data Layer is satellite land cover, not a BARC label or a model call.</p>
        </section>
      ) : (
        cover && (
          <p className="block__note cdl-note">
            <span className="tag tag--cdl" title="USDA Cropland Data Layer: satellite land cover, not a BARC label">USDA Cropland Data Layer</span> {cdlText(cover)}
          </p>
        )
      )}
      {/* An unlabeled call replaces the "no model call" bar: it is a call, just not a scored one. */}
      {!(unlabeledCall && !label && !pred) && !reason && <ProbabilityBar pred={pred} />}
      {unlabeledCall && !label && !pred && (
        <p className="block__note">
          <span className="tag">Model call, no label</span> {unlabeledCall.label}, P(silage) {num(unlabeledCall.p_silage)}, season end {year}.
          {' '}BARC did not label this field-year; the Cropland Data Layer shows it {Math.round(unlabeledCall.corn_share * 100)}% corn. There is no reference to check this call against.
        </p>
      )}

      <section className="block">
        <div className="block__head">
          <h3>Greenness and residue over the season</h3>
          {series.data?.decline_date && (
            <span className="block__note txt-flag">
              Decline {shortDate(series.data.decline_date)}
            </span>
          )}
        </div>
        {series.loading && <div className="skeleton skeleton--chart" />}
        {series.error && <p className="muted small">{missingLooks}</p>}
        {series.data && (series.data.points.some((p) => p.ndvi != null) ? <SeriesChart points={series.data.points} decline={series.data.decline_date} asOf={asOf} /> : <p className="muted small">{missingLooks}</p>)}
      </section>

      {!showChips && (
        <section className="block">
          <Pending title="Before and after images">Sentinel-2 true-color cutouts of this field from just before and just after its greenness drop.</Pending>
        </section>
      )}
      {showChips && !seasonEnd && (
        <section className="block">
          <div className="block__head"><h3>Before and after</h3></div>
          <p className="muted small">Shown on Nov 30: the images are picked from the whole season, so on {shortDate(asOf)} they could show later imagery.</p>
        </section>
      )}
      {showChips && seasonEnd && (
      <section className="block">
        <div className="block__head">
          <h3>Before and after</h3>
          {stub && <span className="tag tag--warn">Stub imagery</span>}
        </div>
        <div className="chips">
          <Chip src={api.chipUrl(id, year, 'pre')} caption="Before the season’s largest greenness drop" missing={missingLooks} />
          <Chip src={api.chipUrl(id, year, 'post')} caption="After that drop" missing={missingLooks} />
        </div>
      </section>
      )}

      <section className="block">
        <div className="block__head">
          <h3>Why the model decided</h3>
        </div>
        {pred ? (
          <Contributions raw={pred.top_features} />
        ) : (
          <p className="muted small">
            {reason ? reason.na : unlabeledCall && !label ? 'Signal breakdowns are saved for labeled field-years only.' : 'Not applicable: no model call for this field-year.'}
          </p>
        )}
      </section>
    </div>
  )
}

function Badge({ kicker, text, color, outline }: { kicker: string; text: string; color?: string; outline?: boolean }) {
  return (
    <div className="badge">
      <span className="badge__kicker">{kicker}</span>
      <span className="badge__text">
        <span
          className={`swatch ${outline ? 'swatch--outline' : 'swatch--fill'}`}
          style={outline ? { borderColor: color ?? DATA.undecided } : { background: color ?? DATA.undecided }}
        />
        {text}
      </span>
    </div>
  )
}

function ProbabilityBar({ pred }: { pred: Pred | undefined }) {
  const p = pred?.p_silage
  if (p == null) {
    const why =
      pred?.class === 'Insufficient'
        ? 'Too few clear satellite looks — the model abstains instead of guessing.'
        : !pred
          ? 'No model call for this field-year: BARC has no label to score it against.'
          : 'No harvest signal yet at this date — check a later as-of date.'
    return (
      <section className="pbar pbar--empty">
        <div className="pbar__value">{pred?.class === 'Pending' ? 'Pending (NA)' : pred?.class === 'Insufficient' ? 'Abstained (X)' : (pred?.class ?? '—')}</div>
        <p>{why}</p>
      </section>
    )
  }
  const color = p >= 0.5 ? DATA.silage : DATA.grain
  return (
    <section className="pbar" aria-label={`Probability of silage ${num(p)}`}>
      <div className="pbar__top">
        <span className="pbar__label">P(silage)</span>
        <span className="pbar__value" style={{ color }}>{num(p)}</span>
      </div>
      <div className="pbar__track">
        <div className="pbar__fill" style={{ width: `${p * 100}%`, background: color }} />
        <div className="pbar__mid" title="Decision threshold 0.5" />
      </div>
      <div className="pbar__ends">
        <span>0 · Grain</span>
        <span>0.5</span>
        <span>Silage · 1</span>
      </div>
    </section>
  )
}

function SeriesChart({ points, decline, asOf }: { points: { date: string; ndvi: number | null; ndti: number | null }[]; decline: string | null; asOf: string }) {
  const t = useTheme().chart
  const data = useMemo(() => points.map((p) => ({ ...p, t: toTime(p.date) })), [points])
  const ticks = useMemo(() => {
    if (!data.length) return []
    const first = new Date(data[0].t)
    const out: number[] = []
    for (let m = first.getUTCMonth() + 1; ; m++) {
      const tt = Date.UTC(first.getUTCFullYear(), m, 1)
      if (tt > data[data.length - 1].t) break
      out.push(tt)
    }
    return out
  }, [data])
  if (!data.length) return <p className="inline-error">No observations.</p>
  const asOfT = toTime(asOf)
  const lastT = data[data.length - 1].t
  return (
    <ResponsiveContainer width="100%" height={270}>
      <LineChart data={data} margin={{ top: 22, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={['dataMin', 'dataMax']}
          ticks={ticks}
          tickFormatter={monthOf}
          stroke={t.axis}
          tick={{ fill: t.muted, fontSize: 12 }}
          height={36}
          label={xTitle(`Satellite date, ${new Date(data[0].t).getUTCFullYear()}`, t.muted)}
        />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} stroke={t.axis} tick={{ fill: t.muted, fontSize: 12 }} width={58} label={yTitle('Index (0–1)', t.muted)} />
        {asOfT < lastT && (
          <ReferenceArea x1={asOfT} x2={lastT} fill={t.muted} fillOpacity={0.1} ifOverflow="hidden" label={{ value: 'after as-of', position: 'insideTopRight', fill: t.muted, fontSize: 13 }} />
        )}
        {decline && (
          <ReferenceLine
            x={toTime(decline)}
            stroke={t.flag ?? DATA.flag}
            strokeWidth={2}
            label={{ value: `decline ${shortDate(decline)}`, position: 'top', fill: t.flag ?? DATA.flag, fontSize: 13, fontWeight: 600 }}
          />
        )}
        <Tooltip
          content={(p) => <ChartTip {...(p as unknown as TipProps)} title={(l) => shortDate(new Date(Number(l)).toISOString())} value={(v) => v.toFixed(2)} />}
        />
        <Legend verticalAlign="top" height={28} iconType="plainline" wrapperStyle={{ fontSize: 13, color: t.ink, paddingBottom: 4 }} />
        <Line dataKey="ndvi" name="NDVI (greenness)" stroke={t.ndvi} strokeWidth={2} dot={false} activeDot={{ r: 5 }} connectNulls isAnimationActive={false} />
        {data.some((p) => p.ndti != null) && <Line dataKey="ndti" name="NDTI (residue)" stroke={DATA.ndti} strokeWidth={2} dot={false} activeDot={{ r: 5 }} connectNulls isAnimationActive={false} />}
      </LineChart>
    </ResponsiveContainer>
  )
}

function Chip({ src, caption, missing }: { src: string; caption: string; missing: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <figure className="chip">
      {failed ? <div className="chip__missing">{missing}</div> : <img src={src} alt={caption} onError={() => setFailed(true)} />}
      <figcaption>{caption}</figcaption>
    </figure>
  )
}

function Contributions({ raw }: { raw: string | undefined }) {
  const rows = useMemo(
    () =>
      parseTopFeatures(raw)
        .map((f) => ({ ...f, label: featureName(f.name) }))
        .sort((a, b) => Math.abs(b.contrib) - Math.abs(a.contrib)),
    [raw],
  )
  if (!rows.length) return <p className="muted small">No signal breakdown is saved for this call.</p>
  const m = Math.max(0.5, ...rows.map((r) => Math.abs(r.contrib)))
  return (
    <div className="contrib" role="table" aria-label="Feature contributions; negative pushes toward grain, positive toward silage">
      {rows.map((r) => {
        const w = `${(Math.abs(r.contrib) / m) * 50}%`
        const toSilage = r.contrib >= 0
        return (
          <div className="contrib__row" role="row" key={r.name} title={`value ${num(r.value)}`}>
            <span className="contrib__label" role="rowheader">{r.label}</span>
            <span className="contrib__track" role="cell" aria-hidden="true">
              <span className="contrib__axis" />
              <span
                className="contrib__bar"
                style={toSilage ? { left: '50%', width: w, background: DATA.silage } : { right: '50%', width: w, background: DATA.grain }}
              />
            </span>
            <span className="contrib__val" role="cell">
              {toSilage ? '+' : '−'}
              {Math.abs(r.contrib).toFixed(2)}
            </span>
          </div>
        )
      })}
      <div className="contrib__row contrib__dir" aria-hidden="true">
        <span />
        <span className="contrib__ends">
          <span className="txt-grain">◀ Grain</span>
          <span className="contrib__zero">0</span>
          <span className="txt-silage">Silage ▶</span>
        </span>
        <span />
      </div>
    </div>
  )
}
