"""
gpu_orb.py: everything Solu draws on the GPU.

  OrbMotion      the glass orb's colors, swirl, breathing and voice reaction
  StardustRiver  waving streams of sparkles behind the orb, in the orb's colors
  VoiceRings     rings that pulse out of the orb with Solu's voice
  Renderer       owns the OpenGL objects and draws a whole frame

All motion runs on time measured in double precision on the CPU and is
passed to the shaders already wrapped, so animation stays smooth after
weeks of uptime.
"""

import math
import os

# the Pi 4 GPU only advertises OpenGL 3.1, ModernGL wants 3.3; Mesa runs these shaders fine when told to
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "3.3")
os.environ.setdefault("MESA_GLSL_VERSION_OVERRIDE", "330")

import moderngl
import numpy as np

TAU = 2 * math.pi
NOISE_TIME_PERIOD = 867.0  # the 3D noise repeats exactly every 867 units of time, so wrapping there is seamless
BREATH_SECONDS = 4.0

# four flow colors per state, how fast the liquid moves, and how lively it is
STATES = {
    "sleep":  {"colors": ["#FFFFFF", "#AFC3E0", "#E4ECFA", "#8F9DB8"], "speed": 0.55, "energy": 0.15},
    "idle":   {"colors": ["#4DB8FF", "#2E5BFF", "#7AF0FF", "#8E6CFF"], "speed": 1.0,  "energy": 0.45},
    "think":  {"colors": ["#FFD86B", "#82F4FF", "#FF7BD5", "#8E6CFF"], "speed": 2.2,  "energy": 0.7},
    "speak":  {"colors": ["#B388FF", "#FF7BD5", "#5B4BFF", "#82F4FF"], "speed": 1.4,  "energy": 0.6},
    "joking": {"colors": ["#69F0AE", "#B2FF59", "#40C4FF", "#1DE9B6"], "speed": 1.5,  "energy": 0.7},
    "error":  {"colors": ["#FF5252", "#FF2E63", "#FF9A76", "#B0103A"], "speed": 1.2,  "energy": 0.6},
    "alarm":  {"colors": ["#FFC800", "#FF8A00", "#FFE680", "#FF5E3A"], "speed": 1.8,  "energy": 1.0},
}

# ------------------------------------------------------------------
# shaders
# ------------------------------------------------------------------

FULLSCREEN_VS = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

