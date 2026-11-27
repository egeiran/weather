import type { LayerId } from '../core/types';
import type { WeatherState } from '../core/WeatherLayers';
import type { ParticlesSetting } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

export function LayerPicker(props: {
  state: WeatherState | null;
  layer: LayerId;
  onLayer: (l: LayerId) => void;
  particles: ParticlesSetting;
  onParticles: (p: ParticlesSetting) => void;
  /** Shown state comes from `state.arrows`; toggling sets an explicit on/off. */
  arrows?: boolean;
  onArrows: (on: boolean) => void;
}) {
  const { t } = useWeatherI18n();
  const layers = props.state?.layers ?? [];
  const p = props.state?.particles;
  const particlesOn = p ? p.enabled : props.particles !== false;
  const reason =
    p?.reason === 'reduced-motion'
      ? t('particles.reducedMotion')
      : p?.reason === 'slow-connection'
        ? t('particles.slowConnection')
        : null;
  return (
    <div className="wl-panel wl-layers" role="group" aria-label={t('layers.title')}>
      <div className="wl-layer-buttons">
        {layers.map((l) => (
          <button
            key={l}
            type="button"
            className="wl-layer-button"
            aria-pressed={l === props.layer}
            onClick={() => props.onLayer(l)}
          >
            {t(`layer.${l}`)}
          </button>
        ))}
      </div>
      <div className="wl-toggles">
        <label className="wl-toggle">
          <input
            type="checkbox"
            checked={particlesOn}
            onChange={(e) => props.onParticles(e.target.checked)}
          />
          <span>{t('particles.toggle')}</span>
          {reason && props.particles === 'auto' && <small className="wl-muted"> {reason}</small>}
        </label>
        <label className="wl-toggle">
          <input
            type="checkbox"
            checked={props.state?.arrows ?? props.arrows ?? false}
            onChange={(e) => props.onArrows(e.target.checked)}
          />
          <span>{t('arrows.toggle')}</span>
        </label>
      </div>
    </div>
  );
}
