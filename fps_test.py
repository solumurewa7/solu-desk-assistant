"""
fps_test.py — bare-bones sanity test for the Pygame rewrite.

Goal: validate the core rendering approach (starfield + glowing orb,
cached-per-state glow, color crossfade, directional light, grain texture,
orbiting particles) actually performs well before we build the full
display.py back up on top of it.

This is throwaway/diagnostic, not part of the final project structure.
Run it, watch the printed FPS, then we decide whether the approach holds.
"""

import pygame
import math
import time

from starfield import Starfield
from orbit_particles import OrbitSystem, draw_particle_list
from orb import Orb

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


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
    clock = pygame.time.Clock()

    starfield = Starfield(SCREEN_W, SCREEN_H)
    orbit_system = OrbitSystem(ORB_SIZE)
    orb = Orb(ORB_SIZE, ORB_COLORS)

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

        # stars and orbit particles drawn first, orb on top -> natural occlusion.
        # alarm hides both the starfield and the orbiting particles, per plan.
        core_rgb, _ = ORB_COLORS[current_state]
        starfield.update(dt, now)
        if current_state != "alarm":
            starfield.draw(screen, core_rgb, now, alpha_multiplier=1.0)

        # breathing pulse, same sine-wave technique as the old version
        cycle_seconds = 4
        t = now % cycle_seconds
        wave = math.sin((t / cycle_seconds) * 2 * math.pi)
        scale = 1.0 + (wave * 0.02)

        orb.update(dt)
        base_frame = orb.get_current_frame(current_state, core_rgb)

        new_size = int(base_frame.get_width() * scale)
        scaled_orb = pygame.transform.smoothscale(base_frame, (new_size, new_size))

        orb_center_x = SCREEN_W // 2
        orb_center_y = SCREEN_H // 2

        if current_state != "alarm":
            orbit_system.update(dt, current_state)
            behind, in_front = orbit_system.get_split_particles(orb_center_x, orb_center_y)
            draw_particle_list(screen, behind, core_rgb)

        screen.blit(scaled_orb, (orb_center_x - new_size // 2, orb_center_y - new_size // 2))

        if current_state != "alarm":
            draw_particle_list(screen, in_front, core_rgb)

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