import type { ThresholdLayer, Thresholds } from '../core/thresholds';
import { useWeatherI18n } from './i18n';

const FIELDS: { key: ThresholdLayer; step: number; min: number; max: number }[] = [
  { key: 'wave_height', step: 0.1, min: 0, max: 15 },
  { key: 'gust', step: 1, min: 0, max: 60 },
  { key: 'current', step: 0.1, min: 0, max: 8 },
];

export function ThresholdControls(props: {
  thresholds: Thresholds;
  enabled: boolean;
  onChange: (t: Thresholds) => void;
  onEnabled: (on: boolean) => void;
}) {
  const { t } = useWeatherI18n();
  return (
    <fieldset className="wl-panel wl-thresholds">
      <legend>{t('thresholds.title')}</legend>
      <label className="wl-toggle">
        <input
          type="checkbox"
          checked={props.enabled}
          onChange={(e) => props.onEnabled(e.target.checked)}
        />
        <span>{t('thresholds.enabled')}</span>
      </label>
      {FIELDS.map((f) => (
        <label key={f.key} className="wl-threshold-row">
          <span>{t(`thresholds.${f.key}`)}</span>
          <input
            type="number"
            inputMode="decimal"
            step={f.step}
            min={f.min}
            max={f.max}
            value={props.thresholds[f.key] ?? ''}
            onChange={(e) => {
              const v = e.target.value === '' ? null : Number(e.target.value);
              props.onChange({
                ...props.thresholds,
                [f.key]: v !== null && Number.isFinite(v) ? v : null,
              });
            }}
          />
        </label>
      ))}
      <p className="wl-muted wl-small">{t('thresholds.placeholder')}</p>
    </fieldset>
  );
}
