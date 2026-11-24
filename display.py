"""
display.py: Solu's visual layer (orb, starfield, info panel, reminder panel).
Run directly to preview the display on its own: python3 display.py
"""

import math
import os
import threading
import time
from datetime import datetime

import pygame

from orb import Orb
from starfield import Starfield
from orbit_particles import OrbitSystem, draw_particle_list

# ============================================================================
# CONSTANTS
# ============================================================================

SCREEN_W = 800
SCREEN_H = 480
ORB_SIZE = 340

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "Rubik.ttf")
EMOJI_FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "NotoColorEmoji.ttf")

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

WEATHER_REFRESH_SECONDS = 600
FPS = 60

WEATHER_ICONS = {
    "clear": "\u2600", "sunny": "\u2600",
    "cloud": "\u2601", "overcast": "\u2601",
    "rain": "\U0001F327", "drizzle": "\U0001F326",
    "storm": "\u26C8", "thunder": "\u26C8",
    "snow": "\u2744",
    "fog": "\U0001F32B", "mist": "\U0001F32B", "haze": "\U0001F32B",
    "wind": "\U0001F4A8",
}
DEFAULT_WEATHER_ICON = "\U0001F321"


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
      set_state(state), show_reminder(reminder), dismiss_reminder(),
      claim_wake(), try_start_alarm(reminder)
    Those are safe to call from any thread.
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

        self.starfield = Starfield(SCREEN_W, SCREEN_H, STAR_COLOR)
        self.orb = Orb(ORB_SIZE, ORB_COLORS)
        self.orb.warm_up()
        self.orbit_system = OrbitSystem()

        # state machine. The voice and reminder threads change state while
        # this thread draws, so changes and reads of it go through this lock
        self.state_lock = threading.RLock()
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
        self._text_cache = {}

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
        with self.state_lock:
            if state == self.current_state:
                return
            self.transition_from_state = self.current_state
            self.transition_start_time = time.time()
            self.current_state = state

    def show_reminder(self, reminder):
        """reminder: dict with at least 'time' (e.g. '14:30') and 'message' keys."""
        with self.state_lock:
            self.reminder_data = reminder
            self.reminder_panel_visible = True
            self.orb_target_x_ratio = REMINDER_LEFT_X_RATIO

    def dismiss_reminder(self):
        """Hides the reminder panel and returns the orb to sleep."""
        with self.state_lock:
            self.reminder_panel_visible = False
            self.set_state("sleep")

    def claim_wake(self):
        """Called when the wake word is heard. Atomically decides what it
        means: "alarm" if an alarm is ringing, otherwise "conversation".
        Either way the orb goes to idle (listening)."""
        with self.state_lock:
            meaning = "alarm" if self.current_state == "alarm" else "conversation"
            self.set_state("idle")
            return meaning

    def try_start_alarm(self, reminder):
        """Shows the reminder and starts the alarm, but only if Solu is
        asleep. Checked and done under one lock so a conversation can't
        start in between. Returns True if the alarm started."""
        with self.state_lock:
            if self.current_state != "sleep":
                return False
            self.show_reminder(reminder)
            self.set_state("alarm")
            return True

    def stop(self):
        self.running = False

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    def run(self):
        threading.Thread(target=self._weather_loop, daemon=True).start()
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
            self.clock.tick(FPS)

        pygame.quit()

    # ------------------------------------------------------------------
    # INPUT HANDLING
    # ------------------------------------------------------------------

    def _on_tap(self, x, y):
        if self.current_state == "speak":
            # tapping anywhere while Solu is talking stops the speech immediately
            process = self.active_speech_process
            if process is not None and process.poll() is None:
                process.terminate()
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

    def _weather_loop(self):
        """Refreshes the weather in the background so a slow network never freezes the screen.
        Keeps the last known value if a fetch fails."""
        try:
            from weather import get_weather
        except Exception as e:
            print(f"display: weather unavailable: {e!r}")
            return
        while True:
            data = get_weather()
            if data:
                self.cached_weather_str = f"{data['temp']}\u00b0F  {data['description'].title()}"
            time.sleep(WEATHER_REFRESH_SECONDS)

    def get_sleep_brightness_multiplier_is_night(self):
        """True between 9pm and 8am, used to make the sleep orb invisible at night."""
        hour = datetime.now().hour
        return hour >= 21 or hour < 8

    def _get_effective_transition_duration(self, from_state, state):
        """
        Any transition involving 'sleep' uses a much faster duration
        (0.15s instead of the normal 0.6s). Sleep's near-white/invisible
        color blends into a muddy, washed-out color partway through a
        normal-speed crossfade with any brighter state. This isn't a
        bug (the blend math is correct), it's just an inherent visual
        side effect of that specific color combination, so the fix is
        making the transition fast enough that it's not noticeable.
        """
        if "sleep" in (from_state, state):
            return 0.15
        return self.transition_duration

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    def _render_frame(self, now, dt):
        self.screen.fill(COLOR_BG)

        # one consistent snapshot of the state for this whole frame
        with self.state_lock:
            state = self.current_state
            from_state = self.transition_from_state
            transition_start = self.transition_start_time
        progress = 1.0
        if from_state is not None:
            progress = min((now - transition_start) / self._get_effective_transition_duration(from_state, state), 1.0)
            if progress >= 1.0:
                with self.state_lock:
                    if self.transition_start_time == transition_start:
                        self.transition_from_state = None
                from_state = None

        core_rgb = ORB_COLORS[state][0]
        if from_state is not None:
            core_rgb = interpolate_color(ORB_COLORS[from_state][0], core_rgb, progress)

        self.starfield.update(dt, now)
        if state != "alarm":
            self.starfield.draw(self.screen, now)

        self.orb.set_night(self.get_sleep_brightness_multiplier_is_night())
        self._draw_orb(dt, state, from_state, progress, core_rgb)
        self._update_and_draw_info_panel(now)
        self._update_and_draw_reminder_panel(now)

    def _draw_orb(self, dt, state, from_state, progress, core_rgb):
        scale = self._get_breathing_scale() + self._get_touch_pulse_boost()
        self.orb_current_x_ratio += (self.orb_target_x_ratio - self.orb_current_x_ratio) * ORB_POSITION_EASE_SPEED

        orb_center_x = int(SCREEN_W * self.orb_current_x_ratio)
        orb_center_y = SCREEN_H // 2
        diameter = ORB_SIZE * scale

        # particles behind the orb draw first, then the orb, then particles in front --
        # draw order alone produces correct occlusion
        self.orbit_system.update(dt, state)
        if state != "alarm":
            behind, in_front = self.orbit_system.get_split_particles(orb_center_x, orb_center_y, diameter / 2)
            draw_particle_list(self.screen, behind, core_rgb)

        if from_state is not None:
            self._blit_orb(from_state, diameter, 1.0, orb_center_x, orb_center_y)
            self._blit_orb(state, diameter, progress, orb_center_x, orb_center_y)
        else:
            self._blit_orb(state, diameter, 1.0, orb_center_x, orb_center_y)

        if state != "alarm":
            draw_particle_list(self.screen, in_front, core_rgb)

    def _blit_orb(self, state, diameter, alpha, center_x, center_y):
        """Draws the orb at a fractional size. Blits can only land on whole
        pixels, so the frame one size step up is blended in by the leftover
        fraction. That makes breathing glide instead of stepping."""
        low = int(diameter // 2) * 2  # even sizes keep the orb exactly centered
        fraction = (diameter - low) / 2.0
        for size, weight in ((low, 1.0), (low + 2, fraction)):
            a = int(round(255 * alpha * weight))
            if a <= 0:
                continue
            frame = self.orb.get_frame(state, size)
            frame.set_alpha(a)
            self.screen.blit(frame, (center_x - size // 2, center_y - size // 2))

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

        now_dt = datetime.now()
        time_surf = self._render_text(self.font_primary, now_dt.strftime("%-I:%M %p"), primary_color)
        self.screen.blit(time_surf, (20, 14))

        date_surf = self._render_text(self.font_secondary, now_dt.strftime("%B %d"), secondary_color)
        self.screen.blit(date_surf, (20, 64))

        weather_str = self.cached_weather_str
        icon = DEFAULT_WEATHER_ICON
        lower_desc = weather_str.lower()
        for keyword, emoji in WEATHER_ICONS.items():
            if keyword in lower_desc:
                icon = emoji
                break

        temp_number = weather_str.split("\u00b0")[0] if "\u00b0" in weather_str else "--"
        temp_text = f"{temp_number}\u00b0"
        weather_desc = weather_str.split("  ", 1)[1] if "  " in weather_str else ""

        temp_surf = self._render_text(self.font_primary, temp_text, primary_color)

        icon_surf = self._get_icon_surface(icon, temp_surf.get_height())
        icon_surf.set_alpha(int(255 * self.info_fade_progress))

        pair_width = icon_surf.get_width() + 8 + temp_surf.get_width()
        pair_right_x = SCREEN_W - 20
        icon_x = pair_right_x - pair_width
        temp_x = icon_x + icon_surf.get_width() + 8

        self.screen.blit(icon_surf, (icon_x, 14))
        self.screen.blit(temp_surf, (temp_x, 14))

        desc_surf = self._render_text(self.font_secondary, weather_desc, secondary_color)
        self.screen.blit(desc_surf, (SCREEN_W - 20 - desc_surf.get_width(), 64))

    def _render_text(self, font, text, color):
        """font.render with a small cache, the same text and color repeat every frame."""
        key = (id(font), text, color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 200:
                self._text_cache.clear()
            surf = font.render(text, True, color)
            self._text_cache[key] = surf
        return surf

    def _get_icon_surface(self, icon, height):
        """NotoColorEmoji ignores both requested size and color, so the rendered
        emoji is scaled manually (and cached, scaling every frame is slow)."""
        key = ("icon", icon, height)
        surf = self._text_cache.get(key)
        if surf is None:
            raw = self.font_emoji.render(icon, True, COLOR_PRIMARY_TEXT)
            scale = height / raw.get_height()
            surf = pygame.transform.smoothscale(raw, (max(1, int(raw.get_width() * scale)), height))
            self._text_cache[key] = surf
        return surf

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

        with self.state_lock:
            if not self.reminder_panel_visible and self.reminder_fade_progress == 0.0:
                if self.reminder_data is not None:
                    self.orb_target_x_ratio = CENTER_X_RATIO
                self.reminder_data = None

        reminder = self.reminder_data
        if reminder is None or self.reminder_fade_progress <= 0.01:
            return

        time_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, self.reminder_fade_progress)
        msg_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, self.reminder_fade_progress)

        raw_time = reminder.get("time", "")
        try:
            parsed_time = datetime.strptime(raw_time, "%H:%M")
            display_time = parsed_time.strftime("%-I:%M %p")
        except ValueError:
            display_time = raw_time

        time_surf = self.font_reminder_time.render(display_time, True, time_color)
        self.screen.blit(time_surf, (int(SCREEN_W * 0.62), 180))

        message = reminder.get("message", "")
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