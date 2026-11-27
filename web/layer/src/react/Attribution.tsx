import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

export function Attribution(props: { state: WeatherState | null }) {
  const { t } = useWeatherI18n();
  const list = props.state?.manifest?.attribution ?? [];
  if (!list.length) return null;
  return (
    <div className="wl-attribution">
      {t('attribution.data', { sources: '' })}
      {list.map((a, i) => (
        <span key={a.name}>
          {i > 0 && ', '}
          <a href={a.url} target="_blank" rel="noreferrer" title={a.text}>
            {a.name}
          </a>
          {a.license ? ` (${a.license})` : ''}
        </span>
      ))}
      {list.some((a) => a.name === 'ECMWF') && (
        <span className="wl-muted"> · {t('attribution.ecmwfModified')}</span>
      )}
    </div>
  );
}
