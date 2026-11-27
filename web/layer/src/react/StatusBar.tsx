import { formatTime } from '../core/units';
import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

/**
 * Only what needs attention: "no data at this time", manifest/tile errors and sources showing
 * an older run. Model, run and valid time live in the timeline. Renders nothing when all is well.
 */
export function StatusBar(props: { state: WeatherState | null }) {
  const { t, intl, timeZone } = useWeatherI18n();
  const s = props.state;
  if (!s) return null;
  const layerName = t(`layer.${s.layer}`);
  const fmt = (d: Date | string) => formatTime(new Date(d), intl, timeZone);
  const items: { key: string; text: string; tone: 'warning' | 'error' }[] = [];
  if (s.status === 'error')
    items.push({ key: 'm', text: t('status.manifestError'), tone: 'error' });
  if (s.status === 'no-data') {
    items.push({
      key: 'nd',
      tone: 'warning',
      text: s.layerRange
        ? t('status.noDataAtTime', {
            layer: layerName,
            start: fmt(s.layerRange.start),
            end: fmt(s.layerRange.end),
          })
        : t('status.noDataAtTimeShort', { layer: layerName }),
    });
  }
  if (s.message?.key === 'status.tileError')
    items.push({ key: 'te', text: t('status.tileError'), tone: 'warning' });
  for (const [name, src] of Object.entries(s.manifest?.sources ?? {})) {
    if (src.status === 'stale')
      items.push({
        key: name,
        tone: 'warning',
        text: t('status.sourceStale', { source: src.label }),
      });
    if (src.status === 'error' || src.status === 'missing')
      items.push({
        key: name,
        tone: 'error',
        text: t('status.sourceError', { source: src.label }),
      });
  }
  if (!items.length) return null;
  return (
    <div className="wl-status" role="status" aria-live="polite">
      {items.map((i) => (
        <div key={i.key} className={`wl-status-chip wl-${i.tone}`}>
          {i.text}
        </div>
      ))}
    </div>
  );
}
