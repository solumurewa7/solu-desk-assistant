"""
orbit_particles.py — particles orbiting outside the orb, like planets
around a sun. Each particle has its own random tilt, orbit size, and
speed, so they pass behind the orb (hidden) and in front of it
(visible against the starfield) independently of each other.
"""

import math
import random


NUM_PARTICLES = 8

BASE_ORBIT_SPEED = 0.5  # radians per second baseline, scaled per state

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

MIN_ORBIT_RADIUS_RATIO = 1.15  # orbit radius is always larger than the orb's own radius
MAX_ORBIT_RADIUS_RATIO = 1.55


class OrbitParticle:
    """One particle with its own random orbital plane, orbiting outside the orb."""

    __slots__ = (
        "phase_offset", "tilt", "orbit_radius_ratio", "squash",
        "speed_scale", "trail",
    )

    def __init__(self, index, total_count):
        self.phase_offset = (index / total_count) * 2 * math.pi  # evenly spaced starting positions
        self.tilt = random.uniform(0, math.pi)
        self.orbit_radius_ratio = random.uniform(MIN_ORBIT_RADIUS_RATIO, MAX_ORBIT_RADIUS_RATIO)
        self.squash = random.uniform(0.35, 0.85)  # how flattened the orbit looks from this viewing angle
        self.speed_scale = random.uniform(0.75, 1.35)
        self.trail = []

    def get_state(self, t, base_speed, orb_radius_px):
        """Returns (x, y, depth_scale, is_behind) as pixel offsets from the orb's center."""
        angle = self.phase_offset + t * base_speed * self.speed_scale
        orbit_radius_px = orb_radius_px * self.orbit_radius_ratio

        local_x = math.cos(angle) * orbit_radius_px
        local_y = math.sin(angle) * orbit_radius_px * self.squash

        x = local_x * math.cos(self.tilt) - local_y * math.sin(self.tilt)
        y = local_x * math.sin(self.tilt) + local_y * math.cos(self.tilt)

        depth_factor = math.sin(angle)
        is_behind = depth_factor < 0
        depth_scale = 0.7 + 0.3 * ((depth_factor + 1) / 2)

        return x, y, depth_scale, is_behind


class OrbitSystem:
    """Owns all particles. Call update() once per frame, then
    get_split_particles() to get the behind/in-front lists to draw."""

    def __init__(self):
        self.particles = [OrbitParticle(i, NUM_PARTICLES) for i in range(NUM_PARTICLES)]
        self.elapsed = 0.0

    def update(self, dt, state):
        speed_mult = STATE_SPEED_MULTIPLIER.get(state, 0.6)
        self.elapsed += dt * speed_mult

    def get_split_particles(self, center_x, center_y, orb_radius_px):
        """Returns (behind_list, in_front_list) of (x, y, depth_scale, trail) tuples in screen coordinates."""
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
    """Draws particle entries with fading trail streaks, tinted to color_rgb."""
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