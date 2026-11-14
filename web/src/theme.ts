/**
 * Three design variants, switchable at runtime (header "Design" menu or ?theme=harvest|usda|deck|night).
 *
 * Colors come from the challenge materials: the "Silage or Grain?" deck (field green-black
 * #19251e, harvest gold #e8a82e, cream paper #f5efe4, olive #3d6b2a) and the Hack the Harvest
 * deck (USDA green, gold). Fonts are the U.S. Web Design System families USDA sites use
 * (Source Sans, Merriweather, Public Sans, Roboto Mono), bundled locally for offline demos.
 */
import { createContext, useContext } from 'react'

/** Fixed data colors — identical in every variant so meaning never changes. */
export const DATA = {
  grain: '#e2a43a',
  silage: '#5cbf7a',
  undecided: '#8b9994',
  ndti: '#c9a27c',
  flag: '#ff9b8a',
} as const

export interface ChartTokens {
  ink: string
  muted: string
  grid: string
  axis: string
  surface: string
  ndvi: string
  /** convergence chart: share of fields decided (sky) and accuracy on decided (barn rust) */
  share: string
  accuracy: string
  /** text and marker color for flags; falls back to DATA.flag */
  flag?: string
}

export interface Theme {
  id: 'glass' | 'analyst' | 'harvest' | 'usda' | 'deck' | 'night'
  name: string
  blurb: string
  vars: Record<string, string>
  chart: ChartTokens
}

const SANS_SOURCE = "'Source Sans 3', 'Source Sans Pro', 'Helvetica Neue', Arial, sans-serif"
const SANS_PUBLIC = "'Public Sans', 'Helvetica Neue', Arial, sans-serif"
const SERIF = "'Merriweather', Georgia, serif"
const MONO = "'Roboto Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"

