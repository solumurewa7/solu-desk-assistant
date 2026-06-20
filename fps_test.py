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
from orbit_particles import OrbitSystem, draw_particle_list

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


def add_sheen(orb_surf, size, angle, intensity_rgb):
    """
    Draws a subtle shifting highlight/sheen on the orb's surface — a soft
    bright patch that rotates around the orb over time, faking the sense
    of light catching a curved 3D surface without any real 3D math.

    angle: current rotation angle in radians, driven externally
    intensity_rgb: the orb's own core color, used to tint the sheen so it
    reads as "brighter version of this orb" rather than a generic white
    glare sitting on top.
    """
    sheen_surf = pygame.Surface((size, size), pygame.SRCALPHA)

    center = size // 2
    # the sheen sits near the orb's edge and rotates around it — radius
    # slightly inside the orb's own radius so it reads as ON the surface
    sheen_radius = int(center * 0.78)
    sx = center + math.cos(angle) * sheen_radius
    sy = center + math.sin(angle) * sheen_radius

    sheen_blob_radius = int(size * 0.22)

    r, g, b = intensity_rgb
    # push toward white-ish brightness for the sheen itself, but keep some
    # of the orb's own hue so it doesn't look like a foreign white blob
    sheen_color = (
        min(255, int(r + (255 - r) * 0.55)),
        min(255, int(g + (255 - g) * 0.55)),
        min(255, int(b + (255 - b) * 0.55)),
    )

    # soft sheen via the same downscale/upscale blur trick used for the glow
    small = max(2, sheen_blob_radius // 4)
    blob = pygame.Surface((sheen_blob_radius * 2, sheen_blob_radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(blob, (*sheen_color, 200), (sheen_blob_radius, sheen_blob_radius), sheen_blob_radius)
    shrunk = pygame.transform.smoothscale(blob, (small, small))
    soft = pygame.transform.smoothscale(shrunk, (sheen_blob_radius * 2, sheen_blob_radius * 2))
    soft.set_alpha(90)  # subtle, per the "sheen only, no distinct shapes" decision

    sheen_surf.blit(soft, (int(sx - sheen_blob_radius), int(sy - sheen_blob_radius)))

    # clip the sheen to the orb's own circular silhouette so it never spills
    # outside the orb's edge — done by masking against the orb's alpha
    mask_surf = orb_surf.copy()
    mask_surf.blit(sheen_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # BLEND_RGBA_MULT against the orb keeps the sheen only where the orb's
    # own alpha is already opaque, so it can't bleed past the circle edge

    result = orb_surf.copy()
    result.blit(sheen_surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return result


SHEEN_SPEED_MULTIPLIER = {
    "sleep":  0.15,
    "idle":   0.4,
    "speak":  1.2,
    "joking": 1.1,
    "think":  1.4,
    "error":  0.9,
    "alarm":  0.6,
}


def add_glow(orb_surf, size):
    """
    Soft glow via the downscale -> upscale trick: shrinking and growing a
    surface with smoothscale's bilinear filtering produces a natural blur
    for free, no custom blur kernel needed.

    Tightened per feedback: the original 1.7x canvas + alpha 110 spread the
    glow far wider than the orb itself, making it look like a second,
    fainter orb rather than a rim of light. Pulled the canvas in and the
    glow layer closer to the orb's actual edge, and dropped the opacity
    so it reads as a tight halo, not a second circle.
    """
    glow_canvas_size = int(size * 1.25)  # was 1.7x — much tighter now
    glow_canvas = pygame.Surface((glow_canvas_size, glow_canvas_size), pygame.SRCALPHA)

    # the glow layer itself is only slightly bigger than the orb, not 1.3x+ —
    # this keeps the blur concentrated right at the edge rather than spreading
    glow_layer_size = int(size * 1.08)
    small_size = max(4, glow_layer_size // 6)
    shrunk = pygame.transform.smoothscale(orb_surf, (small_size, small_size))
    blurred = pygame.transform.smoothscale(shrunk, (glow_layer_size, glow_layer_size))

    blurred.set_alpha(70)  # was 110 — softer so it doesn't look like a second orb

    glow_pos_in_canvas = ((glow_canvas_size - glow_layer_size) // 2, (glow_canvas_size - glow_layer_size) // 2)
    glow_canvas.blit(blurred, glow_pos_in_canvas)

    # paste the sharp orb on top, centered
    orb_pos = ((glow_canvas_size - size) // 2, (glow_canvas_size - size) // 2)
    glow_canvas.blit(orb_surf, orb_pos)

    return glow_canvas


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
    clock = pygame.time.Clock()

    starfield = Starfield(SCREEN_W, SCREEN_H)
    orbit_system = OrbitSystem(ORB_SIZE)

    # cache one glowing orb surface per state, generated once (base orb + glow,
    # WITHOUT the sheen baked in — sheen rotates independently every frame
    # so it can't be cached the same way)
    cached_orbs = {}
    for state, (core, edge) in ORB_COLORS.items():
        orb = generate_orb_surface(core, edge, ORB_SIZE)
        cached_orbs[state] = add_glow(orb, ORB_SIZE)

    current_state = "idle"
    sheen_angle = 0.0

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

        base_orb = cached_orbs[current_state]
        new_size = int(base_orb.get_width() * scale)

        # rotate the sheen, speed driven by state, then apply it fresh each frame
        sheen_speed_mult = SHEEN_SPEED_MULTIPLIER.get(current_state, 0.4)
        sheen_angle += 0.8 * sheen_speed_mult * dt
        if sheen_angle > 2 * math.pi:
            sheen_angle -= 2 * math.pi

        # sheen is applied to the orb at its native (unglowed-canvas) size first,
        # then we re-glow... actually simpler: apply sheen to the cached
        # glow-canvas surface directly, since the orb sits centered within it
        # and the sheen math is relative to that surface's own size
        orb_with_sheen = add_sheen(base_orb, base_orb.get_width(), sheen_angle, core_rgb)
        scaled_orb = pygame.transform.smoothscale(orb_with_sheen, (new_size, new_size))

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