export { WeatherLayers } from './core/WeatherLayers';
export type {
  ParticlesSetting,
  ParticlesState,
  PointForecast,
  WeatherLayersOptions,
  WeatherState,
  WeatherStatus,
} from './core/WeatherLayers';
export type { Theme, ThresholdStyle } from './core/gl/renderer';
export * from './core/types';
export { checkManifest, joinUrl, loadManifest, SUPPORTED_MAJOR } from './core/manifest';
export { layerRange, layerTimes, manifestRange, resolveTime, stepTime, timeKey } from './core/time';
export type { ResolvedTime, TimeRange } from './core/time';
export { DEFAULT_THRESHOLDS, firstExceedance, THRESHOLD_VARIABLE } from './core/thresholds';
export type { Exceedance, ThresholdLayer, Thresholds } from './core/thresholds';
export { cssGradient, getRamp, RAMP_FAMILIES, rampColor, VALUE_STOPS } from './core/ramps';
export type { Ramp, RampFamily } from './core/ramps';
export {
  compass,
  DEFAULT_TIME_ZONE,
  displayUnit,
  formatShortTime,
  formatTime,
  formatValue,
} from './core/units';
export { intlLocale, makeTranslator, MESSAGES } from './core/i18n';
export type { Locale, Messages, Translate } from './core/i18n';
export { chunkFor, cellSeries, parseChunk } from './core/series';
export { tileZoomFor, visibleTiles } from './core/tiles';

export const VERSION = '0.1.0';
export { decodeCode, motionVector, sampleTile } from './core/decode';
