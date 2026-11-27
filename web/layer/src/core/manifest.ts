import type { FetchFn, LayerId, Manifest } from './types';

export const SUPPORTED_MAJOR = 1;

export class ManifestError extends Error {}

/** Join a base URL and a relative path from the manifest. */
export function joinUrl(base: string, path: string): string {
  if (/^[a-z]+:\/\//i.test(path) || path.startsWith('/')) return path;
  return base.endsWith('/') ? base + path : `${base}/${path}`;
}

export function checkManifest(m: unknown): Manifest {
  if (!m || typeof m !== 'object') throw new ManifestError('manifest is not an object');
  const mm = m as Partial<Manifest>;
  const version = String(mm.schema_version ?? '');
  const major = Number(version.split('.')[0]);
  if (major !== SUPPORTED_MAJOR) {
    throw new ManifestError(`unsupported manifest schema ${version} (need ${SUPPORTED_MAJOR}.x)`);
  }
  if (!mm.layers || !mm.tile || !mm.sources) throw new ManifestError('manifest is incomplete');
  return mm as Manifest;
}

export async function loadManifest(
  fetchFn: FetchFn,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<Manifest> {
  const res = await fetchFn(joinUrl(baseUrl, 'manifest.json'), { signal, cache: 'no-cache' });
  if (!res.ok) throw new ManifestError(`manifest: HTTP ${res.status}`);
  return checkManifest(await res.json());
}

export function availableLayers(m: Manifest): LayerId[] {
  return (Object.keys(m.layers) as LayerId[]).filter((k) => m.layers[k]?.segments.length);
}
