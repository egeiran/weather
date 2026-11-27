import { useEffect } from 'react';
import { useMap } from 'react-map-gl/maplibre';

import type { Theme, ThresholdStyle } from '../core/gl/renderer';
import type { RampFamily } from '../core/ramps';
import type { Thresholds } from '../core/thresholds';
import type { FetchFn, LayerId } from '../core/types';
import type { ParticlesSetting, WeatherLayers, WeatherState } from '../core/WeatherLayers';
import { useWeatherLayers } from './useWeatherLayers';

export interface WeatherOverlayProps {
  baseUrl: string;
  fetch?: FetchFn;
  layer: LayerId;
  time: Date;
  visible?: boolean;
  particles?: ParticlesSetting;
  arrows?: boolean;
  thresholds?: Thresholds;
  thresholdsEnabled?: boolean;
  thresholdStyle?: ThresholdStyle;
  rampFamily?: RampFamily;
  theme?: Theme;
  opacity?: number;
  beforeId?: string;
  manifestRefreshMs?: number;
  onState?: (state: WeatherState) => void;
  onReady?: (controller: WeatherLayers | null) => void;
}

/**
 * Drop-in overlay for react-map-gl v8 (`react-map-gl/maplibre`). Render it as a child of <Map>.
 * Props are pushed into the controller; state comes back through `onState`.
 */
export function WeatherOverlay(props: WeatherOverlayProps) {
  const { current } = useMap();
  const map = current?.getMap();
  const { controller, state } = useWeatherLayers(map, {
    baseUrl: props.baseUrl,
    fetch: props.fetch,
    layer: props.layer,
    time: props.time,
    visible: props.visible,
    particles: props.particles,
    arrows: props.arrows,
    thresholds: props.thresholds,
    thresholdsEnabled: props.thresholdsEnabled,
    thresholdStyle: props.thresholdStyle,
    rampFamily: props.rampFamily,
    theme: props.theme,
    opacity: props.opacity,
    beforeId: props.beforeId,
    manifestRefreshMs: props.manifestRefreshMs,
  });
  const { onReady, onState } = props;
  useEffect(() => onReady?.(controller), [controller, onReady]);
  useEffect(() => {
    if (state) onState?.(state);
  }, [state, onState]);
  useEffect(() => controller?.setActiveLayer(props.layer), [controller, props.layer]);
  useEffect(() => controller?.setTime(props.time), [controller, props.time]);
  useEffect(() => controller?.setVisible(props.visible ?? true), [controller, props.visible]);
  useEffect(
    () => controller?.setParticles(props.particles ?? 'auto'),
    [controller, props.particles],
  );
  useEffect(() => controller?.setArrows(props.arrows ?? true), [controller, props.arrows]);
  useEffect(() => {
    if (props.thresholds) controller?.setThresholds(props.thresholds);
  }, [controller, props.thresholds]);
  useEffect(
    () => controller?.setThresholdsEnabled(props.thresholdsEnabled ?? true),
    [controller, props.thresholdsEnabled],
  );
  useEffect(() => {
    if (props.thresholdStyle) controller?.setThresholdStyle(props.thresholdStyle);
  }, [controller, props.thresholdStyle]);
  useEffect(() => {
    if (props.rampFamily) controller?.setRampFamily(props.rampFamily);
  }, [controller, props.rampFamily]);
  useEffect(() => {
    if (props.theme) controller?.setTheme(props.theme);
  }, [controller, props.theme]);
  useEffect(() => {
    if (props.opacity !== undefined) controller?.setOpacity(props.opacity);
  }, [controller, props.opacity]);
  return null;
}
