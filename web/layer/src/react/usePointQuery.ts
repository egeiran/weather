import { useCallback, useEffect, useMemo, useState } from 'react';

import { LatestOnly } from '../core/latest';
import type { PointForecast, WeatherLayers } from '../core/WeatherLayers';

export interface LngLat {
  lng: number;
  lat: number;
}

/**
 * State for the point pin/panel. `query` can be called on every drag event: series chunks are
 * cached, so moves within a chunk answer at once, and only the newest position is fetched when
 * a new chunk is needed. The previous forecast stays until the new one arrives (no flicker);
 * `loading` is true only while there is nothing to show yet.
 */
export function usePointQuery(controller: WeatherLayers | null) {
  const [point, setPoint] = useState<LngLat | null>(null);
  const [forecast, setForecast] = useState<PointForecast | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  const runner = useMemo(
    () =>
      controller
        ? new LatestOnly<LngLat, PointForecast | null>(
            (p) => controller.queryPoint(p),
            (_p, f) => {
              setForecast(f);
              setError(false);
              setPending(false);
            },
            () => {
              setForecast(null);
              setError(true);
              setPending(false);
            },
          )
        : null,
    [controller],
  );
  useEffect(() => () => runner?.cancel(), [runner]);

  const query = useCallback(
    (lngLat: LngLat) => {
      setPoint(lngLat);
      if (!runner) return;
      setPending(true);
      runner.push(lngLat);
    },
    [runner],
  );

  const clear = useCallback(() => {
    runner?.cancel();
    setPoint(null);
    setForecast(null);
    setPending(false);
    setError(false);
  }, [runner]);

  return { point, forecast, loading: pending && !forecast, error, query, clear };
}
