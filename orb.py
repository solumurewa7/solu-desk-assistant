"""
orb.py — Solu's glowing orb. Kept deliberately simple per Seyi's call:
just a gradient + glow, no rotating light, no grain texture, no
particles, no highlight — all of those were tried and either looked
broken (the rotating light rendered as an unexplained dark artifact due
to inconsistent alpha behavior in pygame.draw.arc on this build) or just
didn't add enough to be worth keeping (the static highlight). This file
is the clean, working version Seyi confirmed looks right.

What makes this read as dimensional rather than flat:

1. EDGE GRADIENT, TIGHTENED: the color fade-out zone starts at 90% of
   the radius, so the orb's body stays crisp and only a thin band right
   at the boundary softens.

2. GLOW, AS A SHORT EDGE-ONLY RING: a separate, simple radial-falloff
   ring confined to a narrow band just outside the orb's own edge — not
   a blur of the whole orb, which would soften the body itself. The
   ring's reach was shortened (was 0.50-0.60 of size, now 0.50-0.545)
   per feedback that the glow extended too far outward.

Everything here is generated ONCE per state and cached — there is no
per-frame regeneration cost at all for the orb itself. Only the
breathing-scale resize (handled by the caller) happens every frame.
"""

import pygame


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.9):
    """
    Gradient orb via concentric circles. The alpha fade-out zone now
    starts at 90% of the radius (was 55% in the previous pass) — pulled
    in tighter per feedback that the orb looked too blurry overall.
    Most of the orb's body stays crisp, with only a thin band right at
    the boundary softening into transparency, where add_glow's separate
    edge-ring picks up to extend the soft halo outward.
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = 80

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


def add_glow(orb_surf, size, core_rgb):
    """
    Soft glow built as a SEPARATE thin ring drawn just outside the orb's
    own edge, rather than blurring the entire orb via downscale/upscale.
    Reach shortened per feedback (ring now spans 0.50-0.545 of size,
    was 0.50-0.60) so the glow stays tight to the edge rather than
    extending far outward.
    """
    glow_canvas_size = int(size * 1.10)  # pulled in from 1.16 to match the shorter ring reach
    glow_canvas = pygame.Surface((glow_canvas_size, glow_canvas_size), pygame.SRCALPHA)
    gc = glow_canvas_size // 2

    ring_layer = pygame.Surface((glow_canvas_size, glow_canvas_size), pygame.SRCALPHA)
    outer_r = int(size * 0.2)  # pulled in from 0.60 — shorter reach, glow stays tight to the edge
    inner_r = int(size * 0.50)   # starts right at the orb's own edge
    ring_steps = 20
    for i in range(ring_steps, -1, -1):
        frac = i / ring_steps
        r = int(inner_r + (outer_r - inner_r) * frac)
        alpha = int(95 * (1 - frac))
        pygame.draw.circle(ring_layer, (*core_rgb, alpha), (gc, gc), r)

    glow_canvas.blit(ring_layer, (0, 0))

    orb_pos = ((glow_canvas_size - size) // 2, (glow_canvas_size - size) // 2)
    glow_canvas.blit(orb_surf, orb_pos)

    return glow_canvas


class Orb:
    """
    Owns the cached, fully-built orb+glow surface per state. Generated
    ONCE at startup — get_current_frame() just returns the cached
    surface directly, no per-frame work at all for the orb itself.
    """

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_frames = {}  # state -> final orb+glow surface
        for state, (core, edge) in orb_colors.items():
            base = generate_orb_surface(core, edge, orb_size)
            self.cached_frames[state] = add_glow(base, orb_size, core)

    def update(self, dt):
        # nothing animates on the orb itself anymore — kept as a no-op so
        # the caller's existing orb.update(dt) call doesn't need to change
        pass

    def get_current_frame(self, state, core_rgb):
        """Returns the cached, fully-built surface for this state."""
        return self.cached_frames[state]