ORB_FS = """
#version 330
uniform vec2 u_res;        // render target size in pixels
uniform vec2 u_center;     // orb center in pixels
uniform float u_radius;    // orb radius in pixels
uniform float u_visible;   // 0..1, the orb fades out for sleep at night
uniform float u_energy;    // 0..1 how lively the state is
uniform float u_breath;    // -1..1, same breathing cycle as the orb's size
uniform float u_level;     // 0..1 voice loudness, makes the liquid surge
uniform float u_rot;       // how far the liquid has turned
uniform float u_twist;     // how much faster the middle turns than the edge
uniform vec3 u_z;          // noise time for the warp and the two ribbon layers
uniform vec2 u_p0, u_p1, u_p2, u_p3;   // where each color lobe currently is
uniform vec3 u_c0, u_c1, u_c2, u_c3;
uniform vec4 u_ring_r;     // voice ring radii, in orb radii
uniform vec4 u_ring_a;     // voice ring brightness
uniform float u_frame;     // changes every frame, for dithering
out vec4 f_color;

// 3D simplex noise (Ashima Arts / Stefan Gustavson, MIT). Time is the third
// axis, so the shapes morph into new shapes instead of just sliding around.
vec4 permute(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0))
                                   + i.y + vec4(0.0, i1.y, i2.y, 1.0))
                                   + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    vec3 ns = (1.0 / 7.0) * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

float lobe(vec2 q, vec2 c, float sharpness) { vec2 d = q - c; return exp(-dot(d, d) * sharpness); }

void main() {
    vec2 frag = gl_FragCoord.xy;
    vec2 p = (frag - u_center) / u_radius;   // orb space: the orb is the unit circle, y points up
    float r = length(p);
    float px = 1.0 / u_radius;               // one pixel in orb units
    vec3 avg = (u_c0 + u_c1 + u_c2 + u_c3) * 0.25;

    // background: near-black with a soft glow from the orb that swells with breath and voice
    vec2 s = frag / u_res - 0.5;
    vec3 col = vec3(0.010, 0.013, 0.028) * (1.0 - 0.6 * dot(s, s));
    float halo = exp(-max(r - 1.0, 0.0) * 5.5);
    col += avg * halo * (0.10 + 0.08 * u_energy + 0.20 * u_level + 0.03 * u_breath) * u_visible;

    // voice rings: thin soft circles travelling outward from the glass
    float rings = 0.0;
    for (int i = 0; i < 4; i++) {
        float d = (r - u_ring_r[i]) * u_radius;           // distance from this ring in pixels
        rings += exp(-d * d / 18.0) * u_ring_a[i];
    }
    col += mix(u_c0, u_c2, 0.5) * rings * smoothstep(1.0, 1.03, r);

    if (r < 1.0 + 2.0 * px && u_visible > 0.001) {
        float z = sqrt(max(1.0 - r * r, 0.0));
        vec3 n = vec3(p, z);

        // looking through a thick glass ball: the inside bulges outward near the rim
        vec2 q = p * (0.62 + 0.38 * z);

        // stirred liquid: everything turns, and the middle turns faster than the edge
        float a = u_rot + u_twist * (1.0 - r * r);
        q = mat2(cos(a), sin(a), -sin(a), cos(a)) * q;

        // the liquid folds and morphs, more when breathing in and much more when speaking
        float amp = 0.30 + 0.22 * u_energy + 0.30 * u_level + 0.05 * u_breath;
        vec2 w = vec2(snoise(vec3(q * 1.2, u_z.x)), snoise(vec3(q * 1.2 + 7.3, u_z.x)));
        vec2 qw = q + w * amp;

        // where each color lives: four soft lobes drifting around, spreading on each breath
        float spread = 1.0 + 0.08 * u_breath + 0.12 * u_level;
        vec4 wgt = vec4(lobe(qw, u_p0 * spread, 3.0), lobe(qw, u_p1 * spread, 3.0),
                        lobe(qw, u_p2 * spread, 3.5), lobe(qw, u_p3 * spread, 2.5)) + 0.02;
        vec3 hue = (u_c0 * wgt.x + u_c1 * wgt.y + u_c2 * wgt.z + u_c3 * wgt.w) / dot(wgt, vec4(1.0));
        hue = max(mix(vec3(dot(hue, vec3(0.333))), hue, 1.3), 0.0);   // keep colors rich, not pastel

        // silk ribbons: bright where morphing noise crosses zero, dark glass in between
        float n1 = snoise(vec3(qw * 0.8, u_z.y));
        float n2 = snoise(vec3(qw * 1.15 + 3.1, u_z.z));
        float ribbons = exp(-n1 * n1 * 13.0) + 0.6 * exp(-n2 * n2 * 20.0);
        float core = exp(-dot(qw, qw) * 1.8);                          // glow pooled in the middle
        float density = ribbons * (0.55 + 0.45 * u_energy) + core * (0.22 + 0.15 * u_level) + 0.015;
        density *= 1.0 + 0.12 * u_breath + 0.30 * u_level;

        vec3 fluid = hue * density * 1.15;
        fluid = 1.0 - exp(-fluid * 1.4);                               // glow without clipping to white
        fluid *= mix(0.35, 1.0, z);                                    // more glass to look through near the rim

        // glass shell
        float fresnel = pow(1.0 - z, 4.0);
        float edge = smoothstep(0.90, 1.0, r);                         // thin bright lip of the glass
        vec3 rim = mix(avg, vec3(1.0), 0.35) * (fresnel * 0.45 + edge * edge * 0.30);
        vec3 L = normalize(vec3(-0.45, 0.6, 0.66));
        float spec = pow(max(dot(n, L), 0.0), 90.0) * 0.6;             // sharp highlight
        float sheen = pow(max(dot(n, L), 0.0), 8.0) * 0.035;           // faint broad reflection
        vec2 cp = p - vec2(0.22, -0.62);
        float caustic = exp(-dot(cp, cp) * 10.0) * (0.22 + 0.15 * u_level);  // light gathered at the bottom

        vec3 sphere = fluid + rim + vec3(spec + sheen) + hue * caustic;
        float mask = smoothstep(1.0, 1.0 - 1.5 * px, r) * u_visible;  // edge is antialiased in the shader
        col = mix(col, sphere, mask);
    }

    col += (hash(frag + u_frame) - 0.5) / 255.0;    // dither: no banding in dark gradients
    f_color = vec4(col, 1.0);
}
"""

