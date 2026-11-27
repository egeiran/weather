import { useEffect, useState } from 'react';
import type { WeatherState } from 'weather-layers';
import { useWeatherI18n } from 'weather-layers/react';

/** ?debug=1: frame rate and data transferred (for the performance budget). */
export function DebugOverlay(props: { state: WeatherState | null }) {
  const { t } = useWeatherI18n();
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const loop = (now: number) => {
      frames++;
      if (now - last >= 1000) {
        setFps(Math.round((frames * 1000) / (now - last)));
        frames = 0;
        last = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  const s = props.state;
  return (
    <div className="wl-panel demo-debug" data-testid="debug">
      <span data-fps={fps}>
        {fps} {t('debug.fps')}
      </span>
      {' · '}
      <span data-bytes={s?.bytesLoaded ?? 0}>
        {((s?.bytesLoaded ?? 0) / 1024).toFixed(0)} KB {t('debug.bytes')}
      </span>
      {' · '}
      <span data-requests={s?.tileRequests ?? 0}>
        {s?.tileRequests ?? 0} {t('debug.requests')}
      </span>
    </div>
  );
}
