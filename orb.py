"""
orb.py: the orb's pre-rendered frames.

Every pixel is computed directly with numpy instead of stacking pygame
circles, so the edge is a mathematically smooth circle and the gradient has
no banding.
"""

from collections import OrderedDict

import numpy as np
import pygame

NIGHT_COLORS = ((0, 0, 0), (0, 0, 0))  # sleep orb is invisible at night
CACHE_LIMIT = 80                       # frames kept, about 40MB at most


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.97):
    """Radial gradient from core (center) to edge color, fully opaque until
    fade_start_fraction of the radius, then fading smoothly to transparent."""
    center = (size - 1) / 2.0
    coords = np.arange(size, dtype=np.float32) - center
    t = np.hypot(coords[None, :], coords[:, None]) / (size / 2.0)  # 0 at center, 1 at the edge

    core = np.array(core_rgb, dtype=np.float32)
    edge = np.array(edge_rgb, dtype=np.float32)
    rgb = edge + (core - edge) * np.clip(1.0 - t, 0.0, 1.0)[..., None]
    rgb += np.random.default_rng(0).uniform(-0.5, 0.5, rgb.shape)  # dither, hides 8-bit banding

    alpha = np.clip((1.0 - t) / (1.0 - fade_start_fraction), 0.0, 1.0) * 255.0

    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(np.round(rgb), 0, 255)
    rgba[..., 3] = np.round(alpha)
    surf = pygame.image.frombuffer(rgba.tobytes(), (size, size), "RGBA")
    try:
        return surf.convert_alpha()  # faster blits, needs the display to exist
    except pygame.error:
        return surf.copy()


class Orb:
    """Hands out orb frames per (state, size). Each state is rendered once as a
    large master, and each size is a high-quality shrink of it, made the first
    time it's needed (fast) and cached."""

    MASTER_SIZE = 736  # about 2x the biggest size shown, so shrinking also smooths the edge

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors
        self.night = False
        self.masters = {}
        self.cache = OrderedDict()

    def set_night(self, is_night):
        self.night = is_night

    def _master(self, state, night):
        master = self.masters.get((state, night))
        if master is None:
            core, edge = NIGHT_COLORS if night else self.orb_colors[state]
            master = generate_orb_surface(core, edge, self.MASTER_SIZE)
            self.masters[(state, night)] = master
        return master

    def get_frame(self, state, size):
        night = self.night and state == "sleep"
        key = (state, size, night)
        frame = self.cache.get(key)
        if frame is None:
            frame = pygame.transform.smoothscale(self._master(state, night), (size, size))
            self.cache[key] = frame
            if len(self.cache) > CACHE_LIMIT:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(key)
        return frame

    def warm_up(self):
        """Renders every state's master up front (the slow part) so state changes never stall."""
        for state in self.orb_colors:
            self._master(state, False)
        self._master("sleep", True)
