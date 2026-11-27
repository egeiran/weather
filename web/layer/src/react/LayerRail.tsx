import type { LayerId } from '../core/types';
import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';
import { LayerIcon } from './icons';

/** Windy-style vertical layer menu. */
export function LayerRail(props: {
  state: WeatherState | null;
  layer: LayerId;
  onLayer: (l: LayerId) => void;
}) {
  const { t } = useWeatherI18n();
  return (
    <nav className="wl-rail" aria-label={t('layers.rail')}>
      {(props.state?.layers ?? []).map((l) => (
        <button
          key={l}
          type="button"
          className="wl-rail-btn"
          aria-pressed={l === props.layer}
          onClick={() => props.onLayer(l)}
        >
          <LayerIcon layer={l} />
          <span>{t(`layer.${l}`)}</span>
        </button>
      ))}
    </nav>
  );
}