POINTS_VS = """
#version 330
uniform vec2 u_res;
in vec2 in_pos;      // pixels, y up
in float in_size;    // pixels
in vec4 in_col;      // rgb + brightness
out vec4 v_col;
void main() {
    gl_Position = vec4(in_pos / u_res * 2.0 - 1.0, 0.0, 1.0);
    gl_PointSize = in_size;
    v_col = in_col;
}
"""

POINTS_FS = """
#version 330
uniform vec2 u_center;   // orb center, pixels
uniform float u_radius;  // orb radius, pixels (sparkles behind the glass are hidden)
uniform float u_hide;    // 1 = hide sparkles behind the orb, 0 = orb invisible, show them
in vec4 v_col;
out vec4 f_color;
void main() {
    float d = length(gl_PointCoord - 0.5) * 2.0;
    float a = exp(-d * d * 4.0) * (1.0 - smoothstep(0.8, 1.0, d));   // soft round dot
    float behind = 1.0 - smoothstep(u_radius - 1.0, u_radius + 1.5, length(gl_FragCoord.xy - u_center));
    a *= 1.0 - behind * u_hide;
    f_color = vec4(v_col.rgb * v_col.a * a, 1.0);
}
"""

QUAD_VS = """
#version 330
uniform vec4 u_rect;   // x, y, w, h in pixels, y up
uniform vec2 u_res;
in vec2 in_pos;        // 0..1 corners
out vec2 v_uv;
void main() {
    vec2 px = u_rect.xy + in_pos * u_rect.zw;
    gl_Position = vec4(px / u_res * 2.0 - 1.0, 0.0, 1.0);
    v_uv = in_pos;
}
"""

QUAD_FS = """
#version 330
uniform sampler2D u_tex;
uniform float u_alpha;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    f_color = vec4(c.rgb, c.a * u_alpha);
}
"""

