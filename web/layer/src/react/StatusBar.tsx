import { formatTime } from '../core/units';
import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

export function StatusBar(props: { state: WeatherState | null }) {
  const { t, intl, timeZone } = useWeatherI18n();
  const s = props.state;
  if (!s) return null;
  const layerName = t(`layer.${s.layer}`);
  const fmt = (d: Date | string) => formatTime(new Date(d), intl, timeZone);
  const warnings = Object.entries(s.manifest?.sources ?? {})
    .filter(
      ([, src]) => src.status === 'stale' || src.status === 'error' || src.status === 'missing',
    )
    .map(([, src]) =>
      src.status === 'stale'
        ? t('status.sourceStale', { source: src.label })
        : t('status.sourceError', { source: src.label }),
    );
  let main: React.ReactNode = null;
  if (s.status === 'loading') main = <span>{t('status.loading')}</span>;
  else if (s.status === 'error')
    main = <span className="wl-error">{t('status.manifestError')}</span>;
  else if (s.status === 'no-data') {
    main = (
      <span className="wl-warning" role="status">
        {s.layerRange
          ? t('status.noDataAtTime', {
              layer: layerName,
              start: fmt(s.layerRange.start),
              end: fmt(s.layerRange.end),
            })
          : t('status.noDataAtTimeShort', { layer: layerName })}
      </span>
    );
  } else if (s.resolved) {
    const seg = s.resolved.segment;
    main = (
      <>
        <strong className="wl-model">{seg.label}</strong>
        <span>{t('time.validAt', { time: fmt(s.resolved.time) })}</span>
        {seg.step_hours ? (
          <span className="wl-muted">{t('time.step', { hours: seg.step_hours })}</span>
        ) : null}
        {s.layerRange && (
          <span className="wl-muted">{t('status.dataEnds', { time: fmt(s.layerRange.end) })}</span>
        )}
        {s.loading && <span className="wl-spinner" aria-label={t('status.loading')} />}
      </>
    );
  }
  return (
    <div className="wl-panel wl-status" role="status" aria-live="polite">
      <div className="wl-status-main">{main}</div>
      {s.message?.key === 'status.tileError' && (
        <div className="wl-warning">{t('status.tileError')}</div>
      )}
      {warnings.map((w) => (
        <div key={w} className="wl-warning">
          {w}
        </div>
      ))}
    </div>
  );
}
