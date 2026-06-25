import pygame


def generate_orb_surface(core_rgb, edge_rgb, size, fade_start_fraction=0.97):
    """Builds a radial-gradient orb surface, sharp edge (fades only in the outer 3% of the radius)."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = center  # one step per pixel of radius, avoids visible banding

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
    """Caches one pre-rendered gradient surface per state. The sleep
    surface is the only one that ever regenerates, since it's dimmed to
    fully invisible at night."""

    def __init__(self, orb_size, orb_colors):
        self.orb_size = orb_size
        self.orb_colors = orb_colors

        self.cached_frames = {}
        for state, (core, edge) in orb_colors.items():
            self.cached_frames[state] = generate_orb_surface(core, edge, orb_size)

        self.sleep_is_dimmed = False  # tracks whether the cached sleep frame is currently the night (invisible) version

    def update(self, dt):
        pass  # nothing animates on the orb's own texture, kept for interface compatibility

    def get_current_frame(self, state, core_rgb):
        """Returns the cached surface for this state."""
        return self.cached_frames[state]

    def refresh_sleep_frame(self, is_night):
        """Regenerates the cached sleep frame only when day/night actually
        changes -- full brightness during the day, fully invisible at night."""
        if is_night == self.sleep_is_dimmed:
            return

        core, edge = self.orb_colors["sleep"]

        if is_night:
            core = (0, 0, 0)
            edge = (0, 0, 0)

        self.cached_frames["sleep"] = generate_orb_surface(core, edge, self.orb_size)
        self.sleep_is_dimmed = is_night