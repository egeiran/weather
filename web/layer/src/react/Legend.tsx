import { cssGradient } from '../core/ramps';
import { THRESHOLD_VARIABLE, type ThresholdLayer } from '../core/thresholds';
import { displayUnit } from '../core/units';
import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

export function Legend(props: { state: WeatherState | null }) {
  const { t, intl } = useWeatherI18n();
  const s = props.state;
  if (!s?.manifest) return null;
  const ramp = s.ramp;
  const unit = displayUnit(s.manifest.layers[s.layer]?.unit ?? '');
  const span = ramp.max - ramp.min;
  // Keep tick labels apart (stops are denser at low values).
  const ticks: typeof ramp.stops = [];
  for (const st of ramp.stops) {
    const pos = (st.value - ramp.min) / span;
    const prev = ticks[ticks.length - 1];
    const isLast = st === ramp.stops[ramp.stops.length - 1];
    if (!prev || pos - (prev.value - ramp.min) / span >= 0.11) ticks.push(st);
    else if (isLast) ticks[ticks.length - 1] = st;
  }
  const fmt = new Intl.NumberFormat(intl, { maximumFractionDigits: 2 });
  const thrLayer = (s.layer in THRESHOLD_VARIABLE ? s.layer : null) as ThresholdLayer | null;
  const thr = s.thresholdsEnabled && thrLayer ? s.thresholds[thrLayer] : null;
  return (
    <div
      className="wl-panel wl-legend"
      aria-label={t('legend.title', { layer: t(`layer.${s.layer}`), unit })}
    >
      <div className="wl-legend-title">
        {t('legend.title', { layer: t(`layer.${s.layer}`), unit })}
      </div>
      <div className="wl-legend-bar" style={{ background: cssGradient(ramp) }}>
        {thr !== null && thr >= ramp.min && thr <= ramp.max && (
          <div
            className="wl-legend-threshold"
            style={{ left: `${((thr - ramp.min) / span) * 100}%` }}
            title={t('legend.threshold', { value: `${fmt.format(thr)} ${unit}` })}
          />
        )}
      </div>
      <div className="wl-legend-ticks">
        {ticks.map((st) => (
          <span key={st.value} style={{ left: `${((st.value - ramp.min) / span) * 100}%` }}>
            {fmt.format(st.value)}
          </span>
        ))}
      </div>
    </div>
  );
}
