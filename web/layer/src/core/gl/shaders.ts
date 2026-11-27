/** GLSL ES 3.00 shaders. Value tiles: 258x258 RGBA8 (1-px border), NEAREST, codes 0..254, 255 = no data. */

const TILE_SAMPLING = /* glsl */ `
uniform highp sampler2D u_tile;
uniform vec2 u_uvOffset;
uniform vec2 u_uvScale;

float pick(vec4 t, int c) { return c == 0 ? t.r : (c == 1 ? t.g : t.b); }
float code(ivec2 q, int c) {
  q = clamp(q, ivec2(0), ivec2(257));
  return floor(pick(texelFetch(u_tile, q, 0), c) * 255.0 + 0.5);
}
// Tile-local uv (0..1, y down) -> continuous texel coordinate; texel j centre is at uv=(j-0.5)/256.
vec2 texelPos(vec2 uv) { return (u_uvOffset + uv * u_uvScale) * 256.0 + 0.5; }
`;

export const FIELD_VS = /* glsl */ `#version 300 es
in vec2 a_pos;
uniform mat4 u_matrix;
uniform vec4 u_extent;
out vec2 v_uv;
void main() {
  v_uv = a_pos;
  vec2 merc = mix(u_extent.xy, u_extent.zw, a_pos);
  gl_Position = u_matrix * vec4(merc, 0.0, 1.0);
}`;

/** Colour field with bilinear interpolation (manual, no-data aware) and threshold marking. */
export const FIELD_FS = /* glsl */ `#version 300 es
precision highp float;
${TILE_SAMPLING}
uniform sampler2D u_ramp;
uniform int u_valueChannel;
uniform vec2 u_decode;      // scale, offset
uniform vec2 u_rampRange;   // min, max
uniform float u_opacity;
uniform float u_threshold;  // < -1e29 = off
uniform int u_thresholdStyle; // 0 hatch+contour, 1 tint+contour, 2 contour only
uniform vec4 u_markColor;   // straight alpha
uniform float u_pixelRatio;
in vec2 v_uv;
out vec4 fragColor;

void main() {
  vec2 p = texelPos(v_uv);
  vec2 i0 = floor(p);
  vec2 f = p - i0;
  ivec2 b = ivec2(i0);
  float sum = 0.0;
  float wsum = 0.0;
  for (int dy = 0; dy < 2; dy++) {
    for (int dx = 0; dx < 2; dx++) {
      float c = code(b + ivec2(dx, dy), u_valueChannel);
      float w = (dx == 0 ? 1.0 - f.x : f.x) * (dy == 0 ? 1.0 - f.y : f.y);
      if (c < 254.5) { sum += w * (u_decode.y + u_decode.x * c); wsum += w; }
    }
  }
  if (wsum < 0.4) discard;
  float v = sum / wsum;
  float t = clamp((v - u_rampRange.x) / (u_rampRange.y - u_rampRange.x), 0.0, 1.0);
  vec4 col = texture(u_ramp, vec2(t * (255.0 / 256.0) + 0.5 / 256.0, 0.5));
  // Soft edge at the coast / domain border instead of blocky data pixels.
  col.a *= u_opacity * smoothstep(0.4, 0.6, wsum);
  // Marking colour adapts to the field underneath: light on dark colours, dark on light ones.
  float lum = dot(col.rgb, vec3(0.2126, 0.7152, 0.0722));
  vec3 mark = lum < 0.42 ? vec3(1.0) : u_markColor.rgb;
  if (u_threshold > -1e29) {
    float over = step(u_threshold, v);
    float fw = max(fwidth(v), 1e-5);
    float d = abs(v - u_threshold) / fw;
    float line = 1.0 - smoothstep(0.6 * u_pixelRatio, 1.6 * u_pixelRatio, d);
    if (u_thresholdStyle == 0) {
      // Diagonal stripes in screen space (constant density at every zoom).
      float k = fract((gl_FragCoord.x + gl_FragCoord.y) / (7.0 * u_pixelRatio));
      float stripe = 1.0 - smoothstep(0.14, 0.26, abs(k - 0.5));
      float hatch = over * stripe * u_markColor.a * 0.75;
      col.rgb = mix(col.rgb, mark, hatch);
      col.a = max(col.a, hatch);
    } else if (u_thresholdStyle == 1) {
      float tint = over * 0.45;
      col.rgb = mix(col.rgb, mark, tint);
      col.a = max(col.a, 0.55 * over);
    }
    col.rgb = mix(col.rgb, mark, line * u_markColor.a);
    col.a = max(col.a, line * u_markColor.a);
  }
  fragColor = vec4(col.rgb * col.a, col.a);
}`;

/**
 * Vector data pass: writes the motion vector (east, north), normalised by u_maxMag, into an
 * offscreen RGBA8 target: rg = vec/2+0.5, b = |vec|, a = valid. Used by arrows and particles.
 * u_mode: 0 = magnitude channel in its own unit; 1 = waves: speed = 1.56 * period (phase speed).
 */
