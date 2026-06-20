"""
starfield.py — generates and animates the background star field for Solu.

Design (locked in with Seyi):
- ~60-80 stars, pre-generated once at startup, never reshuffled
- Soft round dots, varying size = depth (parallax layers)
- Slow constant ambient drift + per-star twinkle pulses, staggered randomly
- ALL stars match the orb's current color, crossfading at the exact same
  speed/timing as the orb itself (no lag, no wave effect)
- Stars are drawn BEFORE the orb every frame, so the orb and its glow
  simply cover/occlude whatever stars are behind it — no occlusion math needed
- Hidden during "alarm" state (urgent focus, no ambient distraction)
- Can be paused/dimmed externally (e.g. while the info panel is showing)
"""

import random
import math

# ---- Tunable constants ----
NUM_STARS = 70  # within the agreed 60-80 "balanced" range

# Depth layers control parallax: farther stars are smaller, dimmer, and drift slower.
# Each star gets a random depth between 0.0 (far) and 1.0 (near) at creation time.
MIN_STAR_RADIUS = 1
MAX_STAR_RADIUS = 2  # shrunk from 3 — stars were reading too big/bold

MIN_DRIFT_SPEED = 2.0   # pixels per second, far stars
MAX_DRIFT_SPEED = 10.0  # pixels per second, near stars

TWINKLE_CHANCE_PER_SECOND = 0.15  # rough odds any given star starts a twinkle pulse in a given second
TWINKLE_DURATION = 0.6            # how long one twinkle pulse takes, seconds
TWINKLE_BRIGHTNESS_BOOST = 0.6    # how much brighter a star gets at the peak of its twinkle (0-1 scale)


class Star:
    """A single star: position, depth-derived size/speed, and twinkle state."""

    __slots__ = (
        "x", "y", "depth", "radius", "drift_speed", "drift_angle",
        "base_brightness", "twinkle_active", "twinkle_start_time",
    )

    def __init__(self, screen_w, screen_h):
        self.x = random.uniform(0, screen_w)
        self.y = random.uniform(0, screen_h)

        # depth 0.0 = far (small, dim, slow) -> 1.0 = near (bigger, brighter, faster)
        self.depth = random.random()

        self.radius = MIN_STAR_RADIUS + (MAX_STAR_RADIUS - MIN_STAR_RADIUS) * self.depth
        self.drift_speed = MIN_DRIFT_SPEED + (MAX_DRIFT_SPEED - MIN_DRIFT_SPEED) * self.depth

        # each star drifts in its own fixed random direction, forever, at constant speed
        self.drift_angle = random.uniform(0, 2 * math.pi)

        # base brightness also tied to depth, so near stars sit slightly brighter at rest
        self.base_brightness = 0.4 + 0.4 * self.depth  # 0.4 to 0.8 baseline

        self.twinkle_active = False
        self.twinkle_start_time = 0.0


class Starfield:
    """
    Owns the full set of stars and knows how to update/draw them.

    Usage:
        field = Starfield(screen_w, screen_h)
        field.update(dt, current_color_rgb)      # call once per frame
        field.draw(surface, alpha_multiplier=1.0) # call once per frame
    """

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.stars = [Star(screen_w, screen_h) for _ in range(NUM_STARS)]
        self._time_accum = 0.0

    def update(self, dt, now):
        """
        Advances drift and randomly triggers/expires twinkles.
        dt: seconds since last frame (for movement)
        now: time.time() snapshot, shared with twinkle timing
        """
        w, h = self.screen_w, self.screen_h

        for star in self.stars:
            # drift, wrapping around screen edges so stars never just disappear
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

            # twinkle state machine: randomly start one, let it expire on its own
            if star.twinkle_active:
                if now - star.twinkle_start_time >= TWINKLE_DURATION:
                    star.twinkle_active = False
            else:
                # chance per frame scaled by dt, so the overall rate stays
                # roughly TWINKLE_CHANCE_PER_SECOND regardless of frame rate
                if random.random() < TWINKLE_CHANCE_PER_SECOND * dt:
                    star.twinkle_active = True
                    star.twinkle_start_time = now

    def _get_star_brightness(self, star, now):
        """Returns 0.0-1.0 brightness for one star, factoring in any active twinkle."""
        brightness = star.base_brightness

        if star.twinkle_active:
            elapsed = now - star.twinkle_start_time
            progress = elapsed / TWINKLE_DURATION
            # sine bump: 0 -> 1 -> 0 across the twinkle's lifetime, same trick
            # used for the orb's touch-pulse curve
            pulse = math.sin(progress * math.pi)
            brightness += pulse * TWINKLE_BRIGHTNESS_BOOST

        return min(brightness, 1.0)

    def draw(self, surface, color_rgb, now, alpha_multiplier=1.0):
        """
        Draws every star onto the given surface, tinted to color_rgb,
        with per-star brightness/twinkle applied, scaled by alpha_multiplier
        (used to dim/pause the field when the info panel is showing, or
        to hide it entirely during alarm by passing alpha_multiplier=0.0).
        """
        if alpha_multiplier <= 0.0:
            return  # nothing to draw, skip the work entirely (e.g. alarm state)

        import pygame  # local import keeps this module importable without pygame for quick tests

        r, g, b = color_rgb

        for star in self.stars:
            brightness = self._get_star_brightness(star, now) * alpha_multiplier
            if brightness <= 0.02:
                continue  # not worth drawing an essentially-invisible dot

            star_color = (
                int(r * brightness),
                int(g * brightness),
                int(b * brightness),
            )

            pygame.draw.circle(
                surface,
                star_color,
                (int(star.x), int(star.y)),
                max(1, int(round(star.radius))),
            )