"""
gpu_orb_test.py: draws the GPU glass orb and measures how much GPU headroom the Pi has.

On the Pi (stop Solu first so the screen is free):
    sudo systemctl stop solu.service
    DISPLAY=:0 python3 tools/gpu_orb_test.py
    sudo systemctl start solu.service

It cycles through the states (speak pulses with a fake voice) and prints a
table at the end. Tap the screen or press Esc to quit early.

Preview without a screen (renders PNG frames, works on any machine):
    python3 tools/gpu_orb_test.py --preview out_folder
"""

import math
import os
import random
import sys
import time

# the Pi 4 GPU only advertises OpenGL 3.1, ModernGL wants 3.3; Mesa runs these shaders fine when told to
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "3.3")
os.environ.setdefault("MESA_GLSL_VERSION_OVERRIDE", "330")

import numpy as np

try:
    import moderngl
except ImportError:
    sys.exit("moderngl isn't installed. Run: pip install moderngl --break-system-packages")

SCREEN_W, SCREEN_H = 800, 480
ORB_RADIUS = 170
BREATH_SECONDS = 4.0
TAU = 2 * math.pi
NOISE_TIME_PERIOD = 867.0  # the 3D noise repeats exactly every 867 units of time, so wrapping there is seamless

# four flow colors per state, how fast the liquid moves, and how lively it is
STATES = {
    "sleep": {"colors": ["#FFFFFF", "#AFC3E0", "#E4ECFA", "#8F9DB8"], "speed": 0.55, "energy": 0.15},
    "idle":  {"colors": ["#4DB8FF", "#2E5BFF", "#7AF0FF", "#8E6CFF"], "speed": 1.0,  "energy": 0.45},
    "think": {"colors": ["#FFD86B", "#82F4FF", "#FF7BD5", "#8E6CFF"], "speed": 2.2,  "energy": 0.7},
    "speak": {"colors": ["#B388FF", "#FF7BD5", "#5B4BFF", "#82F4FF"], "speed": 1.4,  "energy": 0.6},
    "error": {"colors": ["#FF5252", "#FF2E63", "#FF9A76", "#B0103A"], "speed": 1.2,  "energy": 0.6},
    "alarm": {"colors": ["#FFC800", "#FF8A00", "#FFE680", "#FF5E3A"], "speed": 1.8,  "energy": 1.0},
}

VERTEX_SHADER = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

FRAGMENT_SHADER = """
#version 330
uniform vec2 u_res;        // render target size in pixels
uniform vec2 u_center;     // orb center in pixels
uniform float u_radius;    // orb radius in pixels
uniform float u_energy;    // 0..1 how lively the state is
uniform float u_breath;    // -1..1, same breathing cycle as the orb's size
uniform float u_level;     // 0..1 voice loudness, makes the liquid surge
uniform float u_rot;       // how far the liquid has turned
uniform float u_twist;     // how much faster the middle turns than the edge
uniform vec3 u_z;          // noise time for the warp and the two ribbon layers
uniform vec2 u_p0, u_p1, u_p2, u_p3;   // where each color lobe currently is
uniform vec3 u_c0, u_c1, u_c2, u_c3;
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
    col += avg * halo * (0.10 + 0.08 * u_energy + 0.20 * u_level + 0.03 * u_breath);

    if (r < 1.0 + 2.0 * px) {
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
        float mask = smoothstep(1.0, 1.0 - 1.5 * px, r);           // edge is antialiased in the shader
        col = mix(col, sphere, mask);
    }

    col += (hash(frag + u_frame) - 0.5) / 255.0;    // dither: no banding in dark gradients
    f_color = vec4(col, 1.0);
}
"""

