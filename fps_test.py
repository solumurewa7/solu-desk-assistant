"""
fps_test.py — bare-bones sanity test for the Pygame rewrite.

Goal: validate the core rendering approach (starfield + glowing orb,
cached-per-state glow, color crossfade) actually performs well before
we build the full display.py back up on top of it.

This is throwaway/diagnostic, not part of the final project structure.
Run it, watch the printed FPS, then we decide whether the approach holds.
"""

import pygame
import math
import time
import random

from starfield import Starfield

SCREEN_W = 800
SCREEN_H = 480
ORB_SIZE = 350

ORB_COLORS = {
    "sleep":  ((20, 20, 20),    (0, 0, 0)),
    "idle":   ((77, 184, 255),  (10, 61, 102)),
    "speak":  ((179, 136, 255), (61, 26, 102)),
    "joking": ((105, 240, 174), (26, 102, 67)),
    "think":  ((255, 183, 77),  (102, 61, 10)),
    "error":  ((255, 82, 82),   (102, 10, 10)),
    "alarm":  ((255, 255, 255), (102, 102, 102)),
}


def generate_orb_surface(core_rgb, edge_rgb, size):
    """
    Builds the gradient orb as a Pygame surface using pygame.draw.circle,
    which runs in C (not a Python pixel loop like the old Pillow version).
    Concentric-circle gradient trick carries over conceptually unchanged.
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    steps = 60  # fewer steps than the old Pillow version (100) since each
                # draw.circle call has its own overhead; 60 is plenty smooth

    for i in range(steps, 0, -1):
        radius = int(center * (i / steps))
        blend = 1 - (i / steps)
        r = int(edge_rgb[0] + (core_rgb[0] - edge_rgb[0]) * blend)
        g = int(edge_rgb[1] + (core_rgb[1] - edge_rgb[1]) * blend)
        b = int(edge_rgb[2] + (core_rgb[2] - edge_rgb[2]) * blend)

        if i > steps * 0.95:
            edge_fade = (steps - i) / (steps * 0.05)
            a = int(255 * edge_fade)
        else:
            a = 255

        pygame.draw.circle(surf, (r, g, b, a), (center, center), radius)

    return surf


def add_glow(orb_surf, size):
    """
    Soft glow via the downscale -> upscale trick: shrinking and growing a
    surface with smoothscale's bilinear filtering produces a natural blur
    for free, no custom blur kernel needed. Cheap and idiomatic in Pygame.
    """
    glow_canvas_size = int(size * 1.7)
    glow_canvas = pygame.Surface((glow_canvas_size, glow_canvas_size), pygame.SRCALPHA)

    # shrink way down, then back up — the resampling itself is the blur
    small_size = max(4, glow_canvas_size // 8)
    shrunk = pygame.transform.smoothscale(orb_surf, (small_size, small_size))
    blurred = pygame.transform.smoothscale(shrunk, (glow_canvas_size, glow_canvas_size))

    # dim it down so it reads as a soft halo, not a second solid orb
    blurred.set_alpha(110)

    glow_canvas.blit(blurred, (0, 0))

    # paste the sharp orb on top, centered
    orb_pos = ((glow_canvas_size - size) // 2, (glow_canvas_size - size) // 2)
    glow_canvas.blit(orb_surf, orb_pos)

    return glow_canvas


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
    clock = pygame.time.Clock()

    starfield = Starfield(SCREEN_W, SCREEN_H)

    # cache one glowing orb surface per state, generated once
    cached_orbs = {}
    for state, (core, edge) in ORB_COLORS.items():
        orb = generate_orb_surface(core, edge, ORB_SIZE)
        cached_orbs[state] = add_glow(orb, ORB_SIZE)

    current_state = "idle"

    frame_count = 0
    fps_timer = time.time()
    last_frame_time = time.time()

    running = True
    test_states = ["idle", "speak", "joking", "think", "error", "sleep", "idle"]
    state_switch_timer = time.time()
    state_index = 0

    while running:
        now = time.time()
        dt = now - last_frame_time
        last_frame_time = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # cycle through states every 3 seconds, same as earlier validation tests
        if now - state_switch_timer > 3:
            state_switch_timer = now
            state_index = (state_index + 1) % len(test_states)
            current_state = test_states[state_index]

        screen.fill((0, 0, 0))

        # stars drawn first, orb drawn on top -> orb naturally occludes stars behind it
        core_rgb, _ = ORB_COLORS[current_state]
        starfield.update(dt, now)
        if current_state != "alarm":
            starfield.draw(screen, core_rgb, now, alpha_multiplier=1.0)

        # breathing pulse, same sine-wave technique as the old version
        cycle_seconds = 4
        t = now % cycle_seconds
        wave = math.sin((t / cycle_seconds) * 2 * math.pi)
        scale = 1.0 + (wave * 0.02)

        base_orb = cached_orbs[current_state]
        new_size = int(base_orb.get_width() * scale)
        scaled_orb = pygame.transform.smoothscale(base_orb, (new_size, new_size))

        screen.blit(scaled_orb, (SCREEN_W // 2 - new_size // 2, SCREEN_H // 2 - new_size // 2))

        pygame.display.flip()

        # FPS measurement, printed every 2 seconds, same approach as before
        frame_count += 1
        if now - fps_timer >= 2:
            fps = frame_count / (now - fps_timer)
            print(f"FPS: {fps:.1f}  (state: {current_state})")
            frame_count = 0
            fps_timer = now

        clock.tick(60)  # cap attempts at 60fps, real achieved rate is what we measure above

    pygame.quit()


if __name__ == "__main__":
    main()