"""
orb.py — Solu's glowing orb, rebuilt to fix the "flat/computery" look.

What was wrong before, and what changed:

1. HARD EDGE (the main complaint): the old gradient only faded alpha in the
   outer 5% of steps, leaving a visible seam between "solid colored circle"
   and "soft glow behind it" — three distinct zones instead of one smooth
   falloff. Fixed by extending the fade zone much further inward (now starts
   fading at 55% of the radius out to the edge), so the gradient itself
   dissolves gradually into the glow with no seam.

2. DIRECTIONAL LIGHT (new): a soft bright patch that orbits the orb slowly,
   selling "a lit sphere" rather than "an evenly-lit flat disc." Built with
   pygame.draw.arc confined to the orb's own bounding circle — geometrically
   incapable of spilling outside the orb's silhouette, since an arc can never
   draw outside the rectangle (and therefore radius) it's given. This avoids
   masking entirely (an earlier masking attempt had a real bug and was also
   ~20-40x more expensive than this approach when benchmarked).

3. GRAIN TEXTURE (new): a small noise pattern generated ONCE and cached,
   then tiled across the orb's surface with a slowly shifting offset each
   frame, for an "energy field" feel rather than a perfectly smooth plastic
   look. The texture itself is cheap to generate once; only the tiled blit
   (already proven cheap) happens every frame.

What's still cached per-state (no change in cost from before):
- The base gradient orb + glow (color doesn't change except during a
  crossfade, so this is generated once per state and reused)

What now runs fresh every frame (new, but each piece individually benchmarked
as cheap — see PI_SETUP_NOTES.md history for the numbers):
- The directional light arc (rotates over time)
- The grain texture's tiling offset (shifts over time)
"""

import pygame
import math
import random