BLIT_FRAGMENT_SHADER = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_res;
out vec4 f_color;
void main() { f_color = texture(u_tex, gl_FragCoord.xy / u_res); }
"""

# lobe paths: radius, x speed, y speed, phase
LOBES = [(0.45, 0.53, 0.61, 0.0), (0.45, 0.47, 0.39, 2.1), (0.40, 0.71, 0.57, 4.0), (0.35, 0.33, 0.45, 5.3)]

# ------------------------------------------------------------------


def hex_to_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float64)


class FakeVoice:
    """Stand-in for Ryan's voice loudness: syllable-like bursts with pauses between phrases."""

    def __init__(self):
        self.level = 0.0
        self.target = 0.0
        self.next_change = 0.0

    def update(self, dt, now):
        if now >= self.next_change:
            if random.random() < 0.12:
                self.target, hold = 0.0, random.uniform(0.25, 0.5)     # pause between phrases
            else:
                self.target, hold = random.uniform(0.35, 1.0), random.uniform(0.08, 0.2)  # a syllable
            self.next_change = now + hold
        rate = 18.0 if self.target > self.level else 7.0               # quick attack, slower release
        self.level += (self.target - self.level) * (1.0 - math.exp(-rate * dt))
        return self.level


class OrbRenderer:
    """Owns the shader and all the motion: state blending, breathing, swirling, voice."""

    TRANSITION_SECONDS = 0.6

    def __init__(self, ctx):
        self.ctx = ctx
        self.prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.blit = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=BLIT_FRAGMENT_SHADER)
        triangle = np.array([-1, -1, 3, -1, -1, 3], dtype="f4")  # one triangle covering the screen
        vbo = ctx.buffer(triangle.tobytes())
        self.vao = ctx.vertex_array(self.prog, [(vbo, "2f", "in_pos")])
        self.blit_vao = ctx.vertex_array(self.blit, [(vbo, "2f", "in_pos")])
        self.flow = 0.0          # kept on the CPU in double precision so motion stays smooth after weeks of uptime
        self.frame = 0
        self.state = "sleep"
        self.from_colors = [hex_to_rgb(c) for c in STATES["sleep"]["colors"]]
        self.speed = STATES["sleep"]["speed"]
        self.energy = STATES["sleep"]["energy"]
        self.level = 0.0
        self.transition_start = -1e9

    def set_state(self, state, now):
        self.from_colors = self.current_colors(now)
        self.state = state
        self.transition_start = now

    def current_colors(self, now):
        target = [hex_to_rgb(c) for c in STATES[self.state]["colors"]]
        k = min((now - self.transition_start) / self.TRANSITION_SECONDS, 1.0)
        k = k * k * (3 - 2 * k)  # ease in and out
        return [a + (b - a) * k for a, b in zip(self.from_colors, target)]

    def update(self, dt, now, level=0.0):
        target = STATES[self.state]
        ease = 1.0 - math.pow(0.02, dt)  # glide speed and energy toward the new state
        self.speed += (target["speed"] - self.speed) * ease
        self.energy += (target["energy"] - self.energy) * ease
        self.level = level
        self.flow += dt * self.speed * (1.0 + 0.6 * level)  # the liquid rushes while speaking
        self.frame += 1

    def render(self, width, height, now):
        f = self.flow
        breath = math.sin(now * TAU / BREATH_SECONDS)
        radius = ORB_RADIUS * (width / SCREEN_W) * (1.0 + 0.015 * breath + 0.03 * self.level)
        u = self.prog
        u["u_res"].value = (width, height)
        u["u_center"].value = (width / 2, height / 2)
        u["u_radius"].value = radius
        u["u_energy"].value = self.energy
        u["u_breath"].value = breath
        u["u_level"].value = self.level
        u["u_rot"].value = (f * 0.30) % TAU
        u["u_twist"].value = 1.4 * math.sin(f * 0.21)
        u["u_z"].value = tuple((f * k) % NOISE_TIME_PERIOD for k in (0.22, 0.17, 0.26))
        for i, (rad, sx, sy, ph) in enumerate(LOBES):
            u[f"u_p{i}"].value = (rad * math.cos((f * sx + ph) % TAU), rad * math.sin((f * sy + ph) % TAU))
        for i, c in enumerate(self.current_colors(now)):
            u[f"u_c{i}"].value = tuple(float(v) for v in c)
        u["u_frame"].value = float(self.frame % 64)
        self.vao.render(moderngl.TRIANGLES)

