import { VERSION } from '../src/index';

test('module loads', () => {
  expect(VERSION).toBe('0.1.0');
});
