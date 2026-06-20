"""
orbit_particles.py — orbiting "electron" particles around Solu's orb.

Design (locked in with Seyi):
- 2-3 particles, orbiting at different radii/speeds/angles for variety
- Particles always match the orb's current state color (no fixed accent color)
- Orbit path is an ellipse (squashed circle) to fake a 3D tilt — particles
  appear to swing in front of and behind the orb
- True occlusion: when a particle is on the "far side" of its ellipse, the
  orb is drawn on top of it (fully hidden), not just dimmed
- Small dots with a short fading trail behind them, for a faint
  "motion blur" / electron streak feeling
- Always present in every state EXCEPT alarm (hidden then, same as the
  starfield)
- Rotation speed is driven by orb state: slow/calm in idle/sleep, faster
  during think/speak/joking to feel more energized

Draw order required to make occlusion work correctly (handled by the caller,
display.py / fps_test.py):
    1. draw particles whose current ellipse position is "behind" the orb
    2. draw the orb itself
    3. draw particles whose current ellipse position is "in front of" the orb
This module exposes get_particles_behind() / get_particles_in_front() so the
caller can split the draw calls around the orb blit correctly.
"""

import math
import random


# how fast each particle orbits, in radians per second, scaled by a
# per-state speed multiplier (idle/sleep calm, think/speak/joking energized)
BASE_ORBIT_SPEED = 0.6

STATE_SPEED_MULTIPLIER = {
    "sleep":  0.3,
    "idle":   0.6,
    "speak":  1.4,
    "joking": 1.3,
    "think":  1.6,
    "error":  1.1,
    "alarm":  0.0,  # particles are hidden during alarm anyway, speed is moot
}

NUM_PARTICLES = 3  # within the agreed 2-3 range; 3 gives a touch more life

PARTICLE_RADIUS = 4  # base dot size at full "front" scale
TRAIL_LENGTH = 6      # how many past positions each particle remembers for its streak
TRAIL_FADE_STEP = 0.15  # how much dimmer each older trail point is


class OrbitParticle:
    """One particle: its own orbit radius (ellipse size), starting angle, and trail history."""

    __slots__ = ("orbit_radius_x", "orbit_radius_y", "angle", "angular_speed_scale", "trail")

    def __init__(self, orb_size):
        # ellipse radii are sized relative to the orb itself so this scales
        # naturally if ORB_SIZE ever changes
        base_radius = orb_size * 0.62
        self.orbit_radius_x = base_radius * random.uniform(0.9, 1.15)
        self.orbit_radius_y = base_radius * random.uniform(0.35, 0.5)  # squashed = the "tilt"

        self.angle = random.uniform(0, 2 * math.pi)

        # each particle orbits at a slightly different relative speed so
        # 3 particles don't move in lockstep
        self.angular_speed_scale = random.uniform(0.8, 1.3)

        self.trail = []  # list of (x, y, scale) tuples, most recent first


class OrbitSystem:
    """
    Owns all orbiting particles for the orb.

    Usage each frame:
        system.update(dt, state)
        behind, in_front = system.get_split_particles(orb_center_x, orb_center_y)
        # draw `behind` particles, then the orb, then `in_front` particles
    """

    def __init__(self, orb_size):
        self.orb_size = orb_size
        self.particles = [OrbitParticle(orb_size) for _ in range(NUM_PARTICLES)]

    def update(self, dt, state):
        speed_mult = STATE_SPEED_MULTIPLIER.get(state, 0.6)

        for p in self.particles:
            p.angle += BASE_ORBIT_SPEED * speed_mult * p.angular_speed_scale * dt
            if p.angle > 2 * math.pi:
                p.angle -= 2 * math.pi

    def _particle_screen_pos(self, p, center_x, center_y):
        """
        Computes a particle's current (x, y, depth_scale, is_behind) given
        its orbit angle. depth_scale (0.6 to 1.0) and is_behind together
        sell the "swinging in front of / behind the orb" illusion:
        - sin(angle) drives the ellipse's vertical squash (the "tilt")
        - cos(angle) > 0 means the particle is on the near half, < 0 = far half
        """
        x = center_x + math.cos(p.angle) * p.orbit_radius_x
        y = center_y + math.sin(p.angle) * p.orbit_radius_y

        # cos of angle's "depth" component drives whether it's in front or behind;
        # reusing sin here as a simple depth proxy keeps the ellipse and the
        # front/back split visually consistent with each other
        depth_factor = math.sin(p.angle)  # -1 (far/behind) to 1 (near/front)
        is_behind = depth_factor < 0

        # scale slightly smaller when behind, to reinforce the depth illusion
        # even though it's also fully occluded by the orb when truly behind
        depth_scale = 0.7 + 0.3 * ((depth_factor + 1) / 2)  # 0.7 to 1.0

        return x, y, depth_scale, is_behind

    def get_split_particles(self, center_x, center_y):
        """
        Returns (behind_list, in_front_list), each a list of
        (x, y, depth_scale, trail) ready to draw, already updated this frame.
        Caller draws `behind_list` first, then the orb, then `in_front_list`.
        """
        behind_list = []
        in_front_list = []

        for p in self.particles:
            x, y, depth_scale, is_behind = self._particle_screen_pos(p, center_x, center_y)

            # update this particle's trail history (most recent position first)
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
    Draws a list of (x, y, depth_scale, trail) entries with their fading
    trail streaks, tinted to color_rgb. Call once for the "behind" list
    before drawing the orb, and once for the "in_front" list after.
    """
    import pygame  # local import, same pattern as starfield.py

    r, g, b = color_rgb

    for x, y, depth_scale, trail in particle_entries:
        # draw the trail oldest-to-newest so the newest point ends up on top
        trail_count = len(trail)
        for i in range(trail_count - 1, -1, -1):
            tx, ty, tscale = trail[i]
            # older trail points (higher i) are fainter and smaller
            fade = max(0.0, 1.0 - (i * TRAIL_FADE_STEP))
            if fade <= 0.02:
                continue

            radius = max(1, int(PARTICLE_RADIUS * tscale * fade))
            trail_color = (int(r * fade), int(g * fade), int(b * fade))

            # use SRCALPHA so the faint trail dots blend smoothly rather
            # than drawing solid faint-colored circles directly to screen
            dot_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*trail_color, int(255 * fade)), (radius, radius), radius)
            surface.blit(dot_surf, (int(tx - radius), int(ty - radius)))