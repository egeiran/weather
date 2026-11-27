/**
 * Particles in the "webgl-wind" style: particle positions live in a state texture (16-bit
 * fixed point in RGBA8), are advected on the GPU by the vector field target, and are drawn
 * into a fading trail texture that is composited over the map.
 * Positions are in screen uv (0..1, y up); trails are cleared whenever the camera moves.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

import type { Theme } from './renderer';
import {
  createBuffer,
  createProgram,
  createTarget,
  deleteTarget,
  type Program,
  type Target,
} from './util';

const QUAD_VS = /* glsl */ `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() { v_uv = a_pos; gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0); }`;

const DECODE = /* glsl */ `
vec2 decodePos(vec4 c) { return vec2(c.r / 255.0 + c.b, c.g / 255.0 + c.a); }
vec4 encodePos(vec2 p) { return vec4(fract(p * 255.0), floor(p * 255.0) / 255.0); }
float rand(vec2 co) { return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453); }
`;

const UPDATE_FS = /* glsl */ `#version 300 es
precision highp float;
uniform sampler2D u_state;
uniform sampler2D u_vectors;
uniform vec2 u_east;      // screen-uv direction of geographic east (unit, aspect-corrected)
uniform vec2 u_north;
uniform float u_speed;    // uv per frame at full magnitude
uniform float u_seed;
uniform float u_dropRate;
uniform float u_dropBump;
in vec2 v_uv;
out vec4 fragColor;
${DECODE}
void main() {
  vec2 pos = decodePos(texture(u_state, v_uv));
  vec4 d = texture(u_vectors, pos);
  vec2 vel = (d.rg - 0.5) * 2.0;
  // Weak flows still draw visible streaks (Windy-like): screen speed ~ |v|^0.6.
  float m = length(vel);
  vec2 dir = m > 1e-4 ? vel / m : vec2(0.0);
  vec2 eff = dir * pow(m, 0.6);
  vec2 step = (eff.x * u_east + eff.y * u_north) * u_speed;
  vec2 np = pos + step;
  vec2 seed = (pos + v_uv) * u_seed;
  float drop = u_dropRate + length(vel) * u_dropBump;
  bool respawn = rand(seed) < drop || d.a < 0.5 || np.x < 0.0 || np.x > 1.0 || np.y < 0.0 || np.y > 1.0;
  if (respawn) np = vec2(rand(seed + 1.3), rand(seed + 2.1));
  fragColor = encodePos(clamp(np, 0.0, 1.0));
}`;

const DRAW_VS = /* glsl */ `#version 300 es
uniform sampler2D u_state;
uniform sampler2D u_vectors;
uniform float u_res;
uniform float u_pointSize;
out float v_valid;
out float v_mag;
${DECODE}
void main() {
  int i = gl_VertexID;
  vec2 uv = (vec2(float(i % int(u_res)), float(i / int(u_res))) + 0.5) / u_res;
  vec2 pos = decodePos(texture(u_state, uv));
  vec4 d = texture(u_vectors, pos);
  v_valid = d.a;
  v_mag = d.b;
  gl_PointSize = u_pointSize;
  gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}`;

const DRAW_FS = /* glsl */ `#version 300 es
precision mediump float;
uniform vec4 u_color;
in float v_valid;
in float v_mag;
out vec4 fragColor;
void main() {
  if (v_valid < 0.5) discard;
  // Subtle: faint in calm areas, clearer where it blows (Windy-like).
  float a = u_color.a * (0.25 + 0.75 * smoothstep(0.0, 0.55, v_mag));
  fragColor = vec4(u_color.rgb * a, a);
}`;

const FADE_FS = /* glsl */ `#version 300 es
precision mediump float;
uniform sampler2D u_tex;
uniform float u_opacity;
uniform float u_decay;  // subtracted per frame (in alpha units)
in vec2 v_uv;
out vec4 fragColor;
void main() {
  vec4 c = texture(u_tex, v_uv) * u_opacity;
  // A pure multiply stalls at small 8-bit values (x * 0.96 rounds back to x) and leaves a haze;
  // subtracting a little each frame guarantees the trail fades out completely.
  float a = max(c.a - u_decay, 0.0);
  c.rgb = c.a > 0.0 ? c.rgb * (a / c.a) : vec3(0.0);
  fragColor = vec4(c.rgb, a);
}`;

export class ParticleSystem {
  private updateProg: Program;
  private drawProg: Program;
  private fadeProg: Program;
  private quad: WebGLBuffer;
  private state: [Target, Target] | null = null;
  private trails: [Target, Target] | null = null;
  private res = 0;
  private lastCamera = '';
  private frame = 0;

