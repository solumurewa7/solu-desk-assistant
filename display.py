import pygame
import math
import time
from datetime import datetime

from orb import Orb
from starfield import Starfield
from orbit_particles import OrbitSystem, draw_particle_list

# ============================================================================
# CONSTANTS
# ============================================================================

SCREEN_W = 800
SCREEN_H = 480
ORB_SIZE = 340

FONT_PATH = "assets/fonts/Rubik.ttf"
EMOJI_FONT_PATH = "assets/fonts/NotoColorEmoji.ttf"

ORB_COLORS = {
    "sleep":  ((255, 255, 255), (180, 180, 180)),
    "idle":   ((77, 184, 255),  (10, 61, 102)),
    "speak":  ((179, 136, 255), (61, 26, 102)),
    "joking": ((105, 240, 174), (26, 102, 67)),
    "think":  ((255, 183, 77),  (102, 61, 10)),
    "error":  ((255, 82, 82),   (102, 10, 10)),
    "alarm":  ((255, 200, 0),   (102, 75, 0)),
}

COLOR_PRIMARY_TEXT = (192, 192, 192)
COLOR_SECONDARY_TEXT = (112, 112, 112)
COLOR_BG = (0, 0, 0)
STAR_COLOR = (255, 255, 255)  # stars stay fixed white, only the orb/particles follow state color

INFO_PANEL_DURATION = 5
INFO_FADE_SPEED = 0.15

REMINDER_FADE_SPEED = 0.3
ORB_POSITION_EASE_SPEED = 0.08

REMINDER_LEFT_X_RATIO = 0.28
CENTER_X_RATIO = 0.5

BREATHING_CYCLE_SECONDS = 4
BREATHING_SCALE_AMOUNT = 0.02

TOUCH_PULSE_DURATION = 0.4
TOUCH_PULSE_COOLDOWN = 0.5
TOUCH_PULSE_MAX_BOOST = 0.06


def interpolate_color(color_a, color_b, progress):
    """Blends from color_a to color_b based on progress (0.0 to 1.0)."""
    r = int(color_a[0] + (color_b[0] - color_a[0]) * progress)
    g = int(color_a[1] + (color_b[1] - color_a[1]) * progress)
    b = int(color_a[2] + (color_b[2] - color_a[2]) * progress)
    return (r, g, b)


