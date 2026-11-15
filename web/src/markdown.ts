/** Tiny, safe markdown parser for model-written reports (Agent tab, market report).
 *  Produces plain data (blocks of strings); components/Markdown.tsx turns it into React elements, so no
 *  model text is ever inserted as HTML. Supports headings, paragraphs (single newlines kept as line breaks),
 *  bullet / numbered lists, GitHub-style tables, blockquotes, rules, and inline **bold**, `code` and
 *  [source] citation tags. */

export type Align = 'left' | 'right' | 'center' | null
export type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'para'; lines: string[] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; header: string[]; align: Align[]; rows: string[][] }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'rule' }

export type Inline = { kind: 'text' | 'bold' | 'code' | 'cite'; text: string }

const HEADING = /^(#{1,6})\s+(.*?)\s*#*$/
const BULLET = /^[-*•+]\s+(.*)$/
const NUMBERED = /^\d+[.)]\s+(.*)$/
const SEPARATOR = /^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$/
const RULE = /^(?:-{3,}|\*{3,}|_{3,})$/

/** Cells of a table row: outer pipes dropped, `\|` kept as a literal pipe. */
export function splitRow(line: string): string[] {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
}

const alignOf = (cell: string): Align => {
  const c = cell.trim()
  if (c.startsWith(':') && c.endsWith(':')) return 'center'
  if (c.endsWith(':')) return 'right'
  if (c.startsWith(':')) return 'left'
  return null
}

export function parseMarkdown(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i].trim()
    if (!line) {
      i++
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] })
      i++
      continue
    }
    if (RULE.test(line)) {
      blocks.push({ kind: 'rule' })
      i++
      continue
    }
    // GitHub table: a row with pipes followed by a --- separator row.
    if (line.includes('|') && i + 1 < lines.length && SEPARATOR.test(lines[i + 1].trim()) && lines[i + 1].includes('-')) {
      const header = splitRow(line)
      const align = splitRow(lines[i + 1]).map(alignOf)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim().includes('|')) {
        const cells = splitRow(lines[i])
        rows.push(header.map((_, c) => cells[c] ?? ''))
        i++
      }
      blocks.push({ kind: 'table', header, align: header.map((_, c) => align[c] ?? null), rows })
      continue
    }
    if (line.startsWith('>')) {
      const quote: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) quote.push(lines[i++].trim().replace(/^>\s?/, ''))
      blocks.push({ kind: 'quote', lines: quote })
      continue
    }
    const bullet = BULLET.exec(line)
    const numbered = NUMBERED.exec(line)
    if (bullet || numbered) {
      const ordered = !bullet
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i].trim()
        const m = (ordered ? NUMBERED : BULLET).exec(l)
        if (m) items.push(m[1])
        else if (l && items.length && /^\s{2,}\S/.test(lines[i]) && !BULLET.test(l) && !NUMBERED.test(l))
          items[items.length - 1] += ' ' + l // indented continuation of the previous item
        else break
        i++
      }
      blocks.push({ kind: 'list', ordered, items })
      continue
    }
    const para: string[] = []
    while (i < lines.length) {
      const l = lines[i].trim()
      if (!l || HEADING.test(l) || BULLET.test(l) || NUMBERED.test(l) || l.startsWith('>') || RULE.test(l)) break
      if (l.includes('|') && i + 1 < lines.length && SEPARATOR.test(lines[i + 1].trim())) break
      para.push(l)
      i++
    }
    blocks.push({ kind: 'para', lines: para })
  }
  return blocks
}

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[A-Za-z0-9_./-]+(?:#\d+)?\](?!\())/g

export function parseInline(s: string): Inline[] {
  return s
    .split(INLINE)
    .filter((part) => part !== '')
    .map((part): Inline => {
      if ((part.startsWith('**') && part.endsWith('**')) || (part.startsWith('__') && part.endsWith('__')))
        return { kind: 'bold', text: part.slice(2, -2) }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 1) return { kind: 'code', text: part.slice(1, -1) }
      const cite = /^\[([A-Za-z0-9_./-]+(?:#\d+)?)\]$/.exec(part)
      if (cite) return { kind: 'cite', text: cite[1] }
      return { kind: 'text', text: part }
    })
}
