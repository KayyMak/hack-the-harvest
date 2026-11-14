/**
 * Original mark for the prototype (not a USDA logo): one ear of corn split down the middle —
 * the left half keeps its kernels (harvested for grain), the right half is cut green (chopped
 * for silage). The same drawing is public/favicon.svg.
 */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#13261f" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" fill="none" stroke="rgba(255,255,255,0.14)" />
      <clipPath id="ear-l">
        <rect x="0" y="0" width="16" height="32" />
      </clipPath>
      <clipPath id="ear-r">
        <rect x="16" y="0" width="16" height="32" />
      </clipPath>
      <ellipse cx="16" cy="16.5" rx="6.2" ry="10" fill="#e2a43a" clipPath="url(#ear-l)" />
      <g fill="#9a6a14" clipPath="url(#ear-l)">
        <circle cx="12.6" cy="11" r="1" />
        <circle cx="14.8" cy="12.6" r="1" />
        <circle cx="12.4" cy="14.6" r="1" />
        <circle cx="14.8" cy="16.4" r="1" />
        <circle cx="12.4" cy="18.4" r="1" />
        <circle cx="14.8" cy="20.2" r="1" />
        <circle cx="13" cy="22.2" r="1" />
      </g>
      <ellipse cx="16" cy="16.5" rx="6.2" ry="10" fill="#5cbf7a" clipPath="url(#ear-r)" />
      <g stroke="#2f7a46" strokeWidth="1.3" strokeLinecap="round" clipPath="url(#ear-r)">
        <path d="M16.8 10.5l4 -2" />
        <path d="M16.8 14.5l5.2 -2.4" />
        <path d="M16.8 18.5l5.4 -2.4" />
        <path d="M16.8 22.5l4.6 -2" />
      </g>
      <line x1="16" y1="5" x2="16" y2="28" stroke="#13261f" strokeWidth="1.4" />
    </svg>
  )
}
