/** Cutline icon (public/cutline-icon.svg): one ear of corn sectioned down the middle, grain gold on the left, silage green on the right. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return <img src={`${import.meta.env.BASE_URL}cutline-icon.svg`} width={size} height={size} alt="" aria-hidden="true" style={{ display: 'block', borderRadius: size * 0.22 }} />
}