BLIT_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_res;
out vec4 f_color;
void main() { f_color = texture(u_tex, gl_FragCoord.xy / u_res); }
"""

# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


def hex_to_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float64)


STATE_RGB = {name: [hex_to_rgb(c) for c in s["colors"]] for name, s in STATES.items()}


def smoothstep(k):
    k = min(max(k, 0.0), 1.0)
    return k * k * (3 - 2 * k)


def approach(current, target, rate, dt):
    """Moves current toward target smoothly, frame-rate independent. rate is per second."""
    return current + (target - current) * (1.0 - math.exp(-rate * dt))

# ------------------------------------------------------------------
# orb motion
# ------------------------------------------------------------------

# lobe paths: radius, x speed, y speed, phase
LOBES = [(0.45, 0.53, 0.61, 0.0), (0.45, 0.47, 0.39, 2.1), (0.40, 0.71, 0.57, 4.0), (0.35, 0.33, 0.45, 5.3)]


class OrbMotion:
    """Tracks everything about how the orb moves. update() once per frame, then uniforms()."""

    def __init__(self):
        self.state = "sleep"
        self.from_colors = STATE_RGB["sleep"]
        self.transition_start = -1e9
        self.transition_seconds = 0.6
        self.speed = STATES["sleep"]["speed"]
        self.energy = STATES["sleep"]["energy"]
        self.flow = 0.0
        self.level = 0.0
        self.colors = STATE_RGB["sleep"]

    def set_state(self, state, now, seconds):
        self.from_colors = self.colors_at(now)
        self.state = state
        self.transition_start = now
        self.transition_seconds = seconds

    def colors_at(self, now):
        k = smoothstep((now - self.transition_start) / self.transition_seconds)
        return [a + (b - a) * k for a, b in zip(self.from_colors, STATE_RGB[self.state])]

    def update(self, now, dt, level):
        target = STATES[self.state]
        self.speed = approach(self.speed, target["speed"], 4.0, dt)
        self.energy = approach(self.energy, target["energy"], 4.0, dt)
        self.level = level
        self.flow += dt * self.speed * (1.0 + 0.6 * level)  # the liquid rushes while speaking
        self.colors = self.colors_at(now)

    def uniforms(self):
        f = self.flow
        u = {
            "u_energy": self.energy,
            "u_level": self.level,
            "u_rot": (f * 0.30) % TAU,
            "u_twist": 1.4 * math.sin((f * 0.21) % TAU),
            "u_z": tuple((f * k) % NOISE_TIME_PERIOD for k in (0.22, 0.17, 0.26)),
        }
        for i, (rad, sx, sy, ph) in enumerate(LOBES):
            u[f"u_p{i}"] = (rad * math.cos((f * sx + ph) % TAU), rad * math.sin((f * sy + ph) % TAU))
        for i, c in enumerate(self.colors):
            u[f"u_c{i}"] = tuple(float(v) for v in c)
        return u

# ------------------------------------------------------------------
# stardust river
# ------------------------------------------------------------------


class StardustRiver:
    """Three gently waving streams of sparkles flowing behind the orb."""

    COUNT = 700
    BAND_Y = np.array([-35.0, 10.0, 55.0])          # offset from the orb's height, pixels
    BAND_AMP = np.array([46.0, 34.0, 58.0])         # wave height, pixels
    BAND_FREQ = np.array([0.008, 0.011, 0.006])     # waves per pixel
    BAND_DRIFT = np.array([0.5, -0.4, 0.3])         # how fast each wave shape rolls

    def __init__(self, width, height, seed=1):
        rng = np.random.default_rng(seed)
        n = self.COUNT
        self.width, self.height = width, height
        self.band = rng.integers(0, 3, n)
        self.x = rng.uniform(0, width + 40, n)
        self.depth = rng.uniform(0, 1, n)                                      # 0 far, 1 near
        self.spread = rng.normal(0, 1, n) * (8 + 14 * rng.uniform(0, 1, n))   # distance from the stream's center line
        self.phase = rng.uniform(0, TAU, n)
        self.twinkle = rng.uniform(0.6, 2.0, n)
        self.color_index = rng.integers(0, 4, n)
        self.wave_time = 0.0
        self.swell = 0.0
        self.data = np.zeros((n, 7), dtype="f4")

    def update(self, dt, speed, level):
        self.x += dt * (14 + 30 * self.depth) * (0.7 + 0.5 * speed)
        self.x %= self.width + 40
        self.wave_time = (self.wave_time + dt) % (TAU * 1000)
        self.swell = approach(self.swell, level, 6.0, dt)

    def vertex_data(self, colors, brightness, center_y, now):
        b = self.band
        amp = self.BAND_AMP[b] * (1 + 0.6 * self.swell)
        y = center_y + self.BAND_Y[b] + amp * np.sin(self.x * self.BAND_FREQ[b] + self.wave_time * self.BAND_DRIFT[b] + b * 2.0) + self.spread
        twinkle = 0.55 + 0.45 * np.sin((now % 1000.0) * self.twinkle * 2.5 + self.phase)
        alpha = (0.45 + 0.9 * self.depth) * twinkle * (1 + 0.7 * self.swell) * brightness
        palette = np.array(colors, dtype="f4")
        d = self.data
        d[:, 0] = self.x - 20
        d[:, 1] = y
        d[:, 2] = 3.0 + 4.0 * self.depth
        d[:, 3:6] = palette[self.color_index]
        d[:, 6] = alpha
        return d

# ------------------------------------------------------------------
# voice rings
# ------------------------------------------------------------------


class VoiceRings:
    """Turns voice loudness into rings that pulse out of the orb.

    Rings start on syllable onsets (loudness jumping up), never closer than
    MIN_GAP apart. Each ring tires the effect a little and quiet moments
    let it recover, so a long answer settles into a calm rhythm instead of
    strobing, and the start of each phrase still pulses strongly."""

    LIFETIME = 2.2      # seconds a ring takes to travel out and fade
    MIN_GAP = 0.6       # seconds between rings at most
    MAX_RINGS = 4       # the shader draws up to 4
    ONSET_LEVEL = 0.4   # loudness needed to start a ring
    ONSET_RISE = 0.18   # how sharply loudness must jump
    BRIGHTNESS = 0.55
    BREATH_RING = 0.3   # strength of the gentle ring each breath while listening

    def __init__(self):
        self.rings = []          # (start time, strength)
        self.last_ring = -1e9
        self.fatigue = 1.0
        self.follower = 0.0
        self.last_loud = -1e9

    def update(self, now, dt, level, speaking, breath_peak=False):
        self.fatigue = min(1.0, self.fatigue + dt / 6.0)          # recovers fully after ~6s without rings
        rise = level - self.follower
        self.follower = approach(self.follower, level, 3.0, dt)    # slow follower: onsets stand out against it
        if speaking:
            after_pause = now - self.last_loud > 0.35
            if level > self.ONSET_LEVEL and rise > self.ONSET_RISE and now - self.last_ring >= self.MIN_GAP:
                strength = (0.6 + 0.4 * min(rise / 0.5, 1.0)) * self.fatigue * (1.2 if after_pause else 1.0)
                self._add(now, min(strength, 1.0))
                self.fatigue = max(0.35, self.fatigue * 0.75)
            if level > 0.15:
                self.last_loud = now
        elif breath_peak:
            self._add(now, self.BREATH_RING)
        self.rings = [ring for ring in self.rings if now - ring[0] < self.LIFETIME]

    def _add(self, now, strength):
        self.rings.append((now, strength))
        self.rings = self.rings[-self.MAX_RINGS:]
        self.last_ring = now

    def uniforms(self, now):
        radii, alphas = [0.0] * 4, [0.0] * 4
        for i, (start, strength) in enumerate(self.rings):
            k = (now - start) / self.LIFETIME
            radii[i] = 1.03 + 1.5 * (1 - (1 - k) ** 2.2)                          # fast out, slowing down
            alphas[i] = self.BRIGHTNESS * strength * (1 - k) ** 1.6 * smoothstep(k / 0.06)  # soft start, long fade
        return {"u_ring_r": tuple(radii), "u_ring_a": tuple(alphas)}

# ------------------------------------------------------------------
# renderer
# ------------------------------------------------------------------


class TextTextures:
    """Turns pygame text surfaces into GPU textures, cached, and releases old ones so GPU memory can't leak."""

    LIMIT = 48

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}

    def get(self, key, make_surface):
        entry = self.cache.get(key)
        if entry is None:
            import pygame
            surf = make_surface()
            w, h = surf.get_size()
            data = pygame.image.tostring(surf, "RGBA", True)  # flipped: GL textures start at the bottom
            tex = self.ctx.texture((w, h), 4, data)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            if len(self.cache) >= self.LIMIT:
                self.clear()
            entry = (tex, w, h)
            self.cache[key] = entry
        return entry

    def clear(self):
        for tex, _, _ in self.cache.values():
            tex.release()
        self.cache.clear()


