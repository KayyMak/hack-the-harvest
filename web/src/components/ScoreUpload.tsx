import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, DragEvent } from 'react'
import { ScoreError, scoreUpload } from '../score'
import type { Comparison, CropUse, Rejected, UploadScore } from '../score'
import type { Crop, Forecast } from './forecastTypes'
import { fmtFull, fmtPct, titleCase } from './forecastFormat'

/* Inline styles only (currentColor-based), so the box follows the panel's light or dark ink. */
const tint = (pct: number) => `color-mix(in srgb, currentColor ${pct}%, transparent)`
const S: Record<string, CSSProperties> = {
  box: { border: `1px solid ${tint(16)}`, borderRadius: 14, padding: 14, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 },
  note: { margin: 0 },
  muted: { opacity: 0.72, fontSize: 13 },
  drop: { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10, padding: '12px 12px', borderRadius: 10, border: `1.5px dashed ${tint(30)}` },
  dropOver: { borderStyle: 'solid', borderColor: tint(60), background: tint(8) },
  hiddenInput: { position: 'absolute', width: 1, height: 1, opacity: 0, overflow: 'hidden', pointerEvents: 'none' },
  tiles: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 },
  tile: { borderRadius: 10, padding: '9px 10px', background: tint(6), minWidth: 0 },
  big: { fontSize: 17, fontWeight: 600, marginTop: 2, whiteSpace: 'nowrap' },
  line: { margin: 0, fontSize: 14 },
  cropBtn: { border: `1px solid ${tint(22)}`, background: 'none', color: 'inherit', font: 'inherit', fontSize: 13, padding: '3px 10px', cursor: 'pointer' },
  cropOn: { background: tint(16), fontWeight: 600 },
  table: { fontSize: 12.5 },
  cell: { padding: '6px 5px' },
  pill: { marginLeft: 0, padding: '1px 4px', fontSize: 11.5 },
  scroll: { maxHeight: 320, overflow: 'auto' },
  list: { margin: '6px 0 0', paddingLeft: 18, fontSize: 12.5, maxHeight: 180, overflow: 'auto' },
}

const MAX_BYTES = 50 * 1024 * 1024
const CROP_OF: Record<Crop, CropUse> = { grain: 'Grain', silage: 'Silage' }

