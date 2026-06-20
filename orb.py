import pygame


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.97):
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

        self.cached_frames = {}  # state -> final orb surface, pure gradient
        for state, (core, edge) in orb_colors.items():
            self.cached_frames[state] = generate_orb_surface(core, edge, orb_size)

    def update(self, dt):
        # nothing animates on the orb itself anymore — kept as a no-op so
        # the caller's existing orb.update(dt) call doesn't need to change
        pass

    def get_current_frame(self, state, core_rgb):
        """Returns the cached, fully-built surface for this state."""
        return self.cached_frames[state]