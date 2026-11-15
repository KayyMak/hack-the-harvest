import { Fragment } from 'react'
import type { ReactNode } from 'react'
import { parseInline, parseMarkdown } from '../markdown'

/** A citable source: when a map is passed, [ids] not in it are marked as not retrieved. */
export type CiteInfo = { kind: string; label: string }
export type Cites = Map<string, CiteInfo>

/** Safe markdown for model-written reports: React elements only, never raw HTML (see ../markdown.ts).
 *  Without `cites`, [tool] tags render as neutral chips (the Agent tab cites tool names). */
export function Markdown({ text, cites, className = 'md' }: { text: string; cites?: Cites; className?: string }) {
  const inline = (s: string) => renderInline(s, cites)
  const lines = (ls: string[]) => ls.map((l, i) => (
    <Fragment key={i}>
      {i > 0 && <br />}
      {inline(l)}
    </Fragment>
  ))
  return (
    <div className={className}>
      {parseMarkdown(text).map((b, k) => {
        switch (b.kind) {
          case 'heading':
            return b.level <= 2 ? <h3 key={k}>{inline(b.text)}</h3> : <h4 key={k}>{inline(b.text)}</h4>
          case 'para':
            return <p key={k}>{lines(b.lines)}</p>
          case 'list': {
            const items = b.items.map((it, i) => <li key={i}>{inline(it)}</li>)
            return b.ordered ? <ol key={k}>{items}</ol> : <ul key={k}>{items}</ul>
          }
          case 'quote':
            return <blockquote key={k}>{lines(b.lines)}</blockquote>
          case 'rule':
            return <hr key={k} />
          case 'table':
            return (
              <div className="md__table" key={k} role="region" aria-label="Table" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      {b.header.map((h, c) => (
                        <th key={c} style={b.align[c] ? { textAlign: b.align[c]! } : undefined}>{inline(h)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, c) => (
                          <td key={c} style={b.align[c] ? { textAlign: b.align[c]! } : undefined}>{inline(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        }
      })}
    </div>
  )
}

function renderInline(s: string, cites?: Cites): ReactNode {
  return parseInline(s).map((t, i) => {
    if (t.kind === 'bold') return <strong key={i}>{renderInline(t.text, cites)}</strong>
    if (t.kind === 'code') return <code key={i}>{t.text}</code>
    if (t.kind === 'cite') {
      const c = cites?.get(t.text)
      const unknown = cites !== undefined && !c
      const title = c ? `${c.kind === 'doc' ? 'Document' : 'Tool'}: ${c.label}` : unknown ? 'Not a retrieved source' : `Source: ${t.text}`
      return (
        <sup key={i} className={`cite${unknown ? ' cite--unknown' : ''}`} title={title}>
          {t.text.replace(/^.*\//, '')}
        </sup>
      )
    }
    return <Fragment key={i}>{t.text}</Fragment>
  })
}