const signedAcres = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmtFull(Math.abs(x))}`

function ErrPct({ err }: { err: number | null }) {
  if (err == null) return <span>—</span>
  return <span className={`errtag ${Math.abs(err) <= 0.1 ? 'is-good' : 'is-off'}`} style={S.pill}>{fmtPct(err)}</span>
}

/** Why a row in the judge's file has no error. */
function notScored(c: Comparison): string {
  switch (c.status) {
    case 'missing_prediction': return 'no forecast of ours for this row'
    case 'reference_unknown': return `NASS value ${c.referenceUnknownCode === 'blank' ? 'blank' : c.referenceUnknownCode}: unknown, not scored`
    case 'prediction_unknown': return 'our value is missing'
    case 'duplicate': return 'appears more than once; not scored'
    default: return 'not in your file'
  }
}

/** Drop a NASS Quick Stats export and see the submitted 2025 forecast scored against it, in the browser. */
export function ScoreUpload({ data, crop }: { data: Forecast; crop?: Crop }) {
  const [file, setFile] = useState<{ name: string; text: string } | null>(null)
  const [readError, setReadError] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLElement>(null)

  const outcome = useMemo((): { score: UploadScore } | { error: string } | null => {
    if (!file) return null
    try {
      return { score: scoreUpload(file.text, data) }
    } catch (e) {
      if (e instanceof ScoreError) {
        return { error: `${e.message} It does not look like a NASS Quick Stats CSV export, which has the columns ${['Year', 'Geo Level', 'State', 'Data Item', 'Domain', 'Value'].join(', ')}.` }
      }
      return { error: `Could not score ${file.name}: ${e instanceof Error ? e.message : String(e)}` }
    }
  }, [file, data])

  useEffect(() => {
    if (outcome && 'score' in outcome) box.current?.scrollIntoView({ block: 'start' })
  }, [outcome])

  async function read(f: File | undefined) {
    if (!f) return
    setReadError(null)
    if (f.size > MAX_BYTES) {
      setFile(null)
      setReadError(`${f.name} is ${(f.size / 1e6).toFixed(0)} MB; a Quick Stats export of these rows is far smaller. Export only corn acres harvested.`)
      return
    }
    try {
      setFile({ name: f.name, text: await f.text() })
    } catch (e) {
      setFile(null)
      setReadError(`Could not read ${f.name}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const onDrag = (e: DragEvent, on: boolean) => {
    e.preventDefault()
    setOver(on)
  }
  const error = readError ?? (outcome && 'error' in outcome ? outcome.error : null)
  const score = outcome && 'score' in outcome ? outcome.score : null

  return (
    <section
      ref={box}
      aria-label="Score against your NASS file"
      style={S.box}
      onDragOver={(e) => onDrag(e, true)}
      onDragEnter={(e) => onDrag(e, true)}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false) }}
      onDrop={(e) => { onDrag(e, false); void read(e.dataTransfer.files?.[0]) }}
    >
      <h2 className="rail__title">Score against your NASS file</h2>
      <p className="rail__note rail__note--keep" style={S.note}>
        Drop the QuickStats CSV export (corn for grain/silage, acres harvested, 2025). Nothing is uploaded; it is read in your browser.
      </p>
      <div style={{ ...S.drop, ...(over ? S.dropOver : null) }}>
        <button type="button" className="ghost-btn" style={{ flex: 'none', whiteSpace: 'nowrap' }} onClick={() => input.current?.click()}>Choose CSV</button>
        <span className="rail__note rail__note--keep" style={S.note}>{file ? file.name : 'or drop it here'}</span>
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          aria-label="NASS Quick Stats CSV file"
          tabIndex={-1}
          style={S.hiddenInput}
          onChange={(e) => { void read(e.target.files?.[0]); e.target.value = '' }}
        />
      </div>

      <div aria-live="polite">
        {error && <p role="alert" className="txt-flag" style={S.line}>{error}</p>}
        {score && score.referenceRows === 0 && (
          <>
            <p role="alert" className="txt-flag" style={S.line}>
              No 2025 CORN, GRAIN or SILAGE - ACRES HARVESTED rows (Geo Level STATE or NATIONAL, Domain TOTAL) in this file, so nothing was scored.
            </p>
            <Ignored rows={score.ignored} />
          </>
        )}
        {score && score.referenceRows > 0 && <Results score={score} crop={crop} />}
      </div>
    </section>
  )
}

function Results({ score, crop }: { score: UploadScore; crop?: Crop }) {
  const counts = score.report.statusCounts
  const unscored = score.report.comparisons.filter((c) => c.referenceLines.length > 0 && c.status !== 'scored')
  const notInFile = counts.unmatched_prediction
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p style={S.line}>
        <strong>{counts.scored} rows matched</strong>{' '}
        <span style={S.muted}>
          of {score.rowsRead} read; {unscored.length} not scored; {score.ignored.length} ignored{notInFile ? `; ${notInFile} of our rows not in your file` : ''}.
        </span>
      </p>

      <div style={S.tiles}>
        <Tile label="US grain" c={score.us.Grain} />
        <Tile label="US silage" c={score.us.Silage} />
        <Tile label="Maryland grain" c={score.maryland.Grain} />
        <Tile label="Maryland silage" c={score.maryland.Silage} />
      </div>

      <p style={S.line}>
        States within 10%: grain <strong>{score.tally.Grain.within10} of {score.tally.Grain.states}</strong>, silage{' '}
        <strong>{score.tally.Silage.within10} of {score.tally.Silage.states}</strong>
      </p>
      <p style={S.line}>
        Mean absolute % error by state <span style={S.muted}>(unweighted)</span>:
        grain <strong>{pctAbs(score.tally.Grain.meanAbsPctError)}</strong>, silage <strong>{pctAbs(score.tally.Silage.meanAbsPctError)}</strong>
      </p>

      <StateScores rows={score.states} initial={crop ? CROP_OF[crop] : 'Silage'} />

      {unscored.length > 0 && (
        <details>
          <summary className="rail__note rail__note--keep" style={{ ...S.note, cursor: 'pointer' }}>{unscored.length} {unscored.length === 1 ? 'row' : 'rows'} in your file not scored</summary>
          <ul style={S.list}>
            {unscored.map((c) => (
              <li key={`${c.geography}-${c.cropUse}`}>{titleCase(c.geography)} {c.cropUse.toLowerCase()}: {notScored(c)}</li>
            ))}
          </ul>
        </details>
      )}
      <Ignored rows={score.ignored} />
    </div>
  )
}