class Renderer:
    def __init__(self, ctx, width, height):
        self.ctx = ctx
        self.width, self.height = width, height
        ctx.enable(moderngl.PROGRAM_POINT_SIZE)

        tri = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())  # one triangle covering the screen
        quad = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], dtype="f4").tobytes())

        self.orb_prog = ctx.program(vertex_shader=FULLSCREEN_VS, fragment_shader=ORB_FS)
        self.orb_vao = ctx.vertex_array(self.orb_prog, [(tri, "2f", "in_pos")])
        self.blit_prog = ctx.program(vertex_shader=FULLSCREEN_VS, fragment_shader=BLIT_FS)
        self.blit_vao = ctx.vertex_array(self.blit_prog, [(tri, "2f", "in_pos")])
        self.points_prog = ctx.program(vertex_shader=POINTS_VS, fragment_shader=POINTS_FS)
        self.points_buf = ctx.buffer(reserve=StardustRiver.COUNT * 7 * 4)
        self.points_vao = ctx.vertex_array(self.points_prog, [(self.points_buf, "2f 1f 4f", "in_pos", "in_size", "in_col")])
        self.quad_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=QUAD_FS)
        self.quad_vao = ctx.vertex_array(self.quad_prog, [(quad, "2f", "in_pos")])

        self.text = TextTextures(ctx)
        self.scale = 1.0
        self.offscreen = None
        self.frame = 0

    def set_scale(self, scale):
        """Draws the orb at a lower resolution and scales it up, if the GPU ever can't keep up."""
        if self.offscreen is not None:
            self.offscreen[0].release()
            self.offscreen[1].release()
            self.offscreen = None
        self.scale = scale
        if scale < 1.0:
            size = (int(self.width * scale), int(self.height * scale))
            tex = self.ctx.texture(size, 3)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.offscreen = (tex, self.ctx.framebuffer(color_attachments=[tex]))

    def _set(self, prog, values):
        for name, value in values.items():
            if name in prog:
                prog[name].value = value

    def draw_orb(self, target, center, radius, uniforms):
        self.frame += 1
        if self.offscreen is not None:
            tex, fbo = self.offscreen
            fbo.use()
            w, h = tex.size
            s = w / self.width
        else:
            target.use()
            w, h, s = self.width, self.height, 1.0
        self.ctx.disable(moderngl.BLEND)
        self._set(self.orb_prog, uniforms)
        self._set(self.orb_prog, {
            "u_res": (w, h), "u_center": (center[0] * s, center[1] * s), "u_radius": radius * s,
            "u_frame": float(self.frame % 64),
        })
        self.orb_vao.render(moderngl.TRIANGLES)
        if self.offscreen is not None:
            target.use()
            tex.use(0)
            self._set(self.blit_prog, {"u_res": (self.width, self.height)})
            self.blit_vao.render(moderngl.TRIANGLES)

    def draw_points(self, data, center, radius, hide_amount):
        """hide_amount 1 hides sparkles behind the orb, 0 shows them (orb faded out at night)."""
        if len(data) == 0:
            return
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE  # additive: sparkles glow on top of the dark background
        self.points_buf.write(data.tobytes())
        self._set(self.points_prog, {"u_res": (self.width, self.height), "u_center": center,
                                     "u_radius": radius, "u_hide": float(hide_amount)})
        self.points_vao.render(moderngl.POINTS, vertices=len(data))

    def draw_text(self, entry, x, y_top, alpha):
        """Draws a cached text texture with its top-left corner at (x, y_top) in screen
        coordinates (y down, like pygame)."""
        if alpha <= 0.004:
            return
        tex, w, h = entry
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        tex.use(0)
        self._set(self.quad_prog, {"u_res": (self.width, self.height),
                                   "u_rect": (float(x), float(self.height - y_top - h), float(w), float(h)),
                                   "u_alpha": float(alpha)})
        self.quad_vao.render(moderngl.TRIANGLE_STRIP)