class Display:
    """
    Owns all visual state and the render loop. Call run() to start the
    Pygame window (blocks until quit). Other code (main.py) interacts via:
      set_state(state), show_reminder(reminder), dismiss_reminder()
    """

    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
        self.clock = pygame.time.Clock()

        self.font_primary = pygame.font.Font(FONT_PATH, 38)
        self.font_secondary = pygame.font.Font(FONT_PATH, 18)
        self.font_secondary.set_bold(False)
        self.font_reminder_time = pygame.font.Font(FONT_PATH, 42)
        self.font_reminder_message = pygame.font.Font(FONT_PATH, 22)
        self.font_emoji = pygame.font.Font(EMOJI_FONT_PATH, 32)  # Rubik has no emoji glyphs, needs a real color emoji font

        self.starfield = Starfield(SCREEN_W, SCREEN_H)
        self.orb = Orb(ORB_SIZE, ORB_COLORS)
        self.orbit_system = OrbitSystem()

        # state machine
        self.current_state = "sleep"
        self.transition_from_state = None
        self.transition_start_time = 0
        self.transition_duration = 0.6

        # touch pulse
        self.touch_pulse_active = False
        self.touch_pulse_start_time = 0
        self.last_touch_pulse_time = 0

        # orb horizontal position (for reminder slide)
        self.orb_target_x_ratio = CENTER_X_RATIO
        self.orb_current_x_ratio = CENTER_X_RATIO

        # info panel
        self.info_panel_visible = False
        self.info_panel_show_time = 0
        self.info_fade_progress = 0.0

        self.cached_weather_str = "Loading weather..."
        self.last_weather_fetch = 0

        # reminder panel
        self.reminder_panel_visible = False
        self.reminder_data = None
        self.reminder_fade_progress = 0.0

        self.running = True

        # holds the live subprocess.Popen handle for whatever speech is
        # currently playing, so a tap can interrupt it (see _on_tap).
        # main.py is responsible for setting/clearing this around its
        # own speak calls.
        self.active_speech_process = None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def set_state(self, state):
        """Switch the orb to a new emotional state, crossfading from the current one."""
        if state not in ORB_COLORS:
            print(f"Warning: unknown state '{state}', ignoring")
            return
        if state == self.current_state:
            return
        self.transition_from_state = self.current_state
        self.transition_start_time = time.time()
        self.current_state = state

    def show_reminder(self, reminder):
        """reminder: dict with at least 'time' (e.g. '14:30') and 'message' keys."""
        self.reminder_data = reminder
        self.reminder_panel_visible = True
        self.orb_target_x_ratio = REMINDER_LEFT_X_RATIO

    def dismiss_reminder(self):
        """Hides the reminder panel and returns the orb to sleep."""
        self.reminder_panel_visible = False
        self.set_state("sleep")

    def stop(self):
        self.running = False

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    def run(self):
        last_frame_time = time.time()

        while self.running:
            now = time.time()
            dt = now - last_frame_time
            last_frame_time = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_tap(event.pos[0], event.pos[1])

            self._render_frame(now, dt)

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

    # ------------------------------------------------------------------
    # INPUT HANDLING
    # ------------------------------------------------------------------

    def _on_tap(self, x, y):
        if self.current_state == "speak":
            # tapping anywhere while Solu is talking stops the speech immediately
            if self.active_speech_process is not None and self.active_speech_process.poll() is None:
                self.active_speech_process.terminate()
            self.set_state("sleep")
            return

        if self.reminder_panel_visible:
            self.dismiss_reminder()
            return

        if self._is_tap_on_orb(x, y):
            now = time.time()
            if now - self.last_touch_pulse_time > TOUCH_PULSE_COOLDOWN:
                self.touch_pulse_active = True
                self.touch_pulse_start_time = now
                self.last_touch_pulse_time = now

        # tapping anywhere also reveals the info panel
        self.info_panel_visible = True
        self.info_panel_show_time = time.time()

    def _is_tap_on_orb(self, x, y):
        orb_center_x = SCREEN_W * self.orb_current_x_ratio
        orb_center_y = SCREEN_H // 2
        tap_radius = (ORB_SIZE / 2) * 1.3  # generous margin, easier to hit on a touchscreen
        distance = math.sqrt((x - orb_center_x) ** 2 + (y - orb_center_y) ** 2)
        return distance <= tap_radius

    # ------------------------------------------------------------------
    # ANIMATION HELPERS
    # ------------------------------------------------------------------

    def _get_breathing_scale(self):
        t = time.time() % BREATHING_CYCLE_SECONDS
        wave = math.sin((t / BREATHING_CYCLE_SECONDS) * 2 * math.pi)
        return 1.0 + (wave * BREATHING_SCALE_AMOUNT)

    def _get_touch_pulse_boost(self):
        if not self.touch_pulse_active:
            return 0.0
        elapsed = time.time() - self.touch_pulse_start_time
        if elapsed >= TOUCH_PULSE_DURATION:
            self.touch_pulse_active = False
            return 0.0
        progress = elapsed / TOUCH_PULSE_DURATION
        boost_curve = math.sin(progress * math.pi)
        return boost_curve * TOUCH_PULSE_MAX_BOOST

    def _get_cached_weather(self):
        """Refreshes weather at most once every 10 minutes, keeps the last known value if a fetch fails."""
        now = time.time()
        if now - self.last_weather_fetch > 600:
            try:
                from weather import get_weather
                data = get_weather()
                if data:
                    self.cached_weather_str = f"{data['temp']}\u00b0F  {data['description'].title()}"
            except Exception:
                pass
            self.last_weather_fetch = now
        return self.cached_weather_str

    def get_sleep_brightness_multiplier_is_night(self):
        """True between 11pm and 7am, used to make the sleep orb invisible at night."""
        hour = datetime.now().hour
        return hour >= 23 or hour < 7

    def _get_effective_transition_duration(self):
        """
        Any transition involving 'sleep' uses a much faster duration
        (0.15s instead of the normal 0.6s). Sleep's near-white/invisible
        color blends into a muddy, washed-out color partway through a
        normal-speed crossfade with any brighter state -- this isn't a
        bug (the blend math is correct), it's just an inherent visual
        side effect of that specific color combination, so the fix is
        making the transition fast enough that it's not noticeable.
        """
        if self.transition_from_state is not None:
            if "sleep" in (self.transition_from_state, self.current_state):
                return 0.15
        return self.transition_duration

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    def _render_frame(self, now, dt):
        self.screen.fill(COLOR_BG)

        core_rgb = self._get_current_core_rgb_for_drawing(now)

        self.starfield.update(dt, now)
        if self.current_state != "alarm":
            self.starfield.draw(self.screen, STAR_COLOR, now, alpha_multiplier=1.0)

        self.orb.refresh_sleep_frame(self.get_sleep_brightness_multiplier_is_night())
        self._draw_orb(now, dt, core_rgb)
        self._update_and_draw_info_panel(now)
        self._update_and_draw_reminder_panel(now)

    def _get_current_core_rgb_for_drawing(self, now):
        """The orb's current blended color, used to tint the orbiting particles."""
        target_core, _ = ORB_COLORS[self.current_state]

        if self.transition_from_state is not None:
            elapsed = now - self.transition_start_time
            progress = min(elapsed / self._get_effective_transition_duration(), 1.0)
            from_core, _ = ORB_COLORS[self.transition_from_state]
            return interpolate_color(from_core, target_core, progress)

        return target_core

    def _draw_orb(self, now, dt, core_rgb):
        state = self.current_state

        if self.transition_from_state is not None:
            elapsed = now - self.transition_start_time
            progress = min(elapsed / self._get_effective_transition_duration(), 1.0)

            if progress >= 1.0:
                self.transition_from_state = None
                base_orb = self.orb.get_current_frame(state, core_rgb)
            else:
                old_frame = self.orb.get_current_frame(self.transition_from_state, core_rgb)
                new_frame = self.orb.get_current_frame(state, core_rgb)
                base_orb = old_frame.copy()
                temp = new_frame.copy()
                temp.set_alpha(int(255 * progress))
                base_orb.blit(temp, (0, 0))
        else:
            base_orb = self.orb.get_current_frame(state, core_rgb)

        scale = self._get_breathing_scale() + self._get_touch_pulse_boost()
        self.orb_current_x_ratio += (self.orb_target_x_ratio - self.orb_current_x_ratio) * ORB_POSITION_EASE_SPEED

        new_size = int(base_orb.get_width() * scale)
        scaled_orb = pygame.transform.smoothscale(base_orb, (new_size, new_size))

        orb_center_x = int(SCREEN_W * self.orb_current_x_ratio)
        orb_center_y = SCREEN_H // 2
        paste_x = orb_center_x - (new_size // 2)
        paste_y = orb_center_y - (new_size // 2)

        # particles behind the orb draw first, then the orb, then particles in front --
        # draw order alone produces correct occlusion
        self.orbit_system.update(dt, state)
        if state != "alarm":
            behind, in_front = self.orbit_system.get_split_particles(
                orb_center_x, orb_center_y, new_size / 2
            )
            draw_particle_list(self.screen, behind, core_rgb)

        self.screen.blit(scaled_orb, (paste_x, paste_y))

        if state != "alarm":
            draw_particle_list(self.screen, in_front, core_rgb)

    def _update_and_draw_info_panel(self, now):
        if self.info_panel_visible and (now - self.info_panel_show_time > INFO_PANEL_DURATION):
            self.info_panel_visible = False

        target_progress = 1.0 if self.info_panel_visible else 0.0
        self.info_fade_progress += (target_progress - self.info_fade_progress) * INFO_FADE_SPEED
        if abs(self.info_fade_progress - target_progress) < 0.01:
            self.info_fade_progress = target_progress

        if self.info_fade_progress <= 0.01:
            return

        primary_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, self.info_fade_progress)
        secondary_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, self.info_fade_progress)

        time_str = datetime.now().strftime("%-I:%M %p")
        time_surf = self.font_primary.render(time_str, True, primary_color)
        self.screen.blit(time_surf, (20, 14))

        date_str = datetime.now().strftime("%B %d")
        date_surf = self.font_secondary.render(date_str, True, secondary_color)
        self.screen.blit(date_surf, (20, 64))

        weather_str = self._get_cached_weather()
        weather_icons = {
            "clear": "\u2600", "sunny": "\u2600",
            "cloud": "\u2601", "overcast": "\u2601",
            "rain": "\U0001F327", "drizzle": "\U0001F326",
            "storm": "\u26C8", "thunder": "\u26C8",
            "snow": "\u2744",
            "fog": "\U0001F32B", "mist": "\U0001F32B", "haze": "\U0001F32B",
            "wind": "\U0001F4A8",
        }
        icon = "\U0001F321"
        lower_desc = weather_str.lower()
        for keyword, emoji in weather_icons.items():
            if keyword in lower_desc:
                icon = emoji
                break

        temp_number = weather_str.split("\u00b0")[0] if "\u00b0" in weather_str else "--"
        temp_text = f"{temp_number}\u00b0"
        weather_desc = weather_str.split("  ", 1)[1] if "  " in weather_str else ""

        temp_surf = self.font_primary.render(temp_text, True, primary_color)

        # NotoColorEmoji ignores both requested size and color, so scale and
        # fade the rendered surface manually instead of trusting render() args
        icon_raw = self.font_emoji.render(icon, True, primary_color)
        icon_target_height = temp_surf.get_height()
        icon_scale = icon_target_height / icon_raw.get_height()
        icon_surf = pygame.transform.smoothscale(
            icon_raw,
            (max(1, int(icon_raw.get_width() * icon_scale)), icon_target_height),
        )
        icon_surf.set_alpha(int(255 * self.info_fade_progress))

        pair_width = icon_surf.get_width() + 8 + temp_surf.get_width()
        pair_right_x = SCREEN_W - 20
        icon_x = pair_right_x - pair_width
        temp_x = icon_x + icon_surf.get_width() + 8

        self.screen.blit(icon_surf, (icon_x, 14))
        self.screen.blit(temp_surf, (temp_x, 14))

        desc_surf = self.font_secondary.render(weather_desc, True, secondary_color)
        self.screen.blit(desc_surf, (SCREEN_W - 20 - desc_surf.get_width(), 64))

    def _update_and_draw_reminder_panel(self, now):
        """
        Handles the fade animation and the sequenced dismiss: text fades
        out first, and only once that fade fully completes does the orb
        slide back to center (doing both at once looked rushed/broken).
        """
        target_progress = 1.0 if self.reminder_panel_visible else 0.0
        self.reminder_fade_progress += (target_progress - self.reminder_fade_progress) * REMINDER_FADE_SPEED
        if abs(self.reminder_fade_progress - target_progress) < 0.01:
            self.reminder_fade_progress = target_progress

        if not self.reminder_panel_visible and self.reminder_fade_progress == 0.0:
            if self.reminder_data is not None:
                self.orb_target_x_ratio = CENTER_X_RATIO
            self.reminder_data = None

        if self.reminder_data is None or self.reminder_fade_progress <= 0.01:
            return

        time_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, self.reminder_fade_progress)
        msg_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, self.reminder_fade_progress)

        raw_time = self.reminder_data.get("time", "")
        try:
            parsed_time = datetime.strptime(raw_time, "%H:%M")
            display_time = parsed_time.strftime("%-I:%M %p")
        except ValueError:
            display_time = raw_time

        time_surf = self.font_reminder_time.render(display_time, True, time_color)
        self.screen.blit(time_surf, (int(SCREEN_W * 0.62), 180))

        message = self.reminder_data.get("message", "")
        msg_surf = self._render_wrapped_text(
            message, self.font_reminder_message, msg_color, int(SCREEN_W * 0.33)
        )
        self.screen.blit(msg_surf, (int(SCREEN_W * 0.62), 260))

    def _render_wrapped_text(self, text, font, color, max_width):
        """Manual word-wrap, since Pygame has no built-in text wrapping."""
        words = text.split(" ")
        lines = []
        current_line = ""

        for word in words:
            test_line = (current_line + " " + word).strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        line_surfaces = [font.render(line, True, color) for line in lines]
        total_height = sum(s.get_height() for s in line_surfaces) + (len(lines) - 1) * 4
        combined = pygame.Surface((max_width, max(total_height, 1)), pygame.SRCALPHA)

        y = 0
        for surf in line_surfaces:
            combined.blit(surf, (0, y))
            y += surf.get_height() + 4

        return combined


if __name__ == "__main__":
    display = Display()
    display.run()