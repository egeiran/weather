import { setWorkerUrl } from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import 'maplibre-gl/dist/maplibre-gl.css';
import 'weather-layers/styles.css';
import './app.css';
import { App } from './App';

// MapLibre 6 finds its worker next to its own module; once bundled that path is gone, so point
// it at the emitted worker file explicitly (works in dev and in a static build).
setWorkerUrl(maplibreWorkerUrl);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
