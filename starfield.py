"""
starfield.py: background star field for Solu.

Soft dots with depth-based size and drift speed, plus occasional twinkles.
Stars are drawn from small pre-rendered sprites placed at quarter-pixel
precision, so slow drift glides smoothly instead of hopping pixel to pixel.
Drawn before the orb so it naturally hides the stars behind it.
"""

import math
import random

import numpy as np
import pygame

NUM_STARS = 35

MIN_STAR_RADIUS = 1
MAX_STAR_RADIUS = 2

MIN_DRIFT_SPEED = 2.0   # pixels/sec, far stars
MAX_DRIFT_SPEED = 10.0  # pixels/sec, near stars

TWINKLE_CHANCE_PER_SECOND = 0.15
TWINKLE_DURATION = 0.6
TWINKLE_BRIGHTNESS_BOOST = 0.6

SUBPIXEL_STEPS = 4      # sprite positions per pixel, each axis
RADIUS_STEPS = 5        # sprite sizes between MIN and MAX radius
BRIGHTNESS_STEPS = 32
SPRITE_SIZE = 2 * MAX_STAR_RADIUS + 3
SUPERSAMPLE = 4         # samples per pixel per axis when rendering sprites


def _build_sprites(color_rgb):
    """sprites[radius][brightness][sub_y][sub_x], each an antialiased dot to add onto the screen."""
    color = np.array(color_rgb, dtype=np.float32)
    half = SPRITE_SIZE // 2
    offsets = (np.arange(SUPERSAMPLE) + 0.5) / SUPERSAMPLE  # sample points inside a pixel
    sample_coords = (np.arange(SPRITE_SIZE)[:, None] + offsets[None, :]).ravel() - half

    sprites = []
    for ri in range(RADIUS_STEPS):
        radius = MIN_STAR_RADIUS + (MAX_STAR_RADIUS - MIN_STAR_RADIUS) * ri / (RADIUS_STEPS - 1)
        by_brightness = []
        for bi in range(BRIGHTNESS_STEPS):
            brightness = (bi + 1) / BRIGHTNESS_STEPS
            by_y = []
            for sy in range(SUBPIXEL_STEPS):
                by_x = []
                for sx in range(SUBPIXEL_STEPS):
                    dx = sample_coords - sx / SUBPIXEL_STEPS
                    dy = sample_coords - sy / SUBPIXEL_STEPS
                    inside = (dx[None, :] ** 2 + dy[:, None] ** 2) <= radius ** 2
                    coverage = inside.reshape(SPRITE_SIZE, SUPERSAMPLE, SPRITE_SIZE, SUPERSAMPLE).mean(axis=(1, 3))
                    rgb = np.round(coverage[..., None] * color * brightness).astype(np.uint8)
                    by_x.append(pygame.surfarray.make_surface(rgb.transpose(1, 0, 2)))
                by_y.append(by_x)
            by_brightness.append(by_y)
        sprites.append(by_brightness)
    return sprites


class Star:
    """One star: position, depth-derived size/speed, and twinkle state."""

    __slots__ = ("x", "y", "radius_index", "vx", "vy", "base_brightness", "twinkle_active", "twinkle_start_time")

    def __init__(self, screen_w, screen_h):
        self.x = random.uniform(0, screen_w)
        self.y = random.uniform(0, screen_h)

        depth = random.random()  # 0.0 far, 1.0 near
        self.radius_index = round(depth * (RADIUS_STEPS - 1))
        drift_speed = MIN_DRIFT_SPEED + (MAX_DRIFT_SPEED - MIN_DRIFT_SPEED) * depth
        drift_angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(drift_angle) * drift_speed
        self.vy = math.sin(drift_angle) * drift_speed
        self.base_brightness = 0.4 + 0.4 * depth

        self.twinkle_active = False
        self.twinkle_start_time = 0.0


class Starfield:
    """Owns all stars. Call update() then draw() once per frame."""

    def __init__(self, screen_w, screen_h, color_rgb=(255, 255, 255)):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.stars = [Star(screen_w, screen_h) for _ in range(NUM_STARS)]
        self.sprites = _build_sprites(color_rgb)

    def update(self, dt, now):
        """Advances drift and randomly starts/expires twinkles."""
        w, h = self.screen_w, self.screen_h
        for star in self.stars:
            star.x += star.vx * dt
            star.y += star.vy * dt

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
            elif random.random() < TWINKLE_CHANCE_PER_SECOND * dt:
                star.twinkle_active = True
                star.twinkle_start_time = now

    def _get_star_brightness(self, star, now):
        brightness = star.base_brightness
        if star.twinkle_active:
            progress = (now - star.twinkle_start_time) / TWINKLE_DURATION
            brightness += math.sin(progress * math.pi) * TWINKLE_BRIGHTNESS_BOOST  # 0 -> 1 -> 0 over the twinkle
        return min(brightness, 1.0)

    def draw(self, surface, now, alpha_multiplier=1.0):
        """Draws all stars. alpha_multiplier scales brightness, 0 hides them."""
        if alpha_multiplier <= 0.0:
            return
        half = SPRITE_SIZE // 2
        blits = []
        for star in self.stars:
            brightness = self._get_star_brightness(star, now) * alpha_multiplier
            level = int(brightness * BRIGHTNESS_STEPS) - 1
            if level < 0:
                continue
            ix, iy = math.floor(star.x), math.floor(star.y)
            sx = int((star.x - ix) * SUBPIXEL_STEPS)
            sy = int((star.y - iy) * SUBPIXEL_STEPS)
            sprite = self.sprites[star.radius_index][level][sy][sx]
            blits.append((sprite, (ix - half, iy - half)))
        for sprite, pos in blits:
            surface.blit(sprite, pos, special_flags=pygame.BLEND_RGB_ADD)
