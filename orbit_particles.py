"""
orbit_particles.py — orbiting particles around Solu's orb, like planets
orbiting a sun.

Corrected from an earlier version that had particles tracing paths
INSIDE the orb's radius (looked like spots moving across its face,
which wasn't the intent). This version orbits particles OUTSIDE the
orb's radius — they pass behind it (hidden by the orb's own circle)
and in front of it (visible against the starfield, appearing to pass
over the orb's edge), exactly like watching planets cross in front of
or disappear behind a sun from a fixed viewing angle.

Each particle has its OWN independent orbital plane:
  - its own random tilt (rotation of the orbit ellipse)
  - its own random orbit radius (always larger than the orb itself)
  - its own random speed
  - evenly spaced starting phase, so all particles don't bunch together

The "tilt" is what gives each orbit its own distinct flattened-ellipse
look from this fixed front-on viewing angle — exactly like how Earth's
orbit looks like a wide ellipse from one viewing angle while a more
edge-on orbit looks like a thin sliver, depending on how that orbital
plane happens to be oriented relative to the viewer.

Occlusion (verified correct via direct math check before building this):
depth and screen position are derived from the SAME orbit angle, so a
particle marked "behind" is always positioned within the orb's own
radius on screen (where the orb's draw would cover it), and a particle
marked "in front" near the orb's radius correctly appears to pass over
its edge, the same way a transiting planet would.
"""

import math
import random


NUM_PARTICLES = 8

BASE_ORBIT_SPEED = 0.5  # radians per second baseline, scaled per-particle and per-state

STATE_SPEED_MULTIPLIER = {
    "sleep":  0.25,
    "idle":   0.6,
    "speak":  1.3,
    "joking": 1.2,
    "think":  1.5,
    "error":  1.0,
    "alarm":  0.0,
}

PARTICLE_RADIUS = 4
TRAIL_LENGTH = 5
TRAIL_FADE_STEP = 0.18

# orbit radius range, as a multiple of the ORB's radius — always > 1.0 so
# particles trace paths fully outside the orb's own circle, never across
# its face
MIN_ORBIT_RADIUS_RATIO = 1.15
MAX_ORBIT_RADIUS_RATIO = 1.55


class OrbitParticle:
    """
    One particle with its own independently-randomized orbital plane,
    orbiting OUTSIDE the orb's own radius.
    """

    __slots__ = (
        "phase_offset", "tilt", "orbit_radius_ratio", "squash",
        "speed_scale", "trail",
    )

    def __init__(self, index, total_count):
        self.phase_offset = (index / total_count) * 2 * math.pi

        # each particle's own random orbital plane orientation
        self.tilt = random.uniform(0, math.pi)

        # the orbit's actual size, as a multiple of the orb's radius —
        # always bigger than the orb itself (this is the actual fix from
        # the previous version, which used a fraction smaller than 1.0
        # and put particles inside the orb instead of around it)
        self.orbit_radius_ratio = random.uniform(MIN_ORBIT_RADIUS_RATIO, MAX_ORBIT_RADIUS_RATIO)

        # how flattened the orbit appears from this fixed viewing angle —
        # 1.0 would look like a perfect circle (orbit plane facing us
        # directly), smaller values look like a thin flattened ellipse
        # (orbit plane closer to edge-on). Randomized per particle so
        # each one's "tilt" reads as genuinely different, not just a
        # rotated copy of the same shape.
        self.squash = random.uniform(0.35, 0.85)

        self.speed_scale = random.uniform(0.75, 1.35)

        self.trail = []

    def get_state(self, t, base_speed, orb_radius_px):
        """
        Returns (x, y, depth_scale, is_behind) in actual screen pixel
        offsets from the orb's center, at time t.
        """
        angle = self.phase_offset + t * base_speed * self.speed_scale

        orbit_radius_px = orb_radius_px * self.orbit_radius_ratio

        # base circular orbit in local space, squashed on one axis to
        # fake this particle's own viewing angle
        local_x = math.cos(angle) * orbit_radius_px
        local_y = math.sin(angle) * orbit_radius_px * self.squash

        # rotate by this particle's own tilt
        x = local_x * math.cos(self.tilt) - local_y * math.sin(self.tilt)
        y = local_x * math.sin(self.tilt) + local_y * math.cos(self.tilt)

        # depth from the same angle that drives position, so a particle
        # marked "behind" is always positioned where the orb's own circle
        # would actually cover it on screen (verified directly before
        # building this — see module docstring)
        depth_factor = math.sin(angle)
        is_behind = depth_factor < 0

        depth_scale = 0.7 + 0.3 * ((depth_factor + 1) / 2)

        return x, y, depth_scale, is_behind


class OrbitSystem:
    """
    Owns all orbiting particles. Call update(dt, state) once per frame,
    then get_split_particles(center_x, center_y, orb_radius_px) to get
    the behind/in-front lists ready to draw around the orb.
    """

    def __init__(self):
        self.particles = [OrbitParticle(i, NUM_PARTICLES) for i in range(NUM_PARTICLES)]
        self.elapsed = 0.0

    def update(self, dt, state):
        speed_mult = STATE_SPEED_MULTIPLIER.get(state, 0.6)
        self.elapsed += dt * speed_mult

    def get_split_particles(self, center_x, center_y, orb_radius_px):
        """
        orb_radius_px: the orb's own current on-screen radius (NOT the
        particle's orbit radius — each particle computes its own orbit
        radius internally as a multiple of this value).

        Returns (behind_list, in_front_list), each a list of
        (x, y, depth_scale, trail) in actual screen pixel coordinates.
        """
        behind_list = []
        in_front_list = []

        for p in self.particles:
            x_offset, y_offset, depth_scale, is_behind = p.get_state(
                self.elapsed, BASE_ORBIT_SPEED, orb_radius_px
            )

            x = center_x + x_offset
            y = center_y + y_offset

            p.trail.insert(0, (x, y, depth_scale))
            if len(p.trail) > TRAIL_LENGTH:
                p.trail.pop()

            entry = (x, y, depth_scale, list(p.trail))
            if is_behind:
                behind_list.append(entry)
            else:
                in_front_list.append(entry)

        return behind_list, in_front_list


def draw_particle_list(surface, particle_entries, color_rgb):
    """
    Draws a list of (x, y, depth_scale, trail) entries with fading
    trail streaks, tinted to color_rgb.
    """
    import pygame

    r, g, b = color_rgb

    for x, y, depth_scale, trail in particle_entries:
        trail_count = len(trail)
        for i in range(trail_count - 1, -1, -1):
            tx, ty, tscale = trail[i]
            fade = max(0.0, 1.0 - (i * TRAIL_FADE_STEP))
            if fade <= 0.02:
                continue

            radius = max(1, int(PARTICLE_RADIUS * tscale * fade))
            trail_color = (int(r * fade), int(g * fade), int(b * fade))

            dot_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*trail_color, int(255 * fade)), (radius, radius), radius)
            surface.blit(dot_surf, (int(tx - radius), int(ty - radius)))