"""
gpu_orb_test.py: draws the GPU glass orb and measures whether the Pi can hold 60fps.

On the Pi (stop Solu first so the screen is free):
    sudo systemctl stop solu.service
    DISPLAY=:0 python3 tools/gpu_orb_test.py
    sudo systemctl start solu.service

It cycles through the states for about 30 seconds at three render sizes and
prints the results. Tap the screen or press Esc to quit early.

Preview without a screen (renders PNG frames, works on any machine):
    python3 tools/gpu_orb_test.py --preview out_folder
"""

import os
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

# four flow colors per state, plus how fast the inside moves and how lively it is
STATES = {
    "sleep": {"colors": ["#FFFFFF", "#AFC3E0", "#E4ECFA", "#8F9DB8"], "speed": 0.35, "energy": 0.15},
    "idle":  {"colors": ["#4DB8FF", "#2E5BFF", "#7AF0FF", "#8E6CFF"], "speed": 0.8,  "energy": 0.45},
    "think": {"colors": ["#FFD86B", "#82F4FF", "#FF7BD5", "#8E6CFF"], "speed": 1.6,  "energy": 0.7},
    "speak": {"colors": ["#B388FF", "#FF7BD5", "#5B4BFF", "#82F4FF"], "speed": 1.2,  "energy": 0.9},
    "error": {"colors": ["#FF5252", "#FF2E63", "#FF9A76", "#B0103A"], "speed": 1.0,  "energy": 0.6},
    "alarm": {"colors": ["#FFC800", "#FF8A00", "#FFE680", "#FF5E3A"], "speed": 1.4,  "energy": 1.0},
}

VERTEX_SHADER = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