def generate_orb_surface(core_rgb, edge_rgb, size):
    """
    Gradient orb via concentric circles, same core technique as before,
    but with the alpha fade-out zone extended much further inward to kill
    the hard seam between the solid circle and the glow behind it.
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = 70  # slightly more steps than before to keep the now-longer
                # fade zone looking smooth rather than banded

    # fade zone now starts at 55% of the way out, not 95% — this is the
    # actual fix for the "hard edge" complaint
    fade_start_fraction = 0.55

    for i in range(steps, 0, -1):
        radius = int(center * (i / steps))
        blend = 1 - (i / steps)
        r = int(edge_rgb[0] + (core_rgb[0] - edge_rgb[0]) * blend)
        g = int(edge_rgb[1] + (core_rgb[1] - edge_rgb[1]) * blend)
        b = int(edge_rgb[2] + (core_rgb[2] - edge_rgb[2]) * blend)

        step_fraction = i / steps  # 1.0 at outermost ring, ~0 at center
        if step_fraction > fade_start_fraction:
            # map [fade_start_fraction, 1.0] -> alpha [255, 0], smoothly
            fade_progress = (step_fraction - fade_start_fraction) / (1.0 - fade_start_fraction)
            a = int(255 * (1.0 - fade_progress))
        else:
            a = 255

        pygame.draw.circle(surf, (r, g, b, a), (center, center), radius)

    return surf


def add_glow(orb_surf, size):
    """
    Soft glow via downscale -> upscale (the blur-for-free trick). Tuned
    tight per feedback so it reads as a thin rim of light, not a second
    fainter orb.
    """
    glow_canvas_size = int(size * 1.18)
    glow_canvas = pygame.Surface((glow_canvas_size, glow_canvas_size), pygame.SRCALPHA)

    glow_layer_size = int(size * 1.05)
    small_size = max(4, glow_layer_size // 6)
    shrunk = pygame.transform.smoothscale(orb_surf, (small_size, small_size))
    blurred = pygame.transform.smoothscale(shrunk, (glow_layer_size, glow_layer_size))
    blurred.set_alpha(70)

    glow_pos = ((glow_canvas_size - glow_layer_size) // 2, (glow_canvas_size - glow_layer_size) // 2)
    glow_canvas.blit(blurred, glow_pos)

    orb_pos = ((glow_canvas_size - size) // 2, (glow_canvas_size - size) // 2)
    glow_canvas.blit(orb_surf, orb_pos)

    return glow_canvas


def make_grain_texture(tex_size=64, alpha=16):
    """
    One-time generation of a small noise pattern, meant to be cached and
    reused — calling this every frame would be the slow part, but calling
    it once at startup per the design (static base texture, just shifted
    over time) is cheap (~0.6ms measured) and only happens once total,
    not once per state even.
    """
    tex = pygame.Surface((tex_size, tex_size), pygame.SRCALPHA)
    for x in range(0, tex_size, 2):
        for y in range(0, tex_size, 2):
            v = random.randint(0, 255)
            tex.set_at((x, y), (v, v, v, alpha))
    return tex


def draw_grain(target_surf, grain_tex, offset_x, offset_y):
    """
    Tiles the cached grain texture across target_surf with the given
    pixel offset, additive-blended so it brightens/darkens speckles
    rather than flattening color. Confirmed cheap (~0.1ms at orb size).
    """
    tex_size = grain_tex.get_width()
    w, h = target_surf.get_size()
    ox = offset_x % tex_size
    oy = offset_y % tex_size
    for tx in range(-tex_size, w + tex_size, tex_size):
        for ty in range(-tex_size, h + tex_size, tex_size):
            target_surf.blit(grain_tex, (tx + ox, ty + oy), special_flags=pygame.BLEND_RGBA_ADD)


def draw_directional_light(surf, angle_rad, core_rgb, orb_radius_px, center_xy, intensity=1.0):
    """
    Draws a soft bright arc near the orb's edge that rotates over time,
    faking a directional light source hitting a sphere — without any real
    3D math, and without any shape-masking (which we proved is both buggy
    in this pygame build via the blend-flag route, and ~20-40x more
    expensive than this arc-based route when both were benchmarked).

    Geometrically guaranteed to never exceed the orb's silhouette, since
    pygame.draw.arc only ever draws within the rect/radius it's given.

    angle_rad: current rotation angle, driven externally (slowly increasing
    over time, per the "rotates around the orb" decision)
    intensity: 0.0-1.0 multiplier, lets the caller fade this in/out during
    state transitions if desired (not required, defaults to fully on)
    """
    cx, cy = center_xy
    r, g, b = core_rgb
    bright = (
        min(255, int(r + (255 - r) * 0.6)),
        min(255, int(g + (255 - g) * 0.6)),
        min(255, int(b + (255 - b) * 0.6)),
    )

    arc_span = math.radians(70)
    start_angle = angle_rad - arc_span / 2
    end_angle = angle_rad + arc_span / 2

    # several concentric arcs near the edge, fading inward, all confined
    # to the same bounding box as the orb -> can never spill outside it
    layers = 8
    for i in range(layers):
        inset = i * 3
        radius_here = orb_radius_px - inset
        if radius_here <= 0:
            break
        rect = pygame.Rect(
            cx - radius_here, cy - radius_here,
            radius_here * 2, radius_here * 2,
        )
        fade = (1.0 - (i / layers)) * intensity
        if fade <= 0.02:
            continue
        alpha = int(110 * fade)
        width = max(1, 6 - i // 2)
        try:
            pygame.draw.arc(surf, (*bright, alpha), rect, start_angle, end_angle, width=width)
        except ValueError:
            # pygame.draw.arc can raise on a zero/negative-size rect at the
            # very innermost layers for small orbs; just skip that layer
            continue


class Orb:
    """
    Owns the cached base orb+glow per state, the shared grain texture, and
    the rotating light/grain animation state. One instance lives for the
    whole program; call update(dt, state) once per frame, then
    get_current_frame(state, breathing_scale) to fetch the surface to blit.
    """

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_base = {}  # state -> orb+glow surface, generated once each
        for state, (core, edge) in orb_colors.items():
            base_orb = generate_orb_surface(core, edge, orb_size)
            self.cached_base[state] = add_glow(base_orb, orb_size)

        self.grain_tex = make_grain_texture(tex_size=64, alpha=16)

        self.light_angle = 0.0
        self.grain_offset_x = 0.0
        self.grain_offset_y = 0.0

        # how fast the light orbits and grain drifts, in arbitrary units
        # per second — separate from any single state's speed so both keep
        # moving smoothly through transitions
        self.light_speed = 0.5
        self.grain_speed_x = 6.0
        self.grain_speed_y = 4.0

    def update(self, dt):
        self.light_angle += self.light_speed * dt
        if self.light_angle > 2 * math.pi:
            self.light_angle -= 2 * math.pi

        self.grain_offset_x += self.grain_speed_x * dt
        self.grain_offset_y += self.grain_speed_y * dt

    def get_current_frame(self, state, core_rgb):
        """
        Returns a fresh surface for this frame: cached base orb+glow for
        the given state, with the directional light and grain layered on
        top (both regenerated this frame since they animate continuously).
        Caller is responsible for any breathing-scale resize afterward.
        """
        base = self.cached_base[state]
        frame = base.copy()

        canvas_size = frame.get_width()
        center = canvas_size // 2
        # the orb's actual radius within the glow canvas (smaller than the
        # full canvas, since the canvas includes the glow halo padding)
        orb_radius_in_canvas = int(self.orb_size / 2)

        draw_directional_light(
            frame, self.light_angle, core_rgb,
            orb_radius_in_canvas, (center, center),
        )

        draw_grain(frame, self.grain_tex, self.grain_offset_x, self.grain_offset_y)

        return frame