# ------------------------------------------------------------------

STATE_SECONDS = 4.0


def state_at(now):
    order = list(STATES)
    return order[int(now / STATE_SECONDS) % len(order)]


def preview(out_dir, frames=720, fps=30):
    """Renders frames to PNGs with an offscreen context, no screen needed."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    ctx = moderngl.create_standalone_context(backend="egl") if sys.platform.startswith("linux") else moderngl.create_standalone_context()
    fbo = ctx.simple_framebuffer((SCREEN_W, SCREEN_H))
    fbo.use()
    orb = OrbRenderer(ctx)
    voice = FakeVoice()
    random.seed(4)
    for i in range(frames):
        now = i / fps
        state = state_at(now)
        if state != orb.state:
            orb.set_state(state, now)
        level = voice.update(1 / fps, now) if state == "speak" else 0.0
        orb.update(1 / fps, now, level)
        orb.render(SCREEN_W, SCREEN_H, now)
        img = Image.frombytes("RGB", (SCREEN_W, SCREEN_H), fbo.read(components=3)).transpose(Image.FLIP_TOP_BOTTOM)
        img.save(os.path.join(out_dir, f"frame_{i:04d}.png"))
    print(f"wrote {frames} frames to {out_dir}")


def benchmark(seconds_per_test=8):
    """Runs fullscreen on the real screen. Each test draws the orb on screen plus
    `extra` more copies offscreen, to see how much GPU headroom is left."""
    import pygame
    pygame.init()
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.NOFRAME
    try:
        pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, vsync=1)
    except (TypeError, pygame.error):
        pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.mouse.set_visible(False)
    ctx = moderngl.create_context()
    print(f"GPU: {ctx.info['GL_RENDERER']} | OpenGL {ctx.info['GL_VERSION']}")
    if "llvmpipe" in ctx.info["GL_RENDERER"].lower():
        print("WARNING: running on the CPU (llvmpipe), not the GPU. Results will be bad.")

    orb = OrbRenderer(ctx)
    voice = FakeVoice()
    screen = ctx.screen
    spare = ctx.framebuffer(color_attachments=[ctx.texture((SCREEN_W, SCREEN_H), 3)])
    tests = [("orb, full size", 0), ("orb x2 (headroom)", 1), ("orb x3 (headroom)", 2)]
    results = []
    start = last = time.perf_counter()
    quit_early = False

    for label, extra in tests:
        frame_times = []
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds_per_test and not quit_early:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN) or \
                        (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    quit_early = True
            now = time.perf_counter() - start
            dt = time.perf_counter() - last
            state = state_at(now)
            if state != orb.state:
                orb.set_state(state, now)
            level = voice.update(dt, now) if state == "speak" else 0.0
            orb.update(dt, now, level)

            for _ in range(extra):
                spare.use()
                orb.render(SCREEN_W, SCREEN_H, now)
            screen.use()
            orb.render(SCREEN_W, SCREEN_H, now)
            pygame.display.flip()

            t = time.perf_counter()
            frame_times.append(t - last)
            last = t
        if len(frame_times) > 10:
            ft = np.array(frame_times[5:])
            results.append((label, len(ft) / ft.sum(), (ft > 1 / 50).mean() * 100, ft.max() * 1000))
        if quit_early:
            break

    pygame.quit()
    print("\ntest                 avg fps   frames slower than 50fps   worst frame")
    for label, fps, slow, worst in results:
        print(f"{label:<20} {fps:7.1f}   {slow:6.1f}%                    {worst:6.1f}ms")
    smooth = [r for r in results if r[1] >= 57 and r[2] < 2]
    if results and smooth:
        print(f"\nVERDICT: smooth. GPU can draw this orb {1 + tests[[t[0] for t in tests].index(smooth[-1][0])][1]}x per frame at 60fps")
    elif results:
        print("\nVERDICT: can't hold 60fps, shader needs trimming (send me these numbers)")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--preview":
        preview(sys.argv[2])
    else:
        benchmark()
