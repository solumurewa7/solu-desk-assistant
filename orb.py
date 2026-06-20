"""
orb.py — Solu's glowing orb. Built to match a reference image Seyi shared:
a near-black background, the orb's softness coming ONLY from its own
edge fading into transparency (no separate glow halo at all — that was
tried multiple times and never got the look right, so it was dropped
entirely by request), no highlight, with a very fine subtle grain
texture across the surface for an "energy field" feel rather than
perfectly smooth plastic.

History: a rotating directional light and orbiting particle system were
tried earlier and scrapped (the light rendered as a broken-looking dark
artifact due to inconsistent alpha behavior in pygame.draw.arc on this
build; the particles didn't look convincing without real 3D tooling). A
static highlight was tried and worked correctly but was removed for not
fitting the reference's subtle aesthetic. A separate glow ring (several
versions, increasingly subtle) was also tried and ultimately removed
entirely — getting a separate glow layer to look right alongside the
already-soft edge fade never quite worked, and the edge fade alone turned
out to be enough.

What makes this read as dimensional rather than flat:

1. EDGE GRADIENT: the color fade-out zone starts at 90% of the radius, so
   the orb's body stays crisp and only a thin band right at the boundary
   softens into transparency — this IS the only "glow," there's no
   separate halo layer anymore.

2. STEP COUNT SCALES WITH RADIUS: gradient steps are one-per-pixel of the
   orb's radius rather than a fixed count — confirmed via direct pixel
   sampling that a fixed low step count produced real, measurable banding
   (not just a vague impression), while scaling steps to radius measured
   zero such jumps regardless of orb size.

3. SUBTLE GRAIN TEXTURE: a uniform per-pixel brightness deviation (±5),
   confirmed visually as the right amount after two other approaches
   (a regular grid, and sparse scattered points) were tried and rejected
   for looking like a mesh pattern or visible specks respectively.

Everything here is generated ONCE per state and cached — there is no
per-frame regeneration cost at all for the orb itself. Only the
breathing-scale resize (handled by the caller) happens every frame.
"""

import pygame
import pygame.surfarray as surfarray
import numpy as np


def add_subtle_grain(orb_surf, max_deviation=5):
    """
    Applies a very faint per-pixel brightness deviation across the whole
    surface, for a fine "energy field" texture rather than a perfectly
    smooth gradient. Tried two other approaches first and rejected both
    after looking at them directly:
      - a regular grid of grain points: produced a visible mesh/screen-door
        pattern, looked nothing like organic grain
      - sparse scattered single-pixel points: each point stayed individually
        visible as a bright speck, read as "stars on the orb" rather than
        texture
    This uniform-noise approach (every pixel gets a small random nudge at
    once via numpy) is what actually reads as subtle texture rather than a
    distinct effect layered on top. max_deviation=5 was the value
    confirmed visually as "barely noticeable, but there" — deviation of 3
    was nearly invisible, 8 started to look like visible static.

    This only ever runs ONCE per state at init time (called from Orb's
    constructor below), never per-frame, so its ~1ms-per-state cost is
    irrelevant to runtime performance.
    """
    result = orb_surf.copy()
    rgb_array = surfarray.pixels3d(result)  # direct view into the RGB pixel data
    noise = np.random.randint(-max_deviation, max_deviation + 1, rgb_array.shape, dtype=np.int16)
    new_vals = rgb_array.astype(np.int16) + noise
    np.clip(new_vals, 0, 255, out=new_vals)
    rgb_array[:] = new_vals.astype(np.uint8)
    del rgb_array  # release the surface lock created by pixels3d
    return result


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.9):
    """
    Gradient orb via concentric circles. Step count now scales with the
    orb's actual radius (one step per pixel) rather than a fixed number —
    confirmed via direct pixel sampling that a fixed 80 steps produced
    visible banding at this size (161 of 184 sampled pixel-pairs along a
    radial line showed a jump bigger than 4 color units), while one step
    per pixel measured ZERO such jumps. This is essentially free (under
    3ms even at this higher step count, and it only ever runs once per
    state at init).
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = center  # one gradient step per pixel of radius -- eliminates banding

    for i in range(steps, 0, -1):
        radius = int(center * (i / steps))
        blend = 1 - (i / steps)
        r = int(edge_rgb[0] + (core_rgb[0] - edge_rgb[0]) * blend)
        g = int(edge_rgb[1] + (core_rgb[1] - edge_rgb[1]) * blend)
        b = int(edge_rgb[2] + (core_rgb[2] - edge_rgb[2]) * blend)

        step_fraction = i / steps
        if step_fraction > fade_start_fraction:
            fade_progress = (step_fraction - fade_start_fraction) / (1.0 - fade_start_fraction)
            a = int(255 * (1.0 - fade_progress))
        else:
            a = 255

        pygame.draw.circle(surf, (r, g, b, a), (center, center), radius)

    return surf


class Orb:
    """
    Owns the cached, fully-built orb surface (gradient + grain, no
    separate glow layer) per state. Generated ONCE at startup —
    get_current_frame() just returns the cached surface directly, no
    per-frame work at all for the orb itself.
    """

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_frames = {}  # state -> final orb+grain surface
        for state, (core, edge) in orb_colors.items():
            base = generate_orb_surface(core, edge, orb_size)
            self.cached_frames[state] = add_subtle_grain(base, max_deviation=5)

    def update(self, dt):
        # nothing animates on the orb itself anymore — kept as a no-op so
        # the caller's existing orb.update(dt) call doesn't need to change
        pass

    def get_current_frame(self, state, core_rgb):
        """Returns the cached, fully-built surface for this state."""
        return self.cached_frames[state]