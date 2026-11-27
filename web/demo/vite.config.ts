import { createReadStream, existsSync, statSync } from 'node:fs';
import { resolve, sep } from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const repoRoot = resolve(__dirname, '../..');
const dataDir = resolve(repoRoot, process.env.WEATHER_LAYERS_OUTPUT_DIR ?? 'data/out');
const requireAuth = (process.env.WEATHER_DEMO_REQUIRE_AUTH ?? '1') !== '0';
const token = process.env.VITE_DEMO_TOKEN ?? 'demo-token';

const TYPES: Record<string, string> = {
  '.json': 'application/json',
  '.png': 'image/png',
  '.bin': 'application/octet-stream',
};

/**
 * Serves the pipeline output at /weather-data/ like a host backend would: static files,
 * optionally behind a bearer token (proves the injected-fetch hook), immutable caching for
 * run/series files and no-cache for the manifest.
 */
function weatherData(): Plugin {
  return {
    name: 'weather-data',
    configureServer(server) {
      server.middlewares.use('/weather-data', (req, res, next) => {
        const path = decodeURIComponent((req.url ?? '/').split('?')[0]!);
        const file = resolve(dataDir, '.' + path);
        if (!file.startsWith(dataDir + sep)) {
          res.statusCode = 400;
          return res.end();
        }
        if (requireAuth && req.headers.authorization !== `Bearer ${token}`) {
          res.statusCode = 401;
          return res.end('missing or wrong bearer token');
        }
        if (!existsSync(file) || !statSync(file).isFile()) {
          res.statusCode = 404;
          return res.end();
        }
        const ext = file.slice(file.lastIndexOf('.'));
        res.setHeader('Content-Type', TYPES[ext] ?? 'application/octet-stream');
        res.setHeader(
          'Cache-Control',
          path.endsWith('manifest.json') ? 'no-cache' : 'public, max-age=31536000, immutable',
        );
        res.setHeader('Content-Length', String(statSync(file).size));
        createReadStream(file).pipe(res);
        void next;
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), weatherData()],
  // maplibre-gl 6 loads its worker via import.meta.url; pre-bundling would break that path.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: { port: 5173, strictPort: true },
  preview: { port: 4173 },
});
