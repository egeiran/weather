import { useEffect, useRef, useState } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { WeatherLayers, type WeatherLayersOptions, type WeatherState } from '../core/WeatherLayers';

/**
 * Create a WeatherLayers controller for a maplibre map instance and subscribe to its state.
 * Options are read once at creation; drive changes through the returned controller (or use
 * <WeatherOverlay>, which syncs props for you).
 */
export function useWeatherLayers(
  map: MapLibreMap | null | undefined,
  options: WeatherLayersOptions,
): { controller: WeatherLayers | null; state: WeatherState | null } {
  const [controller, setController] = useState<WeatherLayers | null>(null);
  const [state, setState] = useState<WeatherState | null>(null);
  const optsRef = useRef(options);
  useEffect(() => {
    if (!map) return;
    const c = new WeatherLayers(optsRef.current).addTo(map);
    const off = c.on('change', setState);
    setController(c);
    return () => {
      off();
      c.remove();
      setController(null);
    };
  }, [map]);
  return { controller, state };
}
