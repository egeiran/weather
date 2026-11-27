/**
 * The MapLibre custom layer that draws one weather layer: colour field (+ threshold marking),
 * direction arrows and (optionally) particles. Everything is drawn from value tiles on the GPU.
 */
import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MapLibreMap,
} from 'maplibre-gl';

import { joinUrl } from '../manifest';
import { rampTexels, type Ramp } from '../ramps';
import { parentTile, tileExtent, tileUrl, tileZoomFor, visibleTiles, type TileId } from '../tiles';
import type { ResolvedTime } from '../time';
import type { TileStore } from '../tileStore';
import type { LayerId, LayerInfo, Segment } from '../types';
import { ParticleSystem } from './particles';
import { ARROW_FS, ARROW_VS, FIELD_FS, FIELD_VS, VECTOR_FS, arrowGlyph } from './shaders';
import {
  createBuffer,
  createProgram,
  createTarget,
  createTexture,
  deleteTarget,
  toFloat32,
  uploadImage,
  type Program,
  type Target,
} from './util';

export type ThresholdStyle = 'hatch' | 'tint' | 'contour';
export type Theme = 'light' | 'dark';

export interface Scene {
  visible: boolean;
  layerId: LayerId;
  layer: LayerInfo | null;
  resolved: ResolvedTime | null;
  /** Last fully drawn time; its tiles are used as fallback while new ones load. */
  fallback: ResolvedTime | null;
  /** Next time step, prefetched when the current one is complete. */
  prefetch: ResolvedTime | null;
  baseUrl: string;
  ramp: Ramp;
  opacity: number;
  threshold: number | null;
  thresholdStyle: ThresholdStyle;
  theme: Theme;
  arrows: boolean;
  particles: boolean;
  tileZoomOffset: number;
}

interface Draw {
  texture: WebGLTexture;
  extent: [number, number, number, number];
  uvOffset: [number, number];
  uvScale: number;
  segment: Segment;
}

/** Which channel gives the motion magnitude for arrows/particles, and its scaling. */
const VECTOR_SPEC: Record<LayerId, { mag: string; factor: number; maxMag: number }> = {
  wind: { mag: 'wind_speed', factor: 1, maxMag: 25 },
  gust: { mag: 'wind_speed', factor: 1, maxMag: 25 },
  // Waves move at roughly the deep-water phase speed c = g T / 2 pi = 1.56 T (m/s).
  wave_height: { mag: 'wave_period', factor: 1.56, maxMag: 28 },
  wave_period: { mag: 'wave_period', factor: 1.56, maxMag: 28 },
  swell: { mag: 'swell_period', factor: 1.56, maxMag: 28 },
  current: { mag: 'current_speed', factor: 1, maxMag: 2.5 },
};

const QUAD = new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]);
const ARROW_SPACING_CSS = 46;

export class WeatherRenderer implements CustomLayerInterface {
  readonly id: string;
  readonly type = 'custom' as const;
  readonly renderingMode = '2d' as const;

  private map: MapLibreMap | null = null;
  private gl: WebGL2RenderingContext | null = null;
  private fieldProg: Program | null = null;
  private vectorProg: Program | null = null;
  private arrowProg: Program | null = null;
  private quadBuf: WebGLBuffer | null = null;
  private glyphBuf: WebGLBuffer | null = null;
  private anchorBuf: WebGLBuffer | null = null;
  private anchorCount = 0;
  private rampTex: WebGLTexture | null = null;
  private rampKey = '';
  private vectorTarget: Target | null = null;
  private draws: Draw[] = [];
  private vectorReady = false;
  private particles: ParticleSystem | null = null;
  /** True when every wanted tile of the current time is drawn at its own zoom. */
  complete = false;
  lastError: string | null = null;

  constructor(
    id: string,
    private store: TileStore,
    private getScene: () => Scene,
    private onFrame: (info: { complete: boolean; tiles: number }) => void,
  ) {
    this.id = id;
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext) {
    this.map = map;
    this.gl = gl;
    this.fieldProg = createProgram(gl, FIELD_VS, FIELD_FS);
    this.vectorProg = createProgram(gl, FIELD_VS, VECTOR_FS);
    this.arrowProg = createProgram(gl, ARROW_VS, ARROW_FS);
    this.quadBuf = createBuffer(gl, QUAD);
    this.glyphBuf = createBuffer(gl, arrowGlyph());
    this.anchorBuf = gl.createBuffer();
    this.particles = new ParticleSystem(gl);
  }

