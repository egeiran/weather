import { describe, expect, it } from 'vitest';

import { LatestOnly } from '../src/core/latest';

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('LatestOnly (live pin drag)', () => {
  it('keeps one call in flight and collapses queued inputs to the newest', async () => {
    const calls: number[] = [];
    const pending = new Map<number, ReturnType<typeof deferred<string>>>();
    const results: [number, string][] = [];
    const r = new LatestOnly<number, string>(
      (i) => {
        calls.push(i);
        const d = deferred<string>();
        pending.set(i, d);
        return d.promise;
      },
      (i, o) => results.push([i, o]),
    );
    r.push(1);
    r.push(2);
    r.push(3);
    expect(calls).toEqual([1]);
    pending.get(1)!.resolve('a');
    await flush();
    expect(calls).toEqual([1, 3]); // 2 was overtaken while 1 was in flight
    pending.get(3)!.resolve('c');
    await flush();
    expect(results).toEqual([
      [1, 'a'],
      [3, 'c'],
    ]);
  });

  it('answers cached lookups at once, every move', async () => {
    const results: number[] = [];
    const r = new LatestOnly<number, number>(
      async (i) => i * 10,
      (_i, o) => results.push(o),
    );
    for (const i of [1, 2, 3]) {
      r.push(i);
      await flush();
    }
    expect(results).toEqual([10, 20, 30]);
  });

  it('drops results and pending input after cancel, and reports errors', async () => {
    const d = deferred<string>();
    const results: string[] = [];
    const errors: number[] = [];
    let n = 0;
    const r = new LatestOnly<number, string>(
      (i) => (n++ === 0 ? d.promise : Promise.reject(new Error(`boom ${i}`))),
      (_i, o) => results.push(o),
      (i) => errors.push(i),
    );
    r.push(1);
    r.push(2);
    r.cancel(); // pin closed while 1 is in flight
    d.resolve('late');
    await flush();
    expect(results).toEqual([]);
    expect(n).toBe(1);
    r.push(5);
    await flush();
    expect(errors).toEqual([5]);
  });
});