export const VECTOR_FS = /* glsl */ `#version 300 es
precision highp float;
${TILE_SAMPLING}
uniform int u_magChannel;
uniform vec2 u_magDecode;
uniform int u_dirChannel;
uniform float u_dirScale;
uniform float u_dirToOffset;  // +180 for "from" conventions, 0 for "to"
uniform float u_magFactor;
uniform float u_maxMag;
in vec2 v_uv;
out vec4 fragColor;

void main() {
  vec2 p = texelPos(v_uv);
  vec2 i0 = floor(p);
  vec2 f = p - i0;
  ivec2 b = ivec2(i0);
  vec2 vsum = vec2(0.0);
  float wsum = 0.0;
  for (int dy = 0; dy < 2; dy++) {
    for (int dx = 0; dx < 2; dx++) {
      ivec2 q = b + ivec2(dx, dy);
      float cm = code(q, u_magChannel);
      float cd = code(q, u_dirChannel);
      float w = (dx == 0 ? 1.0 - f.x : f.x) * (dy == 0 ? 1.0 - f.y : f.y);
      if (cm < 254.5 && cd < 254.5) {
        float mag = (u_magDecode.y + u_magDecode.x * cm) * u_magFactor;
        float rad = radians(cd * u_dirScale + u_dirToOffset);
        vsum += w * mag * vec2(sin(rad), cos(rad));
        wsum += w;
      }
    }
  }
  if (wsum < 0.5) { fragColor = vec4(0.5, 0.5, 0.0, 0.0); return; }
  vec2 vec = vsum / wsum / u_maxMag;
  vec = clamp(vec, -1.0, 1.0);
  fragColor = vec4(vec * 0.5 + 0.5, clamp(length(vec), 0.0, 1.0), 1.0);
}`;

/** Arrows: one instance per anchor (mercator), glyph rotated to the local flow direction. */
export const ARROW_VS = /* glsl */ `#version 300 es
in vec2 a_vertex;   // glyph space: shaft along +y, length 1
in vec2 a_anchor;   // mercator 0..1
uniform mat4 u_matrix;
uniform sampler2D u_data;
uniform vec2 u_viewport;   // drawing buffer size (px)
uniform float u_size;      // max glyph length (px)
uniform float u_grow;      // halo growth (px)
out float v_alpha;

vec2 toScreen(vec2 merc) {
  vec4 c = u_matrix * vec4(merc, 0.0, 1.0);
  return (c.xy / c.w * 0.5 + 0.5) * u_viewport;
}

void main() {
  vec4 c = u_matrix * vec4(a_anchor, 0.0, 1.0);
  vec2 ndc = c.xy / c.w;
  vec4 d = texture(u_data, ndc * 0.5 + 0.5);
  if (d.a < 0.5 || c.w <= 0.0 || abs(ndc.x) > 1.05 || abs(ndc.y) > 1.05) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_alpha = 0.0;
    return;
  }
  vec2 vec = (d.rg - 0.5) * 2.0;
  float mag = length(vec);
  // Screen directions of geographic east and north at the anchor (handles bearing/pitch).
  float eps = 1e-6;
  vec2 s0 = toScreen(a_anchor);
  vec2 east = normalize(toScreen(a_anchor + vec2(eps, 0.0)) - s0);
  vec2 north = normalize(toScreen(a_anchor - vec2(0.0, eps)) - s0);
  vec2 dirS = mag > 1e-4 ? normalize(vec.x * east + vec.y * north) : north;
  vec2 side = vec2(dirS.y, -dirS.x);
  float len = u_size * (0.5 + 0.5 * clamp(mag * 1.6, 0.0, 1.0));
  vec2 g = a_vertex;
  vec2 off = dirS * (g.y * len) + side * (g.x * u_size * 0.55);
  // halo: push vertices outwards a little
  off += (dirS * sign(g.y) * step(0.001, abs(g.y)) + side * sign(g.x)) * u_grow;
  vec2 screen = s0 + off;
  gl_Position = vec4((screen / u_viewport) * 2.0 - 1.0, 0.0, 1.0);
  v_alpha = mag < 0.02 ? 0.35 : 1.0;
}`;

export const ARROW_FS = /* glsl */ `#version 300 es
precision mediump float;
uniform vec4 u_color; // straight alpha
in float v_alpha;
out vec4 fragColor;
void main() {
  float a = u_color.a * v_alpha;
  fragColor = vec4(u_color.rgb * a, a);
}`;

/** Arrow glyph as triangles: shaft (rectangle) + head (triangle). Units: length 1 along +y. */
export function arrowGlyph(): Float32Array {
  const w = 0.09; // half shaft width (relative to size*0.55)
  const hw = 0.42; // half head width
  const y0 = -0.5;
  const y1 = 0.12;
  const y2 = 0.5;
  // prettier-ignore
  return new Float32Array([
    -w, y0,  w, y0,  w, y1,
    -w, y0,  w, y1, -w, y1,
    -hw, y1, hw, y1, 0, y2,
  ]);
}
