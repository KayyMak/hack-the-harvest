import { useMemo, useState } from 'react'
import type { FieldLandcover, FieldsResponse, Pred, UnlabeledCallView } from '../api'
import { cdlShort, cdlText, classColor, noCallReason, num } from '../format'

type SortKey = 'id' | 'acres' | 'label' | 'call' | 'p' | 'result' | 'cover'

interface Row {
  id: number
  acres: number | null
  label: string
  call: string
  p: number | null
  result: string
  /** the call is a model call on a field with no BARC label */
  unlabeledCall: boolean
  /** USDA Cropland Data Layer cover in words ('' when not available): land cover, not a label */
  cover: string
  coverLong: string
  landcover?: FieldLandcover
}

export function buildRows(fields: FieldsResponse | null, preds: Map<number, Pred>, unlabeled: Map<number, UnlabeledCallView> = new Map(), cover: Map<number, FieldLandcover> = new Map(), seasonEnd = true): Row[] {
  return (fields?.features ?? []).map((f) => {
    const p = preds.get(f.properties.OBJECTID)
    const label = f.properties.label ?? 'Unlabeled'
    const lc = cover.get(f.properties.OBJECTID)
    const land = { cover: lc ? cdlShort(lc) : '', coverLong: lc ? cdlText(lc) : '', landcover: lc }
    const u = !f.properties.label && !p ? unlabeled.get(f.properties.OBJECTID) : undefined
    if (u) return { id: f.properties.OBJECTID, acres: f.properties.ACRES ?? null, label, call: u.label, p: u.p_silage, result: '', unlabeledCall: true, ...land }
    const none = !f.properties.label ? noCallReason(lc, seasonEnd)?.short : undefined
    const call = p?.class === 'Pending' ? 'Not yet decided' : p?.class === 'Insufficient' ? 'Abstained' : (p?.class ?? none ?? 'No call')
    const decided = p?.class === 'Grain' || p?.class === 'Silage'
    const result = !f.properties.label || !decided ? '' : p?.class === f.properties.label ? 'Agrees' : 'Disagrees'
    return { id: f.properties.OBJECTID, acres: f.properties.ACRES ?? null, label, call, p: p?.p_silage ?? null, result, unlabeledCall: false, ...land }
  })
}

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)

export function rowsToCsv(rows: Row[], year: number, asOf: string) {
  const head = 'field_id,year,as_of,acres,barc_label,model_call,p_silage,result,call_type,cdl_top_class,cdl_corn_share,cdl_category'
  const body = rows.map((r) => [r.id, year, r.unlabeledCall ? `${year}-11-30` : asOf, r.acres ?? '', r.label, r.call, r.p ?? '', r.result,
    r.unlabeledCall ? 'model call on unlabeled corn field (no reference)' : r.p != null ? 'held-out call on labeled field' : '',
    csvCell(r.landcover?.crop ?? ''), r.landcover?.corn_share ?? '', r.landcover?.category ?? ''].join(','))
  return [head, ...body].join('\n')
}

const COLS: { key: SortKey; label: string; num?: boolean }[] = [
  { key: 'id', label: 'Field' },
  { key: 'acres', label: 'Acres', num: true },
  { key: 'label', label: 'BARC label' },
  { key: 'call', label: 'Model call' },
  { key: 'p', label: 'P(silage)', num: true },
  { key: 'result', label: 'Result' },
  { key: 'cover', label: 'CDL crop' },
]

export function FieldsTable({ fields, preds, unlabeled, cover, coverError, seasonEnd, onSelect, selectedId }: { fields: FieldsResponse | null; preds: Map<number, Pred>; unlabeled: Map<number, UnlabeledCallView>; cover: Map<number, FieldLandcover>; coverError?: Error | null; seasonEnd: boolean; onSelect: (id: number) => void; selectedId: number | null }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'result', dir: -1 })
  const [filter, setFilter] = useState('')
  const [showUnlabeled, setShowUnlabeled] = useState(false)
  const all = useMemo(() => buildRows(fields, preds, unlabeled, cover, seasonEnd), [fields, preds, unlabeled, cover, seasonEnd])
  const labeledCount = all.filter((r) => r.label !== 'Unlabeled').length
  const rows = useMemo(() => {
    const shown = all.filter((r) => (showUnlabeled || r.label !== 'Unlabeled') && (!filter || `${r.id} ${r.label} ${r.call} ${r.result} ${r.cover}`.toLowerCase().includes(filter.toLowerCase())))
    return shown.sort((a, b) => {
      const va = a[sort.key] ?? ''
      const vb = b[sort.key] ?? ''
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir
    })
  }, [all, showUnlabeled, sort, filter])

  return (
    <div className="ftable">
      <div className="ftable__tools">
        <label className="search">
          <span className="sr-only">Filter fields</span>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by field, label or call" />
        </label>
        <label className="toggle">
          <input type="checkbox" checked={showUnlabeled} onChange={(e) => setShowUnlabeled(e.target.checked)} />
          Show unlabeled ({all.length - labeledCount})
        </label>
        <span className="muted small">{rows.length} {showUnlabeled ? 'fields' : `of ${all.length} fields (labeled)`}</span>
      </div>
      {coverError && <p className="inline-error" role="alert">USDA Cropland Data Layer cover could not be loaded, so the CDL crop column is empty.</p>}
      <div className="ftable__scroll">
        <table>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} className={c.num ? 'is-num' : undefined} aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                  <button onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? ((-s.dir) as 1 | -1) : 1 }))}>
                    {c.label}
                    <span aria-hidden="true" className="sort">{sort.key === c.key ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.id === selectedId ? 'is-selected' : undefined} onClick={() => onSelect(r.id)}>
                <td>
                  <button className="link" onClick={() => onSelect(r.id)}>
                    {r.id}
                  </button>
                </td>
                <td className="is-num">{r.acres ?? '—'}</td>
                <td>
                  <span className="swatch swatch--outline" style={{ borderColor: classColor(r.label === 'Unlabeled' ? null : (r.label as 'Grain')) }} /> {r.label}
                </td>
                <td>
                  {r.unlabeledCall ? (
                    <><span className="swatch swatch--unlabeled" style={{ borderColor: classColor(r.call as 'Grain'), background: `color-mix(in srgb, ${classColor(r.call as 'Grain')} 30%, transparent)` }} /> {r.call} <span className="muted small">(no label)</span></>
                  ) : (
                    <><span className="swatch swatch--fill" style={{ background: classColor(r.call === 'Grain' || r.call === 'Silage' ? (r.call as 'Grain') : null) }} /> {r.call}</>
                  )}
                </td>
                <td className="is-num">{r.p == null ? <span className="muted">n/a</span> : num(r.p)}</td>
                <td className={r.result === 'Disagrees' ? 'is-bad' : r.result === 'Agrees' ? 'is-ok' : undefined}>{r.result || (r.label === 'Unlabeled' ? <span className="muted">Not scored</span> : '—')}</td>
                <td className="ftable__cover" title={`${r.coverLong || 'No cover saved'}. USDA Cropland Data Layer: satellite land cover, not a BARC label.`}>{r.cover || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
