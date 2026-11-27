import { layerTimes, resolveTime, stepTime, timeKey } from '../src/core/time';
import { windLayer } from './fixtures';

describe('time stitching', () => {
  const layer = windLayer();

  test('picks MEPS hourly before its end', () => {
    const r = resolveTime(layer, new Date('2026-11-28T12:20:00Z'))!;
    expect(r.segment.source).toBe('meps');
    expect(r.time.toISOString()).toBe('2026-11-28T12:00:00.000Z');
    expect(r.timeKey).toBe('20261128T1200Z');
  });

  test('switches to ECMWF 3-hourly after MEPS, snapping to the nearest step', () => {
    const r = resolveTime(layer, new Date('2026-11-30T07:10:00Z'))!;
    expect(r.segment.source).toBe('ecmwf');
    expect(r.segment.step_hours).toBe(3);
    expect(r.time.toISOString()).toBe('2026-11-30T06:00:00.000Z');
  });

  test('6-hourly tail and out-of-range handling', () => {
    const r = resolveTime(layer, new Date('2026-12-05T13:00:00Z'))!;
    expect(r.segment.step_hours).toBe(6);
    expect(r.time.toISOString()).toBe('2026-12-05T12:00:00.000Z');
    expect(resolveTime(layer, new Date('2026-12-20T00:00:00Z'))).toBeNull();
    expect(resolveTime(layer, new Date('2026-11-26T00:00:00Z'))).toBeNull();
  });

  test('stepping walks over segment boundaries', () => {
    const last = new Date('2026-11-30T00:00:00Z'); // last MEPS step
    expect(stepTime(layer, last, 1)!.toISOString()).toBe('2026-11-30T03:00:00.000Z');
    expect(stepTime(layer, new Date('2026-11-30T03:00:00Z'), -1)!.toISOString()).toBe(
      last.toISOString(),
    );
    expect(layerTimes(layer).length).toBe(67 + 23 + 16);
  });

  test('timeKey format matches the pipeline', () => {
    expect(timeKey('2026-11-27T06:00:00Z')).toBe('20261127T0600Z');
  });
});
