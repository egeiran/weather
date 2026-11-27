import type { LayerId } from '../core/types';

/** Small line icons (20×20, currentColor) for the layer rail. */
const PATHS: Record<LayerId, string> = {
  wind: 'M3 7h9a2.5 2.5 0 1 0-2.5-2.5M3 11h13a2.5 2.5 0 1 1-2.5 2.5M3 15h6',
  gust: 'M3 7h8a2.5 2.5 0 1 0-2.5-2.5M3 11h10M3 15h5M16 3l-2.5 6h3L14 17',
  wave_height: 'M2 13c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2M10 3v7M7.5 5.5 10 3l2.5 2.5',
  wave_period: 'M2 12c2 0 2-3 4-3s2 3 4 3 2-3 4-3 2 3 4 3M4 16h12M4 14.5V17.5M16 14.5V17.5',
  swell: 'M2 14c3 0 3-6 6-6s3 6 6 6 3-3 4-3M2 17h16',
  current: 'M3 6h10l-3-3M3 6l0 0M17 14H7l3 3M5 10h10',
};

export function LayerIcon({ layer }: { layer: LayerId }) {
  return (
    <svg
      className="wl-icon"
      viewBox="0 0 20 20"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[layer]} />
    </svg>
  );
}

/** Settings icon: three sliders. */
export function GearIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M3 5h8M15 5h2M3 10h3M10 10h7M3 15h9M16 15h1" />
      <circle cx="13" cy="5" r="2" />
      <circle cx="8" cy="10" r="2" />
      <circle cx="14" cy="15" r="2" />
    </svg>
  );
}

/** Arrow pointing up (north); rotate it with CSS to the motion bearing. */
export function DirectionArrow({ bearing }: { bearing: number }) {
  return (
    <svg
      className="wl-dir"
      viewBox="0 0 12 12"
      width="12"
      height="12"
      style={{ transform: `rotate(${bearing}deg)` }}
      aria-hidden="true"
    >
      <path d="M6 1 10 9 6 7.2 2 9Z" fill="currentColor" />
    </svg>
  );
}
