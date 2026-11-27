import { useEffect, useMemo, useRef, useState } from 'react';
import Map, { AttributionControl, NavigationControl, type MapRef } from 'react-map-gl/maplibre';
import {
  DEFAULT_THRESHOLDS,
  type ArrowsSetting,
  RAMP_FAMILIES,
  type LayerId,
  type Locale,
  type ParticlesSetting,
  type RampFamily,
  type Thresholds,
  type ThresholdStyle,
  type WeatherLayers,
  type WeatherState,
} from 'weather-layers';
import {
  Attribution,
  LayerRail,
  Legend,
  PointPanel,
  PointPin,
  SettingsMenu,
  StatusBar,
  ThresholdControls,
  TimeSlider,
  WeatherI18nProvider,
  WeatherOverlay,
  usePointQuery,
  useWeatherI18n,
} from 'weather-layers/react';

import { DATA_BASE_URL, STYLE_DARK, STYLE_LIGHT, authFetch } from './config';
import { DebugOverlay } from './DebugOverlay';

const params = new URLSearchParams(location.search);
const HOUR = 3600_000;

function initialTime(): Date {
  const t = params.get('time');
  if (t) {
    const d = new Date(t);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return new Date(Math.floor(Date.now() / HOUR) * HOUR);
}

function parseParticles(): ParticlesSetting {
  const p = params.get('particles');
  return p === '1' ? true : p === '0' ? false : 'auto';
}

export function App() {
  const [locale, setLocale] = useState<Locale>(params.get('lang') === 'en' ? 'en' : 'nb');
  return (
    <WeatherI18nProvider locale={locale}>
      <Demo locale={locale} onLocale={setLocale} />
    </WeatherI18nProvider>
  );
}

function Demo(props: { locale: Locale; onLocale: (l: Locale) => void }) {
  const { t } = useWeatherI18n();
  const mapRef = useRef<MapRef>(null);
  const [theme, setTheme] = useState<'light' | 'dark'>(
    params.get('theme') === 'dark' ? 'dark' : 'light',
  );
  const [layer, setLayer] = useState<LayerId>((params.get('layer') as LayerId) ?? 'wind');
  const [time, setTime] = useState<Date>(initialTime);
  const [playing, setPlaying] = useState(false);
  const [particles, setParticles] = useState<ParticlesSetting>(parseParticles);
  const [arrows, setArrows] = useState<ArrowsSetting>(
    params.get('arrows') === '1' ? true : params.get('arrows') === '0' ? false : 'auto',
  );
  const [thresholds, setThresholds] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const [thresholdsEnabled, setThresholdsEnabled] = useState(params.get('thresholds') !== '0');
  const [thresholdStyle, setThresholdStyle] = useState<ThresholdStyle>(
    (params.get('tstyle') as ThresholdStyle) ?? 'hatch',
  );
  const [rampFamily, setRampFamily] = useState<RampFamily>(
    (params.get('ramp') as RampFamily) ?? 'calm',
  );
  const [state, setState] = useState<WeatherState | null>(null);
  const [controller, setController] = useState<WeatherLayers | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const {
    point,
    forecast,
    loading: pointLoading,
    error: pointError,
    query,
    clear: clearPoint,
  } = usePointQuery(controller);
  const [bearing, setBearing] = useState(0);
  const fitted = useRef(false);

  // Fit the data area once the manifest is known (unless the URL pins a view).
  useEffect(() => {
    if (fitted.current || !state?.manifest || params.get('view')) return;
    const b = state.manifest.area.bounds;
    mapRef.current?.fitBounds(
      [
        [b[0], b[1]],
        [b[2], b[3]],
      ],
      { padding: 40, duration: 0 },
    );
    fitted.current = true;
  }, [state?.manifest]);

  // ?panel=lat,lon places the pin and opens the details (used by screenshots).
  useEffect(() => {
    const p = params.get('panel');
    if (!p || !controller || !state?.manifest || point) return;
    const [lat, lng] = p.split(',').map(Number);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      // Deep link: fetch the point once data is ready (an external-system sync).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPanelOpen(params.get('details') !== '0');
      query({ lng: lng!, lat: lat! });
    }
  }, [controller, state?.manifest, point, query]);

  const view = params.get('view')?.split(',').map(Number);
  const initialViewState = useMemo(
    () =>
      view && view.length === 3
        ? { latitude: view[0]!, longitude: view[1]!, zoom: view[2]! }
        : { latitude: 63.7, longitude: 8.75, zoom: 7 },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const attribution = (state?.manifest?.attribution ?? []).map((a) => a.name).join(', ');
  const shownTime = state?.resolved?.time ?? time;
  const closePoint = () => {
    clearPoint();
    setPanelOpen(false);
  };

  return (
    <div className="wl-root demo" data-theme={theme}>
      <Map
        ref={mapRef}
        initialViewState={initialViewState}
        mapStyle={theme === 'dark' ? STYLE_DARK : STYLE_LIGHT}
        style={{ position: 'absolute', inset: 0 }}
        attributionControl={false}
        onClick={(e) => query({ lng: e.lngLat.lng, lat: e.lngLat.lat })}
        onRotate={(e) => setBearing(e.viewState.bearing)}
        cursor="crosshair"
      >
        <WeatherOverlay
          baseUrl={DATA_BASE_URL}
          fetch={authFetch}
          layer={layer}
          time={time}
          particles={particles}
          arrows={arrows}
          thresholds={thresholds}
          thresholdsEnabled={thresholdsEnabled}
          thresholdStyle={thresholdStyle}
          rampFamily={rampFamily}
          theme={theme}
          onState={setState}
          onReady={setController}
        />
        <NavigationControl position="bottom-right" showCompass={false} />
        <AttributionControl
          position="bottom-right"
          compact
          customAttribution={
            attribution ? `${t('attribution.data', { sources: attribution })}` : undefined
          }
        />
        {point && (
          <PointPin
            lngLat={point}
            state={state}
            forecast={forecast}
            time={shownTime}
            bearing={bearing}
            onMove={query}
            onOpen={() => setPanelOpen(true)}
            onClose={closePoint}
          />
        )}
      </Map>

      <div className="demo-top-left">
        <Legend state={state} />
        <StatusBar state={state} />
        {point && panelOpen && (
          <div className="demo-point">
            <PointPanel
              state={state}
              forecast={forecast}
              loading={pointLoading}
              error={pointError}
              time={shownTime}
              onClose={() => setPanelOpen(false)}
            />
          </div>
        )}
      </div>

      <div className="demo-top-right">
        <SettingsMenu
          state={state}
          particles={particles}
          onParticles={setParticles}
          arrows={arrows}
          onArrows={setArrows}
          defaultOpen={params.get('settings') === '1'}
        >
          <ThresholdControls
            thresholds={thresholds}
            enabled={thresholdsEnabled}
            onChange={setThresholds}
            onEnabled={setThresholdsEnabled}
          />
          <section>
            <h3>{t('settings.appearance')}</h3>
            <label className="wl-field">
              <span>{t('ramp.family')}</span>
              <select
                value={rampFamily}
                onChange={(e) => setRampFamily(e.target.value as RampFamily)}
              >
                {RAMP_FAMILIES.map((f) => (
                  <option key={f} value={f}>
                    {t(`ramp.${f}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="wl-field">
              <span>{t('thresholdStyle.title')}</span>
              <select
                value={thresholdStyle}
                onChange={(e) => setThresholdStyle(e.target.value as ThresholdStyle)}
              >
                {(['hatch', 'tint', 'contour'] as const).map((s) => (
                  <option key={s} value={s}>
                    {t(`thresholdStyle.${s}`)}
                  </option>
                ))}
              </select>
            </label>
            <div className="wl-field">
              <span>{t('settings.map')}</span>
              <div className="wl-segmented">
                <button
                  type="button"
                  aria-pressed={theme === 'light'}
                  onClick={() => setTheme('light')}
                >
                  {t('theme.light')}
                </button>
                <button
                  type="button"
                  aria-pressed={theme === 'dark'}
                  onClick={() => setTheme('dark')}
                >
                  {t('theme.dark')}
                </button>
              </div>
            </div>
            <div className="wl-field">
              <span>{t('settings.language')}</span>
              <div className="wl-segmented">
                <button
                  type="button"
                  aria-pressed={props.locale === 'nb'}
                  onClick={() => props.onLocale('nb')}
                >
                  {t('lang.nb')}
                </button>
                <button
                  type="button"
                  aria-pressed={props.locale === 'en'}
                  onClick={() => props.onLocale('en')}
                >
                  {t('lang.en')}
                </button>
              </div>
            </div>
          </section>
        </SettingsMenu>
      </div>

      <div className="demo-rail">
        <LayerRail state={state} layer={layer} onLayer={setLayer} />
      </div>

      <div className="demo-bottom">
        <TimeSlider
          state={state}
          time={time}
          onTime={setTime}
          playing={playing}
          onPlaying={setPlaying}
        />
        <Attribution state={state} />
      </div>
      {params.get('debug') === '1' && <DebugOverlay state={state} />}
    </div>
  );
}