  onRemove(_map: MapLibreMap, gl: WebGL2RenderingContext) {
    for (const p of [this.fieldProg, this.vectorProg, this.arrowProg])
      if (p) gl.deleteProgram(p.program);
    for (const b of [this.quadBuf, this.glyphBuf, this.anchorBuf]) if (b) gl.deleteBuffer(b);
    if (this.rampTex) gl.deleteTexture(this.rampTex);
    deleteTarget(gl, this.vectorTarget);
    this.particles?.destroy();
    this.store.destroy((t) => gl.deleteTexture(t));
    this.map = null;
    this.gl = null;
  }

  // -- per-frame -------------------------------------------------------------------------

  prerender(gl: WebGL2RenderingContext, args: CustomRenderMethodInput) {
    const scene = this.getScene();
    this.draws = [];
    this.vectorReady = false;
    if (!scene.visible || !this.map) return;
    this.store.tick();
    this.store.uploadPending((bm) => uploadImage(gl, bm));
    this.store.prune((t) => gl.deleteTexture(t));
    if (this.store.hasPendingUploads()) this.map.triggerRepaint();
    this.updateRamp(gl, scene.ramp);
    this.draws = this.collectDraws(scene);
    const needVectors = scene.arrows || scene.particles;
    if (needVectors && this.draws.length) {
      this.renderVectors(gl, args, scene);
      this.vectorReady = true;
      if (scene.arrows) this.updateAnchors(gl);
    }
    if (scene.particles && this.vectorReady && this.vectorTarget && this.particles) {
      this.particles.step(
        gl,
        this.map,
        this.vectorTarget,
        scene.theme,
        VECTOR_SPEC[scene.layerId].maxMag,
      );
      this.map.triggerRepaint(); // keep animating
    } else {
      this.particles?.reset();
    }
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput) {
    const scene = this.getScene();
    if (!scene.visible || !this.draws.length) return;
    const matrix = toFloat32(args.defaultProjectionData.mainMatrix);
    this.renderField(gl, matrix, scene);
    if (scene.particles && this.vectorReady && this.particles) this.particles.composite(gl);
    if (scene.arrows && this.vectorReady) this.renderArrows(gl, matrix, scene);
  }

  // -- tiles -----------------------------------------------------------------------------

  private viewBounds(): [number, number, number, number] {
    const b = this.map!.getBounds();
    return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  }

  private collectDraws(scene: Scene): Draw[] {
    const { resolved } = scene;
    if (!resolved || !this.map) {
      this.complete = true;
      this.onFrame({ complete: true, tiles: 0 });
      return [];
    }
    const seg = resolved.segment;
    const z = tileZoomFor(this.map.getZoom(), seg, scene.tileZoomOffset);
    const view = this.viewBounds();
    const tiles = visibleTiles(view, z, seg);
    const draws: Draw[] = [];
    const wanted = new Set<string>();
    let complete = true;
    const urlOf = (r: ResolvedTime, t: TileId) =>
      joinUrl(scene.baseUrl, tileUrl(r.segment.tiles, r.timeKey, t));
    for (const t of tiles) {
      const url = urlOf(resolved, t);
      wanted.add(url);
      const e = this.store.request(url, 0);
      if (e.state === 'ready' && e.texture) {
        draws.push({
          texture: e.texture,
          extent: tileExtent(t),
          uvOffset: [0, 0],
          uvScale: 1,
          segment: seg,
        });
        continue;
      }
      if (e.state === 'missing' || e.state === 'error') continue;
      complete = false;
      // Fallback 1: an ancestor tile of the same time that is already loaded.
      const anc = this.findAncestor(t, seg.minzoom, (p) => urlOf(resolved, p));
      if (anc) {
        draws.push({ ...anc, segment: seg });
        continue;
      }
      // Fallback 2: the previously shown time at the same position (avoids flicker).
      if (scene.fallback && scene.fallback.timeKey !== resolved.timeKey) {
        const fseg = scene.fallback.segment;
        const fz = tileZoomFor(this.map.getZoom(), fseg, scene.tileZoomOffset);
        for (const ft of visibleTiles(tileBBox(t), fz, fseg)) {
          const fe = this.store.get(urlOf(scene.fallback, ft));
          if (fe?.state === 'ready' && fe.texture) {
            draws.push({
              texture: fe.texture,
              extent: tileExtent(ft),
              uvOffset: [0, 0],
              uvScale: 1,
              segment: fseg,
            });
          }
        }
      }
    }
    // Prefetch the next step once the current one is complete (smooth playback).
    if (complete && scene.prefetch) {
      for (const t of visibleTiles(
        view,
        tileZoomFor(this.map.getZoom(), scene.prefetch.segment, scene.tileZoomOffset),
        scene.prefetch.segment,
      )) {
        const url = urlOf(scene.prefetch, t);
        wanted.add(url);
        this.store.request(url, 10);
      }
    }
    this.store.cancelQueuedExcept(wanted);
    this.complete = complete;
    this.onFrame({ complete, tiles: tiles.length });
    // Draw coarser (fallback) tiles first so sharper ones end up on top.
    return draws.sort((a, b) => b.extent[2] - b.extent[0] - (a.extent[2] - a.extent[0]));
  }

