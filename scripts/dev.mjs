// One command for development: build the dev area if there is no data yet, then start the demo.
//   npm run dev            (or: make dev)
// Set WEATHER_LAYERS_AREA=coast to build the whole coast instead (takes ~5 min, ~1.9 GB download).
import { spawnSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const out = resolve(root, process.env.WEATHER_LAYERS_OUTPUT_DIR ?? 'data/out');

if (!existsSync(resolve(out, 'manifest.json'))) {
  console.log(`No pipeline output in ${out}; running the pipeline for the development area first…`);
  const r = spawnSync('uv', ['run', '--project', 'pipeline', 'weather-layers', 'run'], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, WEATHER_LAYERS_AREA: process.env.WEATHER_LAYERS_AREA ?? 'dev' },
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
} else {
  console.log(`Using existing pipeline output in ${out} (run \`make pipeline\` to refresh).`);
}

const vite = spawn('npm', ['run', 'dev', '-w', 'web/demo'], { cwd: root, stdio: 'inherit' });
vite.on('exit', (code) => process.exit(code ?? 0));
