import { Marker } from 'react-map-gl/maplibre';

import type { LayerId } from '../core/types';
import { formatValue } from '../core/units';
import type { PointForecast, WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';
import { DirectionArrow } from './icons';
import { valueAt } from './PointPanel';

/** Series variables shown in the pin per layer, and whether its direction is "from". */
const PIN: Record<LayerId, { value: string; dir: string; from: boolean }> = {
  wind: { value: 'wind_speed', dir: 'wind_from_direction', from: true },
  gust: { value: 'wind_gust', dir: 'wind_from_direction', from: true },
  wave_height: { value: 'wave_height', dir: 'wave_from_direction', from: true },
  wave_period: { value: 'wave_period', dir: 'wave_from_direction', from: true },
  swell: { value: 'swell_height', dir: 'swell_from_direction', from: true },
  current: { value: 'current_speed', dir: 'current_to_direction', from: false },
};

/**
 * Windy-style draggable pin (react-map-gl Marker) with a bubble showing the active layer's
 * value and the direction of motion at the shown time. Click the bubble for the full panel.
 */
export function PointPin(props: {
  lngLat: { lng: number; lat: number };
  state: WeatherState | null;
  forecast: PointForecast | null;
  loading: boolean;
  time: Date;
  /** Map bearing in degrees, so the arrow stays true on a rotated map. */
  bearing?: number;
  onMove: (lngLat: { lng: number; lat: number }) => void;
  onOpen: () => void;
  onClose: () => void;
}) {
  const { t, intl } = useWeatherI18n();
  const layer = props.state?.layer ?? 'wind';
  const spec = PIN[layer];
  const unit = props.state?.manifest?.layers[layer]?.unit ?? '';
  const f = props.forecast;
  const value = f ? valueAt(f.times, f.values[spec.value], props.time) : null;
  const dir = f ? valueAt(f.times, f.values[spec.dir], props.time) : null;
  const motion = dir === null ? null : (dir + (spec.from ? 180 : 0) - (props.bearing ?? 0)) % 360;
  return (
    <Marker
      longitude={props.lngLat.lng}
      latitude={props.lngLat.lat}
      anchor="bottom"
      draggable
      onDragEnd={(e) => props.onMove({ lng: e.lngLat.lng, lat: e.lngLat.lat })}
    >
      <div className="wl-pin" title={t('pin.drag')}>
        <div className="wl-pin-bubble">
          <button
            type="button"
            className="wl-pin-value"
            onClick={props.onOpen}
            aria-label={t('pin.open')}
          >
            {props.loading ? (
              <span className="wl-spinner" />
            ) : (
              <>
                <strong>{value === null ? '–' : formatValue(value, unit, intl)}</strong>
                {motion !== null && value !== null && <DirectionArrow bearing={motion} />}
              </>
            )}
          </button>
          <button
            type="button"
            className="wl-pin-close"
            onClick={props.onClose}
            aria-label={t('pin.close')}
          >
            ×
          </button>
        </div>
        <div className="wl-pin-stem" />
        <div className="wl-pin-dot" />
      </div>
    </Marker>
  );
}
