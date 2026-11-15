import { useMemo, useState } from 'react'
import type { FieldsResponse, Pred } from '../api'
import { classColor, num } from '../format'

type SortKey = 'id' | 'acres' | 'label' | 'call' | 'p' | 'result'

interface Row {
  id: number
  acres: number | null
  label: string
  call: string
  p: number | null
  result: string
}

export function buildRows(fields: FieldsResponse | null, preds: Map<number, Pred>): Row[] {
  return (fields?.features ?? []).map((f) => {
    const p = preds.get(f.properties.OBJECTID)
    const label = f.properties.label ?? 'Unlabeled'
    const call = p?.class === 'Pending' ? 'Not yet decided' : p?.class === 'Insufficient' ? 'Abstained' : (p?.class ?? '—')
    const decided = p?.class === 'Grain' || p?.class === 'Silage'
    const result = !f.properties.label || !decided ? '' : p?.class === f.properties.label ? 'Agrees' : 'Disagrees'
    return { id: f.properties.OBJECTID, acres: f.properties.ACRES ?? null, label, call, p: p?.p_silage ?? null, result }
  })
}

export function rowsToCsv(rows: Row[], year: number, asOf: string) {
  const head = 'field_id,year,as_of,acres,barc_label,model_call,p_silage,result'
  const body = rows.map((r) => [r.id, year, asOf, r.acres ?? '', r.label, r.call, r.p ?? '', r.result].join(','))
  return [head, ...body].join('\n')
}

const COLS: { key: SortKey; label: string; num?: boolean }[] = [
  { key: 'id', label: 'Field' },
  { key: 'acres', label: 'Acres', num: true },
  { key: 'label', label: 'BARC label' },
  { key: 'call', label: 'Model call' },
  { key: 'p', label: 'P(silage)', num: true },
  { key: 'result', label: 'Result' },
]

export function FieldsTable({ fields, preds, onSelect, selectedId }: { fields: FieldsResponse | null; preds: Map<number, Pred>; onSelect: (id: number) => void; selectedId: number | null }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'result', dir: -1 })
  const [filter, setFilter] = useState('')
  const rows = useMemo(() => {
    const all = buildRows(fields, preds).filter((r) => !filter || `${r.id} ${r.label} ${r.call} ${r.result}`.toLowerCase().includes(filter.toLowerCase()))
    return all.sort((a, b) => {
      const va = a[sort.key] ?? ''
      const vb = b[sort.key] ?? ''
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir
    })
  }, [fields, preds, sort, filter])

  return (
    <div className="ftable">
      <div className="ftable__tools">
        <label className="search">
          <span className="sr-only">Filter fields</span>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by field, label or call" />
        </label>
        <span className="muted small">{rows.length} fields</span>
      </div>
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
                  <span className="swatch swatch--fill" style={{ background: classColor(r.call === 'Grain' || r.call === 'Silage' ? (r.call as 'Grain') : null) }} /> {r.call}
                </td>
                <td className="is-num">{num(r.p)}</td>
                <td className={r.result === 'Disagrees' ? 'is-bad' : r.result === 'Agrees' ? 'is-ok' : undefined}>{r.result || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
