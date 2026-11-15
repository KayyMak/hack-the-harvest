import assert from 'node:assert/strict'
import test from 'node:test'
import { parseInline, parseMarkdown } from '../src/markdown.ts'

const REPORT = `## BARC 2022 as of Oct 12
### Findings
- Balanced accuracy **0.83** [evaluate].
- Expected silage acres 68.5 [aggregate]
### Table
| Metric [evaluate] | Value |
|---|---:|
| n | 7 |
| recall \\| silage | 1.0 |
### Uncertainty
First line
second line
> **Verifier:** these numbers were not found: 11`

test('report markdown becomes headings, lists, tables, line breaks and quotes', () => {
  const blocks = parseMarkdown(REPORT)
  assert.deepEqual(blocks.map((b) => b.kind), ['heading', 'heading', 'list', 'heading', 'table', 'heading', 'para', 'quote'])
  assert.deepEqual(blocks[0], { kind: 'heading', level: 2, text: 'BARC 2022 as of Oct 12' })
  assert.deepEqual(blocks[2].items, ['Balanced accuracy **0.83** [evaluate].', 'Expected silage acres 68.5 [aggregate]'])
  assert.deepEqual(blocks[4].header, ['Metric [evaluate]', 'Value'])
  assert.deepEqual(blocks[4].align, [null, 'right'])
  assert.deepEqual(blocks[4].rows, [['n', '7'], ['recall | silage', '1.0']])
  assert.deepEqual(blocks[6].lines, ['First line', 'second line'])
  assert.deepEqual(blocks[7].lines, ['**Verifier:** these numbers were not found: 11'])
})

test('inline bold, code and citation tags; HTML stays text', () => {
  assert.deepEqual(parseInline('a **b** `c` [evaluate] <img src=x onerror=alert(1)>'), [
    { kind: 'text', text: 'a ' },
    { kind: 'bold', text: 'b' },
    { kind: 'text', text: ' ' },
    { kind: 'code', text: 'c' },
    { kind: 'text', text: ' ' },
    { kind: 'cite', text: 'evaluate' },
    { kind: 'text', text: ' <img src=x onerror=alert(1)>' },
  ])
  assert.deepEqual(parseInline('[docs/x.md#2]'), [{ kind: 'cite', text: 'docs/x.md#2' }])
})

test('numbered lists and a pipe in prose without a separator are not tables', () => {
  const blocks = parseMarkdown('1. one\n2. two\n\nA | B is just text')
  assert.deepEqual(blocks, [
    { kind: 'list', ordered: true, items: ['one', 'two'] },
    { kind: 'para', lines: ['A | B is just text'] },
  ])
})
