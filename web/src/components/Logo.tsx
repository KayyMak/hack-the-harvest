/**
 * Cutline mark (original, not a USDA logo). Two greenness curves from the season:
 * silage drops off a cliff when it is chopped (green), grain fades out slowly (amber).
 * The same drawing is public/favicon.svg.
 */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#132a22" />
      <path d="M5 25.5H27" stroke="#3b5a4e" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M5 22C8 13 11 9.5 15 9.5C19 9.5 22 13.5 27 22" fill="none" stroke="#e2a43a" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M5 21C8 11 10.5 7 14 7C16.5 7 17.5 7.6 18.6 8.6L19.6 25" fill="none" stroke="#5cbf7a" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
