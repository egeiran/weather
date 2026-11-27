import en from '../src/i18n/en.json';
import nb from '../src/i18n/nb.json';
import { makeTranslator } from '../src/core/i18n';
import { getRamp, luminance, RAMP_FAMILIES, rampTexels, VALUE_STOPS } from '../src/core/ramps';
import { LAYER_IDS } from '../src/core/types';

test('nb and en message files have identical keys', () => {
  expect(Object.keys(nb).sort()).toEqual(Object.keys(en).sort());
  for (const id of LAYER_IDS) expect(nb).toHaveProperty(`layer.${id}`);
});

test('translator fills parameters and falls back', () => {
  const t = makeTranslator('nb');
  expect(t('time.validAt', { time: 'tor 14:00' })).toBe('Gyldig tor 14:00');
  expect(t('no.such.key')).toBe('no.such.key');
});

describe('ramps', () => {
  for (const family of RAMP_FAMILIES) {
    for (const layer of LAYER_IDS) {
      test(`${family}/${layer}: monotonic lightness (colour-blind safe ordering)`, () => {
        const ramp = getRamp(layer, family);
        expect(ramp.stops.map((s) => s.value)).toEqual(VALUE_STOPS[layer]);
        const lum = ramp.stops.map((s) => luminance(s.color));
        const increasing = lum.every((l, i) => i === 0 || l >= lum[i - 1]! - 0.02);
        const decreasing = lum.every((l, i) => i === 0 || l <= lum[i - 1]! + 0.02);
        expect(increasing || decreasing).toBe(true);
        expect(rampTexels(ramp).length).toBe(256 * 4);
      });
    }
  }
});