export const THEMES: Theme[] = [
  {
    id: 'glass',
    name: 'Night glass',
    blurb: 'Default: deep field-green, frosted glass panels floating over the satellite map, Public Sans throughout.',
    vars: {
      '--font-body': SANS_PUBLIC,
      '--font-head': SANS_PUBLIC,
      '--font-mono': MONO,
      '--font-num': SANS_PUBLIC,
      '--bg': '#0d1715',
      '--surface': 'rgba(255, 255, 255, 0.04)',
      '--surface-2': 'rgba(0, 0, 0, 0.22)',
      '--ink': '#e8eeeb',
      '--ink-2': '#c7d2ce',
      '--muted': '#a9b8b2',
      '--border': 'rgba(255, 255, 255, 0.1)',
      '--bar-bg': 'transparent',
      '--bar-ink': '#e8eeeb',
      '--bar-muted': '#a9b8b2',
      '--accent': '#8fcdf2',
      '--accent-ink': '#0d1715',
      '--eyebrow': '#a9b8b2',
      '--highlight': '#8fcdf2',
      '--focus': '#8fcdf2',
      '--radius': '12px',
      '--head-weight': '600',
      '--head-tracking': '-0.01em',
    },
    chart: { ink: '#e8eeeb', muted: '#a9b8b2', grid: 'rgba(255, 255, 255, 0.08)', axis: 'rgba(255, 255, 255, 0.22)', surface: '#16241f', ndvi: '#5cbf7a', share: '#8fcdf2', accuracy: '#f0eee6' },
  },
  {
    id: 'analyst',
    name: 'Analyst',
    blurb: 'Default: plain USWDS-style data tool — white surfaces, Public Sans everywhere, quiet color so the data carries the meaning.',
    vars: {
      '--font-body': SANS_PUBLIC,
      '--font-head': SANS_PUBLIC,
      '--font-mono': MONO,
      '--font-num': SANS_PUBLIC,
      '--bg': '#f0f0f0',
      '--surface': '#ffffff',
      '--surface-2': '#f7f7f7',
      '--ink': '#1b1b1b',
      '--ink-2': '#3d4551',
      '--muted': '#5c6670',
      '--border': '#dfe1e2',
      '--bar-bg': '#ffffff',
      '--bar-ink': '#1b1b1b',
      '--bar-muted': '#5c6670',
      '--bar-border': '1px solid #dfe1e2',
      '--bar-field-bg': '#ffffff',
      '--bar-field-border': '#a9aeb1',
      '--accent': '#1a4480',
      '--accent-ink': '#ffffff',
      '--eyebrow': '#5c6670',
      '--highlight': '#1a4480',
      '--focus': '#2491ff',
      '--mode-static': '#5c6670',
      '--radius': '4px',
      '--head-weight': '700',
      '--head-tracking': '0',
      '--overlay-bg': 'rgba(255, 255, 255, 0.96)',
      '--overlay-ink': '#1b1b1b',
      '--overlay-ink-2': '#3d4551',
      '--overlay-muted': '#5c6670',
      '--overlay-border': '#dfe1e2',
      '--shadow': '0 1px 3px rgba(0, 0, 0, 0.12)',
      '--weight-num': '600',
    },
    chart: { ink: '#1b1b1b', muted: '#5c6670', grid: '#ededed', axis: '#a9aeb1', surface: '#ffffff', ndvi: '#2e7d32', share: '#1a4480', accuracy: '#b4532a' },
  },
  {
    id: 'harvest',
    name: 'Mix · Harvest',
    blurb: 'Default: cream paper (B), Source Sans + Merriweather and green buttons (A), dark field-green bar and map cards (C).',
    vars: {
      '--font-body': SANS_SOURCE,
      '--font-head': SERIF,
      '--font-mono': MONO,
      '--bg': '#ebe4d3',
      '--surface': '#f7f2e7',
      '--surface-2': '#efe8d8',
      '--ink': '#19251e',
      '--ink-2': '#36443b',
      '--muted': '#5d6858',
      '--border': '#d6cbb1',
      '--bar-bg': '#19251e',
      '--bar-ink': '#f5efe4',
      '--bar-muted': '#c9bb92',
      '--accent': '#1f5c38',
      '--accent-ink': '#ffffff',
      '--eyebrow': '#3d6b2a',
      '--highlight': '#e8a82e',
      '--focus': '#e8a82e',
      '--radius': '8px',
      '--head-weight': '700',
      '--head-tracking': '0',
      '--overlay-bg': 'rgba(25, 37, 30, 0.94)',
      '--overlay-ink': '#f5efe4',
      '--overlay-ink-2': '#ddd6c5',
      '--overlay-muted': '#c9bb92',
      '--overlay-border': '#2f3f35',
    },
    chart: { ink: '#19251e', muted: '#5d6858', grid: '#e2d9c5', axis: '#b3a88c', surface: '#f7f2e7', ndvi: '#2e7d32', share: '#2f6fa3', accuracy: '#b4532a' },
  },
  {
    id: 'usda',
    name: 'A · USDA field',
    blurb: 'Source Sans + Merriweather (usda.gov type), deep field-green bar, linen and white cards.',
    vars: {
      '--font-body': SANS_SOURCE,
      '--font-head': SERIF,
      '--font-mono': MONO,
      '--bg': '#f1eee5',
      '--surface': '#ffffff',
      '--surface-2': '#f8f6ef',
      '--ink': '#1c2620',
      '--ink-2': '#3d4841',
      '--muted': '#5b665e',
      '--border': '#dbd5c5',
      '--bar-bg': '#1f3a2b',
      '--bar-ink': '#ffffff',
      '--bar-muted': '#c2cfc5',
      '--accent': '#1f5c38',
      '--accent-ink': '#ffffff',
      '--eyebrow': '#3d6b2a',
      '--highlight': '#e3ac3c',
      '--focus': '#e3ac3c',
      '--radius': '6px',
      '--head-weight': '700',
      '--head-tracking': '0',
    },
    chart: { ink: '#1c2620', muted: '#5b665e', grid: '#e7e2d5', axis: '#b5ad98', surface: '#ffffff', ndvi: '#2e7d32', share: '#2f6fa3', accuracy: '#b4532a' },
  },
  {
    id: 'deck',
    name: 'B · Harvest deck',
    blurb: "Public Sans + Roboto Mono figures on cream paper — matches Justin's challenge deck.",
    vars: {
      '--font-body': SANS_PUBLIC,
      '--font-head': SANS_PUBLIC,
      '--font-mono': MONO,
      '--bg': '#ebe4d3',
      '--surface': '#f7f2e7',
      '--surface-2': '#efe8d8',
      '--ink': '#19251e',
      '--ink-2': '#36443b',
      '--muted': '#5d6858',
      '--border': '#d6cbb1',
      '--bar-bg': '#19251e',
      '--bar-ink': '#f5efe4',
      '--bar-muted': '#c9bb92',
      '--accent': '#19251e',
      '--accent-ink': '#f5efe4',
      '--eyebrow': '#3d6b2a',
      '--highlight': '#e8a82e',
      '--focus': '#e8a82e',
      '--radius': '10px',
      '--head-weight': '800',
      '--head-tracking': '-0.01em',
    },
    chart: { ink: '#19251e', muted: '#5d6858', grid: '#e2d9c5', axis: '#b3a88c', surface: '#f7f2e7', ndvi: '#2e7d32', share: '#2f6fa3', accuracy: '#b4532a' },
  },
  {
    id: 'night',
    name: 'C · Night harvest',
    blurb: "The deck's dark field-green slides with cream text and gold accents — check on the real projector first.",
    vars: {
      '--font-body': SANS_PUBLIC,
      '--font-head': SANS_PUBLIC,
      '--font-mono': MONO,
      '--bg': '#111a15',
      '--surface': '#19251e',
      '--surface-2': '#203027',
      '--ink': '#f5efe4',
      '--ink-2': '#ddd6c5',
      '--muted': '#aab09f',
      '--border': '#2f3f35',
      '--bar-bg': '#0c130f',
      '--bar-ink': '#f5efe4',
      '--bar-muted': '#b9b29f',
      '--accent': '#e8a82e',
      '--accent-ink': '#19251e',
      '--eyebrow': '#e8a82e',
      '--highlight': '#e8a82e',
      '--focus': '#e8a82e',
      '--radius': '8px',
      '--head-weight': '700',
      '--head-tracking': '0',
    },
    chart: { ink: '#f5efe4', muted: '#aab09f', grid: '#2a382f', axis: '#4b5a50', surface: '#19251e', ndvi: '#5cb860', share: '#4f8dc9', accuracy: '#d0683a' },
  },
]