  constructor(private gl: WebGL2RenderingContext) {
    this.updateProg = createProgram(gl, QUAD_VS, UPDATE_FS);
    this.drawProg = createProgram(gl, DRAW_VS, DRAW_FS);
    this.fadeProg = createProgram(gl, QUAD_VS, FADE_FS);
    this.quad = createBuffer(gl, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]));
  }

  private ensureState(count: number) {
    const gl = this.gl;
    const res = Math.ceil(Math.sqrt(count));
    if (this.state && this.res === res) return;
    if (this.state) this.state.forEach((t) => deleteTarget(gl, t));
    const data = new Uint8Array(res * res * 4);
    for (let i = 0; i < data.length; i++) data[i] = Math.floor(Math.random() * 256);
    const a = createTarget(gl, res, res, gl.NEAREST);
    gl.bindTexture(gl.TEXTURE_2D, a.tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, res, res, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    const b = createTarget(gl, res, res, gl.NEAREST);
    this.state = [a, b];
    this.res = res;
  }

  private ensureTrails(w: number, h: number) {
    const gl = this.gl;
    if (this.trails && this.trails[0].width === w && this.trails[0].height === h) return;
    if (this.trails) this.trails.forEach((t) => deleteTarget(gl, t));
    this.trails = [createTarget(gl, w, h, gl.NEAREST), createTarget(gl, w, h, gl.NEAREST)];
    this.clearTrails();
  }

  private clearTrails() {
    const gl = this.gl;
    for (const t of this.trails ?? []) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, t.fbo);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }
  }

  reset() {
    this.lastCamera = '';
  }

  private quadAttrib(prog: Program) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    const loc = prog.attribs.a_pos;
    if (loc !== undefined && loc >= 0) {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    }
  }

  /** Advance one frame and draw into the trail texture (call inside prerender). */
  step(
    gl: WebGL2RenderingContext,
    map: MapLibreMap,
    vectors: Target,
    theme: Theme,
    tuning: { speed: number; alpha: number } = { speed: 1, alpha: 1 },
  ) {
    const w = gl.drawingBufferWidth;
    const h = gl.drawingBufferHeight;
    const ratio = map.getPixelRatio();
    const cssArea = (w * h) / (ratio * ratio);
    this.ensureState(Math.min(12000, Math.max(1500, cssArea / 110)));
    this.ensureTrails(w, h);
    const camera = `${map.getCenter().toArray().join()}|${map.getZoom()}|${map.getBearing()}|${map.getPitch()}|${w}x${h}`;
    if (camera !== this.lastCamera) {
      this.clearTrails();
      this.lastCamera = camera;
    }
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);

    // 1) update positions
    const [cur, next] = this.state!;
    gl.bindFramebuffer(gl.FRAMEBUFFER, next.fbo);
    gl.viewport(0, 0, this.res, this.res);
    gl.disable(gl.BLEND);
    const up = this.updateProg;
    gl.useProgram(up.program);
    this.quadAttrib(up);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, cur.tex);
    gl.uniform1i(up.uniforms.u_state!, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, vectors.tex);
    gl.uniform1i(up.uniforms.u_vectors!, 1);
    // Screen-uv directions of east and north (bearing aware, aspect corrected).
    const b = (map.getBearing() * Math.PI) / 180;
    const aspect = w / h;
    gl.uniform2f(up.uniforms.u_east!, Math.cos(b) / aspect, Math.sin(b));
    gl.uniform2f(up.uniforms.u_north!, -Math.sin(b) / aspect, Math.cos(b));
    gl.uniform1f(up.uniforms.u_speed!, 0.0016 * tuning.speed);
    gl.uniform1f(up.uniforms.u_seed!, Math.random() + 0.5);
    gl.uniform1f(up.uniforms.u_dropRate!, 0.004);
    gl.uniform1f(up.uniforms.u_dropBump!, 0.01);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    this.state = [next, cur];

    // 2) fade previous trails into the other trail target, then draw particles on top
    const [trailA, trailB] = this.trails!;
    gl.bindFramebuffer(gl.FRAMEBUFFER, trailB.fbo);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const fade = this.fadeProg;
    gl.useProgram(fade.program);
    this.quadAttrib(fade);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, trailA.tex);
    gl.uniform1i(fade.uniforms.u_tex!, 0);
    gl.uniform1f(fade.uniforms.u_opacity!, 0.96);
    gl.uniform1f(fade.uniforms.u_decay!, 1.5 / 255);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    const dp = this.drawProg;
    gl.useProgram(dp.program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.state[0].tex);
    gl.uniform1i(dp.uniforms.u_state!, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, vectors.tex);
    gl.uniform1i(dp.uniforms.u_vectors!, 1);
    gl.uniform1f(dp.uniforms.u_res!, this.res);
    gl.uniform1f(dp.uniforms.u_pointSize!, Math.max(1, 0.9 * ratio));
    // Thin, translucent streaks: white on dark maps, slate on light ones.
    const color = theme === 'dark' ? [1, 1, 1, 0.5] : [0.1, 0.16, 0.23, 0.36];
    gl.uniform4f(dp.uniforms.u_color!, color[0]!, color[1]!, color[2]!, color[3]! * tuning.alpha);
    gl.drawArrays(gl.POINTS, 0, this.res * this.res);
    this.trails = [trailB, trailA];
    this.frame++;
  }

  /** Composite the trails over the map (call inside render). */
  composite(gl: WebGL2RenderingContext) {
    if (!this.trails) return;
    const fade = this.fadeProg;
    gl.useProgram(fade.program);
    this.quadAttrib(fade);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.trails[0].tex);
    gl.uniform1i(fade.uniforms.u_tex!, 0);
    gl.uniform1f(fade.uniforms.u_opacity!, 0.9);
    gl.uniform1f(fade.uniforms.u_decay!, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  destroy() {
    const gl = this.gl;
    this.state?.forEach((t) => deleteTarget(gl, t));
    this.trails?.forEach((t) => deleteTarget(gl, t));
    gl.deleteProgram(this.updateProg.program);
    gl.deleteProgram(this.drawProg.program);
    gl.deleteProgram(this.fadeProg.program);
    gl.deleteBuffer(this.quad);
  }
}
