/** Small dependency-free SVG time-series chart for the point panel. */
export function SeriesChart(props: {
  times: Date[];
  values: (number | null)[];
  threshold: number | null;
  now: Date;
  min?: number;
  max?: number;
  color: string;
  labelFormatter: (d: Date) => string;
  valueFormatter: (v: number) => string;
  ariaLabel: string;
  width?: number;
  height?: number;
}) {
  const W = props.width ?? 320;
  const H = props.height ?? 120;
  const pad = { l: 34, r: 8, t: 8, b: 20 };
  const pts = props.times
    .map((t, i) => ({ t: t.getTime(), v: props.values[i] }))
    .filter((p): p is { t: number; v: number } => p.v !== null && p.v !== undefined);
  if (pts.length < 2) return null;
  const t0 = Math.max(pts[0]!.t, props.now.getTime() - 3 * 3600_000);
  const shown = pts.filter((p) => p.t >= t0);
  if (shown.length < 2) return null;
  const t1 = shown[shown.length - 1]!.t;
  const vmax =
    Math.max(props.max ?? 0, ...shown.map((p) => p.v), (props.threshold ?? 0) * 1.15) || 1;
  const vmin = props.min ?? 0;
  const x = (t: number) => pad.l + ((t - t0) / (t1 - t0)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - vmin) / (vmax - vmin)) * (H - pad.t - pad.b);
  // Break the line where data has gaps (e.g. between sources) longer than 7 h.
  const paths: string[] = [];
  let d = '';
  shown.forEach((p, i) => {
    const gap = i > 0 && p.t - shown[i - 1]!.t > 7 * 3600_000;
    d += `${i === 0 || gap ? 'M' : 'L'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`;
  });
  paths.push(d);
  const yTicks = [vmin, (vmin + vmax) / 2, vmax];
  const xTicks = [t0, t0 + (t1 - t0) / 3, t0 + (2 * (t1 - t0)) / 3, t1];
  const nowX = x(Math.min(t1, Math.max(t0, props.now.getTime())));
  return (
    <svg className="wl-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.ariaLabel}>
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="wl-chart-grid" />
          <text x={pad.l - 4} y={y(v) + 3} textAnchor="end" className="wl-chart-text">
            {props.valueFormatter(v)}
          </text>
        </g>
      ))}
      {xTicks.map((tk) => (
        <text key={tk} x={x(tk)} y={H - 6} textAnchor="middle" className="wl-chart-text">
          {props.labelFormatter(new Date(tk))}
        </text>
      ))}
      {props.threshold !== null && props.threshold <= vmax && (
        <>
          <rect
            x={pad.l}
            y={pad.t}
            width={W - pad.l - pad.r}
            height={Math.max(0, y(props.threshold) - pad.t)}
            className="wl-chart-over"
          />
          <line
            x1={pad.l}
            x2={W - pad.r}
            y1={y(props.threshold)}
            y2={y(props.threshold)}
            className="wl-chart-threshold"
          />
        </>
      )}
      {paths.map((p) => (
        <path
          key={p}
          d={p}
          fill="none"
          stroke={props.color}
          strokeWidth={2}
          strokeLinejoin="round"
        />
      ))}
      <line x1={nowX} x2={nowX} y1={pad.t} y2={H - pad.b} className="wl-chart-now" />
    </svg>
  );
}
