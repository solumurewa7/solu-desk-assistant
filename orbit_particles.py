import math
import random


NUM_PARTICLES = 8  # comfortably within the "6+" Seyi asked for

BASE_ORBIT_SPEED = 0.5  # radians per second baseline, scaled per-particle and per-state

# how much faster/slower particles orbit depending on the orb's current state —
# carried over from the original version's intent (calmer when idle/sleep,
# more energized when actively thinking/speaking)
STATE_SPEED_MULTIPLIER = {
    "sleep":  0.25,
    "idle":   0.6,
    "speak":  1.3,
    "joking": 1.2,
    "think":  1.5,
    "error":  1.0,
    "alarm":  0.0,  # hidden during alarm anyway, multiplier is moot
}

PARTICLE_RADIUS = 4
TRAIL_LENGTH = 5
TRAIL_FADE_STEP = 0.18


class OrbitParticle:

    __slots__ = (
        "phase_offset", "tilt", "radius_a", "radius_b",
        "speed_scale", "trail",
    )

    def __init__(self, index, total_count):
        # evenly spaced starting position around the cycle, so particles
        # don't all bunch up together at startup even before their
        # individually different speeds spread them out further over time
        self.phase_offset = (index / total_count) * 2 * math.pi

        # each particle's own random orbital plane — this is the actual
        # "any angle, anywhere" requirement: a full random tilt, not
        # confined to a shared horizontal or vertical axis
        self.tilt = random.uniform(0, math.pi)

        # semi-major/semi-minor axes, relative fractions of the orb's
        # radius — randomized per particle so orbit SIZES vary too, not
        # just orientation, reinforcing the cloud-of-electrons feeling
        self.radius_a = random.uniform(0.55, 0.78)
        self.radius_b = random.uniform(0.15, 0.40)

        self.speed_scale = random.uniform(0.75, 1.35)

        self.trail = []  # list of (x, y, depth_scale) tuples, most recent first

    def _local_position(self, angle):
        local_x = math.cos(angle) * self.radius_a
        local_y = math.sin(angle) * self.radius_b
        return local_x, local_y

    def get_state(self, t, base_speed):
        angle = self.phase_offset + t * base_speed * self.speed_scale

        local_x, local_y = self._local_position(angle)

        # rotate the local ellipse position by this particle's own tilt
        # to place it in its randomly-oriented orbital plane
        x = local_x * math.cos(self.tilt) - local_y * math.sin(self.tilt)
        y = local_x * math.sin(self.tilt) + local_y * math.cos(self.tilt)

        # depth uses the UNROTATED local_y as the front/back proxy —
        # consistent regardless of tilt, since tilt only changes where
        # on screen the particle appears, not which half of its own
        # orbital cycle it's currently in
        depth_factor = math.sin(angle)  # -1 (far/behind) to 1 (near/front)
        is_behind = depth_factor < 0

        depth_scale = 0.7 + 0.3 * ((depth_factor + 1) / 2)  # 0.7 to 1.0

        return x, y, depth_scale, is_behind


class OrbitSystem:

    def __init__(self):
        self.particles = [OrbitParticle(i, NUM_PARTICLES) for i in range(NUM_PARTICLES)]
        self.elapsed = 0.0

    def update(self, dt, state):
        speed_mult = STATE_SPEED_MULTIPLIER.get(state, 0.6)
        self.elapsed += dt * speed_mult

    def get_split_particles(self, center_x, center_y, orbit_radius_px):
        behind_list = []
        in_front_list = []

        for p in self.particles:
            x_ratio, y_ratio, depth_scale, is_behind = p.get_state(self.elapsed, BASE_ORBIT_SPEED)

            x = center_x + x_ratio * orbit_radius_px
            y = center_y + y_ratio * orbit_radius_px

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
    import pygame  # local import, consistent with the rest of this project's pattern

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