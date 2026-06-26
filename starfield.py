"""
starfield.py — background star field for Solu.

~70 stars, generated once at startup. Soft dots with depth-based size
and drift speed, occasional twinkle pulses, all tinted to match the
orb's current color in sync. Drawn before the orb so it naturally
occludes whatever stars sit behind it. Hidden during the alarm state.
"""

import random
import math

NUM_STARS = 35

MIN_STAR_RADIUS = 1
MAX_STAR_RADIUS = 2

MIN_DRIFT_SPEED = 2.0   # pixels/sec, far stars
MAX_DRIFT_SPEED = 10.0  # pixels/sec, near stars

TWINKLE_CHANCE_PER_SECOND = 0.15
TWINKLE_DURATION = 0.6
TWINKLE_BRIGHTNESS_BOOST = 0.6


class Star:
    """One star: position, depth-derived size/speed, and twinkle state."""

    __slots__ = (
        "x", "y", "depth", "radius", "drift_speed", "drift_angle",
        "base_brightness", "twinkle_active", "twinkle_start_time",
    )

    def __init__(self, screen_w, screen_h):
        self.x = random.uniform(0, screen_w)
        self.y = random.uniform(0, screen_h)

        self.depth = random.random()  # 0.0 far, 1.0 near
        self.radius = MIN_STAR_RADIUS + (MAX_STAR_RADIUS - MIN_STAR_RADIUS) * self.depth
        self.drift_speed = MIN_DRIFT_SPEED + (MAX_DRIFT_SPEED - MIN_DRIFT_SPEED) * self.depth
        self.drift_angle = random.uniform(0, 2 * math.pi)
        self.base_brightness = 0.4 + 0.4 * self.depth

        self.twinkle_active = False
        self.twinkle_start_time = 0.0


class Starfield:
    """Owns all stars. Call update() then draw() once per frame."""

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.stars = [Star(screen_w, screen_h) for _ in range(NUM_STARS)]

    def update(self, dt, now):
        """Advances drift and randomly starts/expires twinkles."""
        w, h = self.screen_w, self.screen_h

        for star in self.stars:
            star.x += math.cos(star.drift_angle) * star.drift_speed * dt
            star.y += math.sin(star.drift_angle) * star.drift_speed * dt

            if star.x < -5:
                star.x = w + 5
            elif star.x > w + 5:
                star.x = -5
            if star.y < -5:
                star.y = h + 5
            elif star.y > h + 5:
                star.y = -5

            if star.twinkle_active:
                if now - star.twinkle_start_time >= TWINKLE_DURATION:
                    star.twinkle_active = False
            else:
                if random.random() < TWINKLE_CHANCE_PER_SECOND * dt:
                    star.twinkle_active = True
                    star.twinkle_start_time = now

    def _get_star_brightness(self, star, now):
        brightness = star.base_brightness

        if star.twinkle_active:
            elapsed = now - star.twinkle_start_time
            progress = elapsed / TWINKLE_DURATION
            pulse = math.sin(progress * math.pi)  # 0 -> 1 -> 0 over the twinkle
            brightness += pulse * TWINKLE_BRIGHTNESS_BOOST

        return min(brightness, 1.0)

    def draw(self, surface, color_rgb, now, alpha_multiplier=1.0):
        """Draws all stars tinted to color_rgb. alpha_multiplier=0.0 hides them entirely (alarm state)."""
        if alpha_multiplier <= 0.0:
            return

        import pygame

        r, g, b = color_rgb

        for star in self.stars:
            brightness = self._get_star_brightness(star, now) * alpha_multiplier
            if brightness <= 0.02:
                continue

            star_color = (int(r * brightness), int(g * brightness), int(b * brightness))

            pygame.draw.circle(
                surface,
                star_color,
                (int(star.x), int(star.y)),
                max(1, int(round(star.radius))),
            )