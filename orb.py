import pygame
import pygame.surfarray as surfarray
import numpy as np


def add_subtle_grain(orb_surf, max_deviation=5):
    result = orb_surf.copy()
    rgb_array = surfarray.pixels3d(result)  # direct view into the RGB pixel data
    alpha_array = surfarray.pixels_alpha(result)  # direct view into the alpha channel

    # alpha as a 0.0-1.0 multiplier, broadcast to match the RGB array's shape
    alpha_strength = (alpha_array.astype(np.float32) / 255.0)[:, :, np.newaxis]

    raw_noise = np.random.randint(-max_deviation, max_deviation + 1, rgb_array.shape, dtype=np.int16)
    scaled_noise = (raw_noise.astype(np.float32) * alpha_strength).astype(np.int16)

    new_vals = rgb_array.astype(np.int16) + scaled_noise
    np.clip(new_vals, 0, 255, out=new_vals)
    rgb_array[:] = new_vals.astype(np.uint8)

    del rgb_array  # release the surface locks created by pixels3d/pixels_alpha
    del alpha_array
    return result


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.9):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = center  # one gradient step per pixel of radius -- eliminates banding

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


class Orb:
    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_frames = {}  # state -> final orb+grain surface
        for state, (core, edge) in orb_colors.items():
            base = generate_orb_surface(core, edge, orb_size)
            self.cached_frames[state] = add_subtle_grain(base, max_deviation=5)

    def update(self, dt):
        # nothing animates on the orb itself anymore — kept as a no-op so
        # the caller's existing orb.update(dt) call doesn't need to change
        pass

    def get_current_frame(self, state, core_rgb):
        """Returns the cached, fully-built surface for this state."""
        return self.cached_frames[state]