export const themeById = (id: string | null | undefined): Theme =>
  THEMES.find((t) => t.id === id) ?? THEMES[0]

/** Light or dark. Only the default glass design has both; the other variants are fixed. */
export type Mode = 'dark' | 'light'

export const modeById = (id: string | null | undefined): Mode => (id === 'light' ? 'light' : 'dark')

/** Light counterpart of the glass design: same layout, white frosted panels, dark ink. */
const GLASS_LIGHT: Pick<Theme, 'vars' | 'chart'> = {
  vars: {
    '--bg': '#e9eeec',
    '--surface': 'rgba(20, 45, 38, 0.04)',
    '--surface-2': 'rgba(20, 45, 38, 0.06)',
    '--ink': '#13221d',
    '--ink-2': '#33453e',
    '--muted': '#55655e',
    '--border': 'rgba(20, 45, 38, 0.14)',
    '--bar-ink': '#13221d',
    '--bar-muted': '#55655e',
    '--accent': '#1c5d86',
    '--accent-ink': '#ffffff',
    '--eyebrow': '#55655e',
    '--highlight': '#1c5d86',
    '--focus': '#1c5d86',
  },
  chart: { ink: '#13221d', muted: '#55655e', grid: 'rgba(20, 45, 38, 0.1)', axis: 'rgba(20, 45, 38, 0.3)', surface: '#ffffff', ndvi: '#2e7d32', share: '#1c5d86', accuracy: '#b4532a', flag: '#c62828' },
}

/** The theme actually shown: the glass design swaps to its light palette in light mode. */
export function withMode(theme: Theme, mode: Mode): Theme {
  if (theme.id !== 'glass' || mode === 'dark') return theme
  return { ...theme, vars: { ...theme.vars, ...GLASS_LIGHT.vars }, chart: GLASS_LIGHT.chart }
}

export const isDark = (theme: Theme, mode: Mode) =>
  theme.id === 'glass' ? mode === 'dark' : theme.id === 'night'

export function applyTheme(theme: Theme, mode: Mode = 'dark') {
  const root = document.documentElement
  const shown = withMode(theme, mode)
  for (const t of THEMES) for (const k of Object.keys(t.vars)) root.style.removeProperty(k)
  for (const [k, v] of Object.entries(shown.vars)) root.style.setProperty(k, v)
  root.dataset.theme = theme.id
  root.dataset.mode = isDark(theme, mode) ? 'dark' : 'light'
  root.style.colorScheme = isDark(theme, mode) ? 'dark' : 'light'
}

export const ThemeContext = createContext<Theme>(THEMES[0])
export const useTheme = () => useContext(ThemeContext)
