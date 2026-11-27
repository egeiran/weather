import { rampColor, cssColor, getRamp } from '../core/ramps';
import type { LayerId } from '../core/types';
import { compass, formatAxisTime, formatShortTime, formatTime, formatValue } from '../core/units';
import type { PointForecast, WeatherState } from '../core/WeatherLayers';
import { SeriesChart } from './Chart';
import { useWeatherI18n } from './i18n';

const LAYER_VARIABLE: Record<LayerId, string> = {
  wind: 'wind_speed',
  gust: 'wind_gust',
  wave_height: 'wave_height',
  wave_period: 'wave_period',
  swell: 'swell_height',
  current: 'current_speed',
};

/** Value of a series variable at time t: nearest non-missing step within 3 h. */
export function valueAt(
  times: Date[],
  values: (number | null)[] | undefined,
  t: Date,
): number | null {
  if (!values) return null;
  let best: number | null = null;
  let dist = Infinity;
  const x = t.getTime();
  for (let i = 0; i < times.length; i++) {
    const v = values[i];
    if (v === null || v === undefined) continue;
    const d = Math.abs(times[i]!.getTime() - x);
    if (d < dist) {
      dist = d;
      best = v;
    }
  }
  return dist <= 3 * 3600_000 ? best : null;
}

export function PointPanel(props: {
  state: WeatherState | null;
  forecast: PointForecast | null;
  loading: boolean;
  error: boolean;
  time: Date;
  onClose: () => void;
}) {
  const { t, intl, timeZone } = useWeatherI18n();
  const f = props.forecast;
  const fmtNum = (v: number, digits = 1) =>
    new Intl.NumberFormat(intl, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(v);
  const at = (name: string) => (f ? valueAt(f.times, f.values[name], props.time) : null);
  const layer = props.state?.layer ?? 'wind';
  const chartVar = LAYER_VARIABLE[layer];
  const thrLayer =
    layer === 'gust' || layer === 'wave_height' || layer === 'current' ? layer : null;
  const threshold =
    thrLayer && props.state?.thresholdsEnabled ? (props.state.thresholds[thrLayer] ?? null) : null;
  const ramp = getRamp(layer, props.state?.rampFamily ?? 'calm');
  const lineColor = cssColor(rampColor(ramp, ramp.min + (ramp.max - ramp.min) * 0.75).color);
  const unit = props.state?.manifest?.layers[layer]?.unit ?? '';
  const allNull = f ? Object.values(f.values).every((arr) => arr.every((v) => v === null)) : false;

  const rows: { label: string; value: string; detail?: string }[] = f
    ? [
        {
          label: t('point.wind'),
          value: formatValue(at('wind_speed'), 'm/s', intl),
          detail:
            at('wind_speed') !== null
              ? t('point.from', {
                  dir: `${compass(at('wind_from_direction'), intl)} (${fmtNum(at('wind_from_direction') ?? 0, 0)}°)`,
                })
              : undefined,
        },
        { label: t('point.gust'), value: formatValue(at('wind_gust'), 'm/s', intl) },
        {
          label: t('point.waves'),
          value: formatValue(at('wave_height'), 'm', intl),
          detail:
            at('wave_height') !== null
              ? `${t('point.from', { dir: compass(at('wave_from_direction'), intl) })}, ${t('point.period', { value: formatValue(at('wave_period'), 's', intl) })}`
              : undefined,
        },
        {
          label: t('point.swell'),
          value: formatValue(at('swell_height'), 'm', intl),
          detail:
            at('swell_height') !== null
              ? `${t('point.from', { dir: compass(at('swell_from_direction'), intl) })}, ${t('point.period', { value: formatValue(at('swell_period'), 's', intl) })}`
              : undefined,
        },
        {
          label: t('point.current'),
          value: formatValue(at('current_speed'), 'kn', intl),
          detail:
            at('current_speed') !== null
              ? t('point.towards', {
                  dir: `${compass(at('current_to_direction'), intl)} (${fmtNum(at('current_to_direction') ?? 0, 0)}°)`,
                })
              : undefined,
        },
        { label: t('point.seaTemp'), value: formatValue(at('sea_temperature'), 'degC', intl) },
      ]
    : [];

  return (
    <section className="wl-panel wl-point" aria-label={t('point.title')}>
      <header className="wl-point-header">
        <h2>{t('point.title')}</h2>
        <button
          type="button"
          className="wl-icon-button"
          onClick={props.onClose}
          aria-label={t('point.close')}
        >
          ×
        </button>
      </header>
      {props.loading && <p className="wl-muted">{t('point.loading')}</p>}
      {props.error && <p className="wl-error">{t('point.error')}</p>}
      {!props.loading && !props.error && !f && <p className="wl-muted">{t('point.noData')}</p>}
      {f && (
        <>
          <p className="wl-muted wl-small">
            {t('point.cell', { lat: fmtNum(f.cell.lat, 3), lon: fmtNum(f.cell.lng, 3) })} ·{' '}
            {formatTime(props.time, intl, timeZone)}
          </p>
          {allNull ? (
            <p className="wl-muted">{t('point.noData')}</p>
          ) : (
            <dl className="wl-values">
              {rows.map((r) => (
                <div key={r.label} className="wl-value-row">
                  <dt>{r.label}</dt>
                  <dd>
                    <strong>{r.value}</strong>
                    {r.detail && <span className="wl-muted"> {r.detail}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <h3 className="wl-chart-title">{t('point.chart', { layer: t(`layer.${layer}`) })}</h3>
          <SeriesChart
            times={f.times}
            values={f.values[chartVar] ?? []}
            threshold={threshold}
            now={props.time}
            color={lineColor}
            labelFormatter={(d) => formatAxisTime(d, intl, timeZone)}
            valueFormatter={(v) => fmtNum(v, unit === 'kn' || unit === 'm' ? 1 : 0)}
            ariaLabel={t('point.chart', { layer: t(`layer.${layer}`) })}
          />
          <ul className="wl-exceed">
            {f.exceedances.map((e) => {
              const name = t(`layer.${e.layer}`);
              const u = e.layer === 'gust' ? 'm/s' : e.layer === 'current' ? 'kn' : 'm';
              const value = formatValue(e.threshold, u, intl);
              let text: string;
              if (!e.dataEnd) text = t('exceed.noData', { layer: name });
              else if (e.already) text = t('exceed.already', { layer: name, value });
              else if (e.first)
                text = t('exceed.over', {
                  layer: name,
                  value,
                  time: formatShortTime(e.first, intl, timeZone),
                });
              else
                text = t('exceed.never', {
                  layer: name,
                  value,
                  end: formatShortTime(e.dataEnd, intl, timeZone),
                });
              return (
                <li key={e.layer} className={e.first ? 'wl-exceed-hit' : 'wl-exceed-ok'}>
                  {text}
                </li>
              );
            })}
          </ul>
          <p className="wl-muted wl-small">
            {t('point.source', {
              sources: f.sources
                .map((s) => props.state?.manifest?.sources[s]?.label ?? s)
                .join(', '),
            })}
          </p>
        </>
      )}
    </section>
  );
}
