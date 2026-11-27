import { useEffect, useMemo, useRef } from 'react';

import { floorHour, stepTime } from '../core/time';
import { formatShortTime, formatTime } from '../core/units';
import type { WeatherState } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';

const HOUR = 3600_000;

/**
 * Timeline from now to the end of the data. The header shows the valid time, the model and
 * run, the step length and where the layer's data ends; the track shows model segments.
 */
export function TimeSlider(props: {
  state: WeatherState | null;
  time: Date;
  onTime: (d: Date) => void;
  playing: boolean;
  onPlaying: (p: boolean) => void;
  now?: Date;
  playIntervalMs?: number;
}) {
  const { t, intl, timeZone } = useWeatherI18n();
  const s = props.state;
  const now = props.now ?? new Date();
  const range = s?.range;
  const min = range
    ? Math.max(range.start.getTime(), floorHour(now).getTime())
    : floorHour(now).getTime();
  const max = range ? Math.max(min + HOUR, range.end.getTime()) : min + 240 * HOUR;
  const layer = s?.manifest?.layers[s.layer];
  const timeRef = useRef(props.time);
  useEffect(() => {
    timeRef.current = props.time;
  }, [props.time]);
  const { onTime, onPlaying, playing } = props;

  useEffect(() => {
    if (!playing || !layer) return;
    const id = setInterval(() => {
      const next = stepTime(layer, timeRef.current, 1);
      onTime(next && next.getTime() <= max ? next : new Date(min));
    }, props.playIntervalMs ?? 900);
    return () => clearInterval(id);
  }, [playing, layer, min, max, onTime, props.playIntervalMs]);

  const pct = (ms: number) => `${(((ms - min) / (max - min)) * 100).toFixed(3)}%`;
  const segments = useMemo(
    () =>
      (layer?.segments ?? [])
        .map((g, i, all) => {
          // A step starts where the previous segment ends, so bands are contiguous.
          const prevEnd = i > 0 ? Date.parse(all[i - 1]!.end) : Date.parse(g.start);
          return { ...g, s: Math.max(min, prevEnd), e: Math.min(max, Date.parse(g.end)) };
        })
        .filter((g) => g.e > g.s),
    [layer, min, max],
  );
  const days = useMemo(() => {
    const out: number[] = [];
    const hourFmt = new Intl.DateTimeFormat('en-GB', {
      timeZone,
      hour: '2-digit',
      hourCycle: 'h23',
    });
    for (let x = Math.ceil(min / HOUR) * HOUR; x <= max; x += HOUR) {
      if (hourFmt.format(new Date(x)) === '00') out.push(x);
    }
    return out;
  }, [min, max, timeZone]);
  const value = Math.min(max, Math.max(min, props.time.getTime()));
  const layerEnd = layer ? Date.parse(layer.end) : max;
  const seg = s?.resolved?.segment;
  const fmt = (d: Date | number) => formatTime(new Date(d), intl, timeZone);

  return (
    <div className="wl-timeline">
      <div className="wl-timeline-head">
        <div className="wl-transport">
          <button
            type="button"
            className="wl-round-btn wl-small-btn"
            onClick={() => layer && onTime(stepTime(layer, props.time, -1) ?? props.time)}
            aria-label={t('time.prev')}
          >
            ‹
          </button>
          <button
            type="button"
            className="wl-round-btn wl-play"
            onClick={() => onPlaying(!playing)}
            aria-label={playing ? t('time.pause') : t('time.play')}
          >
            {playing ? '❚❚' : '▶'}
          </button>
          <button
            type="button"
            className="wl-round-btn wl-small-btn"
            onClick={() => layer && onTime(stepTime(layer, props.time, 1) ?? props.time)}
            aria-label={t('time.next')}
          >
            ›
          </button>
        </div>
        <output className="wl-time-now">{fmt(s?.resolved?.time ?? props.time)}</output>
        <div className="wl-time-meta" role="status" aria-live="polite">
          {seg ? (
            <>
              <span className="wl-model">{seg.label}</span>
              {seg.step_hours ? <span>{t('time.step', { hours: seg.step_hours })}</span> : null}
              {layer && <span>{t('time.dataUntil', { time: fmt(layerEnd) })}</span>}
            </>
          ) : null}
          {s?.loading && <span className="wl-spinner" aria-label={t('status.loading')} />}
        </div>
        <button type="button" className="wl-chip-btn" onClick={() => onTime(new Date(min))}>
          {t('time.now')}
        </button>
      </div>
      <div className="wl-track">
        <div className="wl-segments" aria-hidden="true">
          {segments.map((g) => (
            <div
              key={`${g.source}-${g.start}`}
              className={`wl-segment wl-src-${g.source}`}
              style={{ left: pct(g.s), width: pct(min + (g.e - g.s)) }}
              title={t('segment.label', { label: g.label, step: g.step_hours ?? '' })}
            >
              <span>{t('segment.short', { label: g.label, hours: g.step_hours ?? '–' })}</span>
            </div>
          ))}
          {layerEnd < max && <div className="wl-data-end" style={{ left: pct(layerEnd) }} />}
        </div>
        <input
          className="wl-range"
          type="range"
          min={min}
          max={max}
          step={HOUR}
          value={value}
          aria-label={t('time.slider')}
          aria-valuetext={fmt(value)}
          onChange={(e) => {
            onPlaying(false);
            onTime(new Date(Number(e.target.value)));
          }}
        />
        <div className="wl-days" aria-hidden="true">
          {days.map((d) => (
            <span key={d} style={{ left: pct(d) }}>
              {formatShortTime(new Date(d), intl, timeZone).split(' ')[0]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