  private findAncestor(t: TileId, minzoom: number, url: (p: TileId) => string) {
    let p = parentTile(t);
    while (p && p.z >= minzoom) {
      const e = this.store.get(url(p));
      if (e?.state === 'ready' && e.texture) {
        const dz = t.z - p.z;
        const n = 2 ** dz;
        return {
          texture: e.texture,
          extent: tileExtent(t),
          uvOffset: [(t.x - p.x * n) / n, (t.y - p.y * n) / n] as [number, number],
          uvScale: 1 / n,
        };
      }
      p = parentTile(p);
    }
    return null;
  }

  // -- passes ----------------------------------------------------------------------------

  private updateRamp(gl: WebGL2RenderingContext, ramp: Ramp) {
    const key = `${ramp.layer}:${ramp.family}`;
    if (key === this.rampKey && this.rampTex) return;
    if (this.rampTex) gl.deleteTexture(this.rampTex);
    this.rampTex = createTexture(gl, gl.LINEAR, 256, 1, rampTexels(ramp));
    this.rampKey = key;
  }

  private bindQuad(gl: WebGL2RenderingContext, prog: Program) {
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    const loc = prog.attribs.a_pos!;
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  }

  private setTileUniforms(gl: WebGL2RenderingContext, prog: Program, d: Draw) {
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, d.texture);
    gl.uniform1i(prog.uniforms.u_tile!, 0);
    gl.uniform4f(prog.uniforms.u_extent!, ...d.extent);
    gl.uniform2f(prog.uniforms.u_uvOffset!, ...d.uvOffset);
    gl.uniform2f(prog.uniforms.u_uvScale!, d.uvScale, d.uvScale);
  }

  private renderField(gl: WebGL2RenderingContext, matrix: Float32Array, scene: Scene) {
    const prog = this.fieldProg!;
    gl.useProgram(prog.program);
    this.bindQuad(gl, prog);
    gl.uniformMatrix4fv(prog.uniforms.u_matrix!, false, matrix);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.rampTex);
    gl.uniform1i(prog.uniforms.u_ramp!, 1);
    gl.uniform2f(prog.uniforms.u_rampRange!, scene.ramp.min, scene.ramp.max);
    gl.uniform1f(prog.uniforms.u_opacity!, scene.opacity);
    gl.uniform1f(prog.uniforms.u_threshold!, scene.threshold ?? -1e30);
    gl.uniform1i(
      prog.uniforms.u_thresholdStyle!,
      scene.thresholdStyle === 'hatch' ? 0 : scene.thresholdStyle === 'tint' ? 1 : 2,
    );
    const mark = scene.theme === 'dark' ? [1, 1, 1, 0.9] : [0.08, 0.08, 0.12, 0.85];
    gl.uniform4f(prog.uniforms.u_markColor!, mark[0]!, mark[1]!, mark[2]!, mark[3]!);
    gl.uniform1f(prog.uniforms.u_pixelRatio!, this.map?.getPixelRatio() ?? 1);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    for (const d of this.draws) {
      const ch = d.segment.channels[d.segment.value_channel]!;
      gl.uniform1i(prog.uniforms.u_valueChannel!, d.segment.value_channel);
      gl.uniform2f(prog.uniforms.u_decode!, ch.scale, ch.offset);
      this.setTileUniforms(gl, prog, d);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }

  private renderVectors(gl: WebGL2RenderingContext, args: CustomRenderMethodInput, scene: Scene) {
    const w = Math.max(1, Math.round(gl.drawingBufferWidth / 2));
    const h = Math.max(1, Math.round(gl.drawingBufferHeight / 2));
    if (!this.vectorTarget || this.vectorTarget.width !== w || this.vectorTarget.height !== h) {
      deleteTarget(gl, this.vectorTarget);
      this.vectorTarget = createTarget(gl, w, h, gl.LINEAR);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.vectorTarget.fbo);
    gl.viewport(0, 0, w, h);
    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    gl.clearColor(0.5, 0.5, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const prog = this.vectorProg!;
    gl.useProgram(prog.program);
    this.bindQuad(gl, prog);
    gl.uniformMatrix4fv(
      prog.uniforms.u_matrix!,
      false,
      toFloat32(args.defaultProjectionData.mainMatrix),
    );
    const spec = VECTOR_SPEC[scene.layerId];
    gl.uniform1f(prog.uniforms.u_magFactor!, spec.factor);
    gl.uniform1f(prog.uniforms.u_maxMag!, spec.maxMag);
    for (const d of this.draws) {
      const chans = d.segment.channels;
      const mi = Math.max(
        0,
        chans.findIndex((c) => c.name === spec.mag),
      );
      const dch = chans[d.segment.direction_channel]!;
      const conv = scene.layer?.direction_convention ?? 'from';
      gl.uniform1i(prog.uniforms.u_magChannel!, mi);
      gl.uniform2f(prog.uniforms.u_magDecode!, chans[mi]!.scale, chans[mi]!.offset);
      gl.uniform1i(prog.uniforms.u_dirChannel!, d.segment.direction_channel);
      gl.uniform1f(prog.uniforms.u_dirScale!, dch.scale);
      gl.uniform1f(prog.uniforms.u_dirToOffset!, conv === 'from' ? 180 : 0);
      this.setTileUniforms(gl, prog, d);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }

  private updateAnchors(gl: WebGL2RenderingContext) {
    const map = this.map!;
    const zoom = map.getZoom();
    const worldCss = 512 * 2 ** zoom;
    const k = Math.floor(Math.log2(worldCss / ARROW_SPACING_CSS));
    const cell = 2 ** -k; // mercator units; on screen between 1x and 2x the spacing
    const c = map.getCanvas();
    const corners = [
      [0, 0],
      [c.clientWidth, 0],
      [0, c.clientHeight],
      [c.clientWidth, c.clientHeight],
    ].map(([x, y]) => map.unproject([x!, y!]));
    const xs = corners.map((p) => (p.lng + 180) / 360);
    const ys = corners.map((p) => {
      const s = Math.sin((Math.max(-85, Math.min(85, p.lat)) * Math.PI) / 180);
      return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
    });
    const i0 = Math.floor(Math.min(...xs) / cell);
    const i1 = Math.ceil(Math.max(...xs) / cell);
    const j0 = Math.floor(Math.min(...ys) / cell);
    const j1 = Math.ceil(Math.max(...ys) / cell);
    const count = (i1 - i0 + 1) * (j1 - j0 + 1);
    if (count > 6000) {
      this.anchorCount = 0;
      return;
    }
    const data = new Float32Array(count * 2);
    let n = 0;
    for (let j = j0; j <= j1; j++) {
      for (let i = i0; i <= i1; i++) {
        // stagger every other row for a less mechanical look
        const ox = (j & 1) * 0.5;
        data[n++] = (i + 0.5 + ox) * cell;
        data[n++] = (j + 0.5) * cell;
      }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, this.anchorBuf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
    this.anchorCount = count;
  }

  private renderArrows(gl: WebGL2RenderingContext, matrix: Float32Array, scene: Scene) {
    if (!this.anchorCount || !this.vectorTarget) return;
    const prog = this.arrowProg!;
    gl.useProgram(prog.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.glyphBuf);
    const vloc = prog.attribs.a_vertex!;
    gl.enableVertexAttribArray(vloc);
    gl.vertexAttribPointer(vloc, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(vloc, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.anchorBuf);
    const aloc = prog.attribs.a_anchor!;
    gl.enableVertexAttribArray(aloc);
    gl.vertexAttribPointer(aloc, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(aloc, 1);
    gl.uniformMatrix4fv(prog.uniforms.u_matrix!, false, matrix);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.vectorTarget.tex);
    gl.uniform1i(prog.uniforms.u_data!, 0);
    gl.uniform2f(prog.uniforms.u_viewport!, gl.drawingBufferWidth, gl.drawingBufferHeight);
    const ratio = this.map?.getPixelRatio() ?? 1;
    gl.uniform1f(prog.uniforms.u_size!, 15 * ratio);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    const dark = scene.theme === 'dark';
    // halo, then glyph
    const halo = dark ? [0.04, 0.06, 0.09, 0.55] : [1, 1, 1, 0.7];
    const fill = dark ? [0.94, 0.96, 0.98, 0.9] : [0.09, 0.13, 0.17, 0.78];
    gl.uniform1f(prog.uniforms.u_grow!, 1.2 * ratio);
    gl.uniform4f(prog.uniforms.u_color!, halo[0]!, halo[1]!, halo[2]!, halo[3]!);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 9, this.anchorCount);
    gl.uniform1f(prog.uniforms.u_grow!, 0);
    gl.uniform4f(prog.uniforms.u_color!, fill[0]!, fill[1]!, fill[2]!, fill[3]!);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 9, this.anchorCount);
    gl.vertexAttribDivisor(aloc, 0);
    gl.disableVertexAttribArray(aloc);
  }
}

function tileBBox(t: TileId): [number, number, number, number] {
  const [x0, y0, x1, y1] = tileExtent(t);
  const lat = (y: number) => (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI;
  return [x0 * 360 - 180, lat(y1), x1 * 360 - 180, lat(y0)];
}
