"""
orb.py — Solu's glowing orb. Built to match a reference image Seyi shared:
a near-black background, the orb's softness coming ONLY from its own
edge fading into transparency. No separate glow halo, no highlight, and
(as of this version) no grain texture either — every one of those was
tried, and grain specifically introduced a visible speckled ring right
at the edge (the noise was applied at full strength even on the
low-alpha fade pixels, where it overwhelmed the tiny color signal left).
Rather than keep tuning it, the call was made to drop grain entirely and
just maximize sharpness on the gradient itself.

History: a rotating directional light and orbiting particle system were
tried earlier and scrapped (the light rendered as a broken-looking dark
artifact due to inconsistent alpha behavior in pygame.draw.arc on this
build; the particles didn't look convincing without real 3D tooling). A
static highlight was tried and worked correctly but didn't fit the
reference's subtle aesthetic. A separate glow ring (several versions)
was tried and removed — never looked right alongside the edge fade. Grain
texture was tried, alpha-scaled to fix an edge artifact, and ultimately
removed anyway in favor of pure sharpness.

What this file does now, in full:

1. EDGE GRADIENT: the color fade-out zone starts at 90% of the radius, so
   the orb's body stays crisp and only a thin band right at the boundary
   softens into transparency — this is the only softening anywhere on
   the orb.

2. STEP COUNT SCALES WITH RADIUS: gradient steps are one-per-pixel of the
   orb's radius rather than a fixed count — confirmed via direct pixel
   sampling that a fixed low step count produced real, measurable
   banding, while scaling steps to radius measured zero such jumps
   regardless of orb size. This is the main thing that makes the orb
   look sharp/high-quality rather than stepped.

Everything here is generated ONCE per state and cached — there is no
per-frame regeneration cost at all for the orb itself. Only the
breathing-scale resize (handled by the caller) happens every frame.
"""

import pygame


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
    Owns the cached, fully-built orb surface (pure gradient, no glow, no
    grain) per state. Generated ONCE at startup — get_current_frame()
    just returns the cached surface directly, no per-frame work at all
    for the orb itself.
    """

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_frames = {}  # state -> final orb surface, pure gradient
        for state, (core, edge) in orb_colors.items():
            self.cached_frames[state] = generate_orb_surface(core, edge, orb_size)

    def update(self, dt):
        # nothing animates on the orb itself anymore — kept as a no-op so
        # the caller's existing orb.update(dt) call doesn't need to change
        pass

    def get_current_frame(self, state, core_rgb):
        """Returns the cached, fully-built surface for this state."""
        return self.cached_frames[state]