FRAGMENT_SHADER = """
#version 330
uniform vec2 u_res;       // render target size in pixels
uniform vec2 u_center;    // orb center in pixels
uniform float u_radius;   // orb radius in pixels
uniform float u_flow;     // flow time, integrated on the CPU so speed changes never jump
uniform float u_energy;   // 0..1 how lively the inside is (later: driven by voice level)
uniform float u_frame;    // changes every frame, for dithering
uniform vec3 u_c0, u_c1, u_c2, u_c3;
out vec4 f_color;

// 2D simplex noise (Ashima Arts / Stefan Gustavson, MIT)
vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
    vec2 i = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod(i, 289.0);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m * m; m = m * m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec2 frag = gl_FragCoord.xy;
    vec2 p = (frag - u_center) / u_radius;   // orb space: the orb is the unit circle, y points up
    float r = length(p);
    float px = 1.0 / u_radius;               // one pixel in orb units
    vec3 avg = (u_c0 + u_c1 + u_c2 + u_c3) * 0.25;
    float t = u_flow;

    // background: near-black with a faint tint and soft glow from the orb
    vec2 s = frag / u_res - 0.5;
    vec3 col = vec3(0.010, 0.013, 0.028) * (1.0 - 0.6 * dot(s, s));
    float halo = exp(-max(r - 1.0, 0.0) * 5.5);
    col += avg * halo * (0.10 + 0.10 * u_energy);

    if (r < 1.0 + 2.0 * px) {
        float z = sqrt(max(1.0 - r * r, 0.0));
        vec3 n = vec3(p, z);

        // looking through a thick glass ball: the inside bulges outward near the rim
        vec2 q = p * (0.62 + 0.38 * z);

        // the liquid: domain-warped space so the color shapes stretch and fold like a living fluid
        vec2 w = vec2(snoise(q * 1.25 + vec2(0.0, t * 0.30)),
                      snoise(q * 1.25 + vec2(5.2, -t * 0.27)));
        vec2 qw = q + w * (0.30 + 0.25 * u_energy);

        // where each color lives: four soft lobes drifting around inside
        vec2 c0 = 0.45 * vec2(cos(t * 0.53),        sin(t * 0.61));
        vec2 c1 = 0.45 * vec2(cos(t * 0.47 + 2.1),  sin(t * 0.39 + 1.3));
        vec2 c2 = 0.40 * vec2(cos(t * 0.71 + 4.0),  sin(t * 0.57 + 3.6));
        vec2 c3 = 0.35 * vec2(cos(t * 0.33 + 5.3),  sin(t * 0.45 + 0.4));
        vec4 wgt = vec4(exp(-dot(qw - c0, qw - c0) * 3.0), exp(-dot(qw - c1, qw - c1) * 3.0),
                        exp(-dot(qw - c2, qw - c2) * 3.5), exp(-dot(qw - c3, qw - c3) * 2.5)) + 0.02;
        vec3 hue = (u_c0 * wgt.x + u_c1 * wgt.y + u_c2 * wgt.z + u_c3 * wgt.w) / dot(wgt, vec4(1.0));
        hue = max(mix(vec3(dot(hue, vec3(0.333))), hue, 1.3), 0.0);   // keep colors rich, not pastel

        // silk ribbons: bright where a slow warped noise crosses zero, dark glass in between
        float n1 = snoise(qw * 0.8 + vec2(t * 0.11, 1.7));
        float n2 = snoise(qw * 1.1 + vec2(-3.1, t * 0.09));
        float ribbons = exp(-n1 * n1 * 9.0) + 0.6 * exp(-n2 * n2 * 14.0);
        float core = exp(-dot(qw, qw) * 1.8);                          // a little glow pooled in the middle
        float density = ribbons * (0.55 + 0.45 * u_energy) + core * 0.25 + 0.02;

        vec3 fluid = hue * density * 1.25;
        fluid = 1.0 - exp(-fluid * 1.4);                               // glow without clipping to white
        fluid *= mix(0.35, 1.0, z);                                    // more glass to look through near the rim

        // glass shell
        float fresnel = pow(1.0 - z, 4.0);
        float edge = smoothstep(0.90, 1.0, r);                         // thin bright lip of the glass
        vec3 rim = mix(avg, vec3(1.0), 0.35) * (fresnel * 0.45 + edge * edge * 0.30);
        vec3 L = normalize(vec3(-0.45, 0.6, 0.66));
        float spec = pow(max(dot(n, L), 0.0), 90.0) * 0.6;             // sharp highlight
        float sheen = pow(max(dot(n, L), 0.0), 8.0) * 0.035;           // faint broad reflection
        float caustic = exp(-dot(p - vec2(0.22, -0.62), p - vec2(0.22, -0.62)) * 10.0) * 0.22;  // light gathered at the bottom

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

# ------------------------------------------------------------------


def hex_to_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


class OrbRenderer:
    """Owns the shader and the smooth blending between states."""

    TRANSITION_SECONDS = 0.6

    def __init__(self, ctx):
        self.ctx = ctx
        self.prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.blit = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=BLIT_FRAGMENT_SHADER)
        triangle = np.array([-1, -1, 3, -1, -1, 3], dtype="f4")  # one triangle covering the screen
        vbo = ctx.buffer(triangle.tobytes())
        self.vao = ctx.vertex_array(self.prog, [(vbo, "2f", "in_pos")])
        self.blit_vao = ctx.vertex_array(self.blit, [(vbo, "2f", "in_pos")])
        self.flow = 0.0
        self.frame = 0
        self.state = "sleep"
        self.colors = [hex_to_rgb(c) for c in STATES["sleep"]["colors"]]
        self.from_colors = self.colors
        self.speed = STATES["sleep"]["speed"]
        self.energy = STATES["sleep"]["energy"]
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

    def update(self, dt, now):
        target = STATES[self.state]
        ease = 1.0 - pow(0.02, dt)  # glide speed and energy toward the new state
        self.speed += (target["speed"] - self.speed) * ease
        self.energy += (target["energy"] - self.energy) * ease
        self.flow += dt * self.speed
        self.frame += 1

    def render(self, width, height, now, breathe=True):
        radius = ORB_RADIUS * (width / SCREEN_W)
        if breathe:
            radius *= 1.0 + 0.015 * np.sin(now * 2 * np.pi / 4.0)
        colors = self.current_colors(now)
        self.prog["u_res"].value = (width, height)
        self.prog["u_center"].value = (width / 2, height / 2)
        self.prog["u_radius"].value = float(radius)
        self.prog["u_flow"].value = self.flow
        self.prog["u_energy"].value = self.energy
        self.prog["u_frame"].value = float(self.frame % 64)
        for i, c in enumerate(colors):
            self.prog[f"u_c{i}"].value = tuple(float(v) for v in c)
        self.vao.render(moderngl.TRIANGLES)

# ------------------------------------------------------------------


def preview(out_dir, frames=150, fps=30):
    """Renders frames to PNGs with an offscreen context, no screen needed."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    ctx = moderngl.create_standalone_context(backend="egl") if sys.platform.startswith("linux") else moderngl.create_standalone_context()
    fbo = ctx.simple_framebuffer((SCREEN_W, SCREEN_H))
    fbo.use()
    orb = OrbRenderer(ctx)
    order = list(STATES)
    for i in range(frames):
        now = i / fps
        state = order[int(now / 2.5) % len(order)]
        if state != orb.state:
            orb.set_state(state, now)
        orb.update(1 / fps, now)
        orb.render(SCREEN_W, SCREEN_H, now)
        img = Image.frombytes("RGB", (SCREEN_W, SCREEN_H), fbo.read(components=3)).transpose(Image.FLIP_TOP_BOTTOM)
        img.save(os.path.join(out_dir, f"frame_{i:04d}.png"))
    print(f"wrote {frames} frames to {out_dir}")


