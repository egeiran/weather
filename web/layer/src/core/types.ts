/** Types mirroring schema/manifest.schema.json (schema_version 1.x). */

export type LayerId = 'wind' | 'gust' | 'wave_height' | 'wave_period' | 'swell' | 'current';
export const LAYER_IDS: readonly LayerId[] = [
  'wind',
  'gust',
  'wave_height',
  'wave_period',
  'swell',
  'current',
] as const;

export type BBox = [west: number, south: number, east: number, north: number];

export interface Channel {
  name: string;
  unit: string;
  scale: number;
  offset: number;
  nodata: number;
  min: number;
  max: number;
  wrap?: number;
  description?: string;
}

export interface Availability {
  x0: number;
  y0: number;
  width: number;
  height: number;
  count: number;
  bits: string;
}

export interface Segment {
  source: string;
  run_id: string;
  label: string;
  start: string;
  end: string;
  step_hours: number | null;
  times: string[];
  tiles: string;
  minzoom: number;
  maxzoom: number;
  bounds: BBox;
  availability: Record<string, Availability>;
  channels: Channel[];
  value_channel: number;
  direction_channel: number;
}

export interface LayerInfo {
  product: 'wind' | 'waves' | 'swell' | 'current';
  unit: string;
  value: string;
  direction: string;
  direction_convention: 'from' | 'to';
  particles: boolean;
  start: string;
  end: string;
  segments: Segment[];
}

export type SourceStatus = 'ok' | 'stale' | 'error' | 'missing' | 'pending';

export interface SourceInfo {
  label: string;
  model?: string;
  run_id?: string;
  reference_time?: string;
  attribution?: string;
  license?: string;
  products?: string[];
  start?: string;
  end?: string;
  status: SourceStatus;
  message?: string;
  checked_at?: string;
}

export interface SeriesVariable extends Channel {
  product: string;
  segments: {
    source: string;
    run_id: string;
    start: string;
    end: string;
    step_hours: number | null;
  }[];
}

export interface SeriesInfo {
  id: string;
  template: string;
  format: 'WLS1+gzip';
  grid: {
    origin: [number, number];
    dlon: number;
    dlat: number;
    chunk: number;
    row0: number;
    col0: number;
    rows: number;
    cols: number;
  };
  times: string[];
  variables: SeriesVariable[];
  availability: Availability;
}

export interface AttributionInfo {
  name: string;
  text: string;
  url: string;
  license?: string;
}

export interface Manifest {
  schema_version: string;
  generated_at: string;
  area: { name: string; bounds: BBox };
  tile: {
    size: number;
    buffer: number;
    format: 'png';
    encoding: 'rgb8-linear';
    nodata: number;
    scheme: 'xyz';
    time_format: string;
  };
  attribution: AttributionInfo[];
  sources: Record<string, SourceInfo>;
  layers: Partial<Record<LayerId, LayerInfo>>;
  series: SeriesInfo | null;
}

/** fetch-compatible function; the host injects one that adds its own auth. */
export type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;
