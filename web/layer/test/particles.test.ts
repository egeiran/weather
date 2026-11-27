import { WeatherLayers } from '../src/core/WeatherLayers';

function mockEnv(reduced: boolean, connection?: { effectiveType?: string; saveData?: boolean }) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: q.includes('reduce') ? reduced : false,
    addEventListener: () => {},
  }));
  vi.stubGlobal('navigator', { connection });
}

afterEach(() => vi.unstubAllGlobals());

const opts = { baseUrl: '/data/', fetch: () => Promise.reject(new Error('offline')) };

describe('particles setting', () => {
  test('auto: on by default', () => {
    mockEnv(false, { effectiveType: '4g' });
    expect(new WeatherLayers(opts).getState().particles).toMatchObject({
      enabled: true,
      reason: null,
    });
  });

  test('auto: off with prefers-reduced-motion', () => {
    mockEnv(true);
    expect(new WeatherLayers(opts).getState().particles).toMatchObject({
      enabled: false,
      reason: 'reduced-motion',
    });
  });

  test('auto: off on slow or save-data connections', () => {
    mockEnv(false, { effectiveType: '3g' });
    expect(new WeatherLayers(opts).getState().particles.reason).toBe('slow-connection');
    mockEnv(false, { saveData: true, effectiveType: '4g' });
    expect(new WeatherLayers(opts).getState().particles.enabled).toBe(false);
  });

  test('explicit setting wins over auto rules', () => {
    mockEnv(true);
    const w = new WeatherLayers({ ...opts, particles: true });
    expect(w.getState().particles.enabled).toBe(true);
    w.setParticles(false);
    expect(w.getState().particles.enabled).toBe(false);
  });
});

describe('arrows setting', () => {
  test("'auto' shows arrows only when particles are off", () => {
    mockEnv(false, { effectiveType: '4g' });
    const w = new WeatherLayers(opts);
    expect(w.getState()).toMatchObject({ arrows: false, arrowsSetting: 'auto' });
    w.setParticles(false);
    expect(w.getState().arrows).toBe(true);
  });

  test("'auto' falls back to arrows with reduced motion", () => {
    mockEnv(true);
    expect(new WeatherLayers(opts).getState().arrows).toBe(true);
  });

  test('explicit arrows can run together with particles', () => {
    mockEnv(false, { effectiveType: '4g' });
    const w = new WeatherLayers({ ...opts, arrows: true });
    expect(w.getState()).toMatchObject({ arrows: true, particles: { enabled: true } });
  });
});