const pctAbs = (x: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

function Tile({ label, c }: { label: string; c: Comparison | null }) {
  return (
    <div style={S.tile}>
      <div className="kpi__label">{label}</div>
      {!c ? (
        <div className="kpi__sub">not in your file</div>
      ) : c.status !== 'scored' || c.signedError == null ? (
        <div className="kpi__sub">{notScored(c)}</div>
      ) : (
        <>
          <div style={S.big}>{signedAcres(c.signedError)} <span style={{ fontSize: 13, fontWeight: 500 }}>ac</span></div>
          <div><ErrPct err={c.relativeError} /></div>
          <div className="kpi__sub" style={{ marginTop: 4 }}>ours {fmtFull(c.predictionValue)}</div>
          <div className="kpi__sub" style={{ marginTop: 0 }}>NASS {fmtFull(c.referenceValue)}</div>
        </>
      )}
    </div>
  )
}

type SortKey = 'state' | 'ours' | 'nass' | 'err'

function StateScores({ rows, initial }: { rows: Comparison[]; initial: CropUse }) {
  const [crop, setCrop] = useState<CropUse>(initial)
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'err', dir: -1 })
  const shown = useMemo(() => {
    const val = (c: Comparison, k: SortKey): number | string =>
      k === 'state' ? c.geography : k === 'ours' ? c.predictionValue ?? -1 : k === 'nass' ? c.referenceValue ?? -1 : Math.abs(c.relativeError ?? -1)
    return rows.filter((c) => c.cropUse === crop).sort((a, b) => {
      const x = val(a, sort.key)
      const y = val(b, sort.key)
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir || (a.geography < b.geography ? -1 : 1)
    })
  }, [rows, crop, sort])
  const head = (k: SortKey, label: string, num = true) => (
    <th className={num ? 'is-num' : undefined} aria-sort={sort.key === k ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button type="button" style={S.cell} onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? ((-s.dir) as 1 | -1) : k === 'state' ? 1 : -1 }))}>
        {label}
        <span aria-hidden="true" className="sort">{sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
      </button>
    </th>
  )
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>Every matched state</span>
        <span role="group" aria-label="Crop" style={{ display: 'inline-flex' }}>
          {(['Grain', 'Silage'] as CropUse[]).map((c, i) => (
            <button
              key={c}
              type="button"
              aria-pressed={crop === c}
              onClick={() => setCrop(c)}
              style={{ ...S.cropBtn, ...(crop === c ? S.cropOn : null), borderRadius: i === 0 ? '8px 0 0 8px' : '0 8px 8px 0', marginLeft: i ? -1 : 0 }}
            >
              {c}
            </button>
          ))}
        </span>
      </div>
      <div className="ftable">
        <div className="ftable__scroll" style={S.scroll}>
          <table style={S.table}>
            <thead>
              <tr>
                {head('state', 'State', false)}
                {head('ours', 'Ours')}
                {head('nass', 'NASS')}
                {head('err', 'Error')}
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.geography} style={{ cursor: 'default' }}>
                  <td style={S.cell}>{titleCase(c.geography)}</td>
                  <td className="is-num" style={S.cell}>{fmtFull(c.predictionValue)}</td>
                  <td className="is-num" style={S.cell}>{fmtFull(c.referenceValue)}</td>
                  <td className="is-num" style={S.cell}><ErrPct err={c.relativeError} /></td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr><td colSpan={4} style={S.cell}>No {crop.toLowerCase()} states matched.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Ignored({ rows }: { rows: Rejected[] }) {
  if (rows.length === 0) return null
  return (
    <details>
      <summary className="rail__note rail__note--keep" style={{ ...S.note, cursor: 'pointer' }}>
        {rows.length} {rows.length === 1 ? 'row' : 'rows'} ignored (other items, years or geographies)
      </summary>
      <ul style={S.list}>
        {rows.slice(0, 200).map((r) => (
          <li key={r.line}>
            Line {r.line}{r.state ? `, ${titleCase(r.state)}` : ''}: {r.reasons.join('; ')}
          </li>
        ))}
        {rows.length > 200 && <li>…and {rows.length - 200} more</li>}
      </ul>
    </details>
  )
}