def benchmark(seconds_per_scale=10, scales=(1.0, 0.75, 0.5)):
    """Runs fullscreen on the real screen and reports frame pacing at each render size."""
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
    screen = ctx.screen
    order = list(STATES)
    results = []
    start = time.perf_counter()
    quit_early = False

    for scale in scales:
        w, h = int(SCREEN_W * scale), int(SCREEN_H * scale)
        fbo = None
        if scale < 1.0:
            tex = ctx.texture((w, h), 3)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            fbo = ctx.framebuffer(color_attachments=[tex])
        frame_times = []
        t0 = last = time.perf_counter()
        while time.perf_counter() - t0 < seconds_per_scale and not quit_early:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN) or \
                        (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    quit_early = True
            now = time.perf_counter() - start
            state = order[int(now / 2.5) % len(order)]
            if state != orb.state:
                orb.set_state(state, now)
            orb.update(now - (last - start), now)

            if fbo is not None:
                fbo.use()
                orb.render(w, h, now)
                screen.use()
                tex.use(0)
                orb.blit["u_res"].value = (SCREEN_W, SCREEN_H)
                orb.blit_vao.render(moderngl.TRIANGLES)
            else:
                screen.use()
                orb.render(SCREEN_W, SCREEN_H, now)
            pygame.display.flip()

            t = time.perf_counter()
            frame_times.append(t - last)
            last = t
        if frame_times:
            ft = np.array(frame_times[5:] or frame_times)
            results.append((scale, w, h, len(ft) / ft.sum(), (ft > 1 / 50).mean() * 100, ft.max() * 1000))
        if quit_early:
            break

    pygame.quit()
    print("\nscale   size      avg fps   frames slower than 50fps   worst frame")
    for scale, w, h, fps, slow, worst in results:
        print(f"{scale:<7} {w}x{h:<6} {fps:7.1f}   {slow:6.1f}%                    {worst:6.1f}ms")
    if results:
        best = [r for r in results if r[3] >= 57 and r[4] < 2]
        if best:
            print(f"\nVERDICT: smooth 60fps at {best[0][1]}x{best[0][2]} (scale {best[0][0]})")
        else:
            print("\nVERDICT: can't hold 60fps yet, shader needs trimming (send me these numbers)")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--preview":
        preview(sys.argv[2])
    else:
        benchmark()
