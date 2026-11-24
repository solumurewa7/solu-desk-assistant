import math
import random
from collections import deque

import pygame
import pygame.gfxdraw

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

    __slots__ = ("phase_offset", "cos_tilt", "sin_tilt", "orbit_radius_ratio", "squash", "speed_scale", "trail")

    def __init__(self, index, total_count):
        self.phase_offset = (index / total_count) * 2 * math.pi  # evenly spaced starting positions
        tilt = random.uniform(0, math.pi)
        self.cos_tilt, self.sin_tilt = math.cos(tilt), math.sin(tilt)
        self.orbit_radius_ratio = random.uniform(MIN_ORBIT_RADIUS_RATIO, MAX_ORBIT_RADIUS_RATIO)
        self.squash = random.uniform(0.35, 0.85)  # how flattened the orbit looks from this viewing angle
        self.speed_scale = random.uniform(0.75, 1.35)
        self.trail = deque(maxlen=TRAIL_LENGTH)

    def get_state(self, t, base_speed, orb_radius_px):
        """Returns (x, y, depth_scale, is_behind) as pixel offsets from the orb's center."""
        angle = self.phase_offset + t * base_speed * self.speed_scale
        orbit_radius_px = orb_radius_px * self.orbit_radius_ratio

        local_x = math.cos(angle) * orbit_radius_px
        local_y = math.sin(angle) * orbit_radius_px * self.squash

        x = local_x * self.cos_tilt - local_y * self.sin_tilt
        y = local_x * self.sin_tilt + local_y * self.cos_tilt

        depth_factor = math.sin(angle)
        depth_scale = 0.7 + 0.3 * ((depth_factor + 1) / 2)
        return x, y, depth_scale, depth_factor < 0


class OrbitSystem:
    """Owns all particles. Call update() once per frame, then
    get_split_particles() to get the behind/in-front lists to draw."""

    def __init__(self):
        self.particles = [OrbitParticle(i, NUM_PARTICLES) for i in range(NUM_PARTICLES)]
        self.elapsed = 0.0

    def update(self, dt, state):
        self.elapsed += dt * STATE_SPEED_MULTIPLIER.get(state, 0.6)

    def get_split_particles(self, center_x, center_y, orb_radius_px):
        """Returns (behind_list, in_front_list), each entry is a particle's trail, newest point first."""
        behind_list = []
        in_front_list = []
        for p in self.particles:
            x_offset, y_offset, depth_scale, is_behind = p.get_state(self.elapsed, BASE_ORBIT_SPEED, orb_radius_px)
            p.trail.appendleft((center_x + x_offset, center_y + y_offset, depth_scale))
            (behind_list if is_behind else in_front_list).append(p.trail)
        return behind_list, in_front_list


def draw_particle_list(surface, trails, color_rgb):
    """Draws each particle with a fading trail, tinted to color_rgb. Draws
    straight onto the screen with alpha blending and smooth edges, no
    temporary surfaces."""
    r, g, b = color_rgb
    for trail in trails:
        for i in range(len(trail) - 1, -1, -1):
            fade = 1.0 - i * TRAIL_FADE_STEP
            if fade <= 0.02:
                continue
            tx, ty, tscale = trail[i]
            radius = max(1, int(PARTICLE_RADIUS * tscale * fade))
            color = (int(r * fade), int(g * fade), int(b * fade), int(255 * fade))
            x, y = int(tx), int(ty)
            pygame.gfxdraw.filled_circle(surface, x, y, radius, color)
            if radius >= 2:
                pygame.gfxdraw.aacircle(surface, x, y, radius, color)
