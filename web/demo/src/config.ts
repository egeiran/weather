/** Demo configuration (Vite env vars, all optional). */
export const STYLE_LIGHT =
  import.meta.env.VITE_STYLE_LIGHT ?? 'https://tiles.openfreemap.org/styles/positron';
export const STYLE_DARK =
  import.meta.env.VITE_STYLE_DARK ?? 'https://tiles.openfreemap.org/styles/dark';
export const DATA_BASE_URL =
  import.meta.env.VITE_WEATHER_BASE_URL ?? `${import.meta.env.BASE_URL}weather-data/`;
export const DEMO_TOKEN = import.meta.env.VITE_DEMO_TOKEN ?? 'demo-token';

/** The host injects a fetch that adds its own auth; here a static demo bearer token. */
export const authFetch = (input: string, init?: RequestInit) =>
  fetch(input, {
    ...init,
    headers: {
      ...(init?.headers as Record<string, string> | undefined),
      Authorization: `Bearer ${DEMO_TOKEN}`,
    },
  });
