import {
  BRAND,
  MONOGRAM_PATH,
  MONOGRAM_STROKE_WIDTH,
  MONOGRAM_VIEWBOX,
} from './config';

interface MonogramProps {
  /** Side of the rounded square, in pixels. */
  size: number;
  radius: number;
}

/**
 * The brand mark, shared by the Open Graph card and the Apple touch icon.
 *
 * Rendered by satori inside `ImageResponse`, not by React in the browser: every
 * element needs an explicit `display`, and only inline styles apply.
 */
export function Monogram({ size, radius }: MonogramProps) {
  const glyph = Math.round(size * 0.62);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: radius,
        background: BRAND.primary,
      }}
    >
      <svg
        width={glyph}
        height={glyph}
        viewBox={MONOGRAM_VIEWBOX}
        fill="none"
        stroke={BRAND.navy}
        strokeWidth={MONOGRAM_STROKE_WIDTH}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={MONOGRAM_PATH} />
      </svg>
    </div>
  );
}
