"""
display.py: Solu's screen. The orb, stardust and voice rings are drawn on the
GPU (see gpu_orb.py). This file handles state, touch, and the info and
reminder panels.

Preview on the Pi without the rest of Solu (stop solu.service first):
    DISPLAY=:0 python3 display.py --demo
"""

import math
import os
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime

from gpu_orb import BREATH_SECONDS, STATES, TAU, OrbMotion, Renderer, StardustRiver, VoiceRings, approach  # first: sets the Mesa GL overrides
import moderngl
import pygame

# ============================================================================
# CONSTANTS
# ============================================================================

SCREEN_W = 800
SCREEN_H = 480
ORB_RADIUS = 170

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "Rubik.ttf")
EMOJI_FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "NotoColorEmoji.ttf")

COLOR_PRIMARY_TEXT = (192, 192, 192)
COLOR_SECONDARY_TEXT = (112, 112, 112)

INFO_PANEL_DURATION = 5     # seconds the time/weather panel stays after a tap
INFO_FADE_RATE = 10.0       # fade speeds, per second (higher is snappier)
REMINDER_FADE_RATE = 20.0
ORB_SLIDE_RATE = 5.0

REMINDER_LEFT_X_RATIO = 0.28
CENTER_X_RATIO = 0.5

BREATHING_SCALE_AMOUNT = 0.015

TOUCH_PULSE_DURATION = 0.4
TOUCH_PULSE_COOLDOWN = 0.5
TOUCH_PULSE_MAX_BOOST = 0.06

TRANSITION_SECONDS = 0.6
SLEEP_TRANSITION_SECONDS = 0.25   # waking up and going to sleep feel snappier

VOICE_ATTACK_RATE = 25.0    # how fast the orb reacts when the voice gets louder
VOICE_RELEASE_RATE = 8.0    # and how fast it settles back
LISTEN_REACTION = 0.6       # how much your own voice moves the orb while it's listening

RIVER_BRIGHTNESS = {"alarm": 0.3}   # dimmer behind the reminder text
RIVER_NIGHT_BRIGHTNESS = 0.5
RIVER_FADE_IN_RATE = 1.5

WEATHER_REFRESH_SECONDS = 600
FPS = 60
FRAME_BUDGET = 1 / 55              # average frame time that counts as "can't keep up"
RENDER_SCALES = [1.0, 0.85, 0.75]  # orb resolution steps if the GPU ever falls behind

WEATHER_ICONS = {
    "clear": "☀", "sunny": "☀",
    "cloud": "☁", "overcast": "☁",
    "rain": "\U0001F327", "drizzle": "\U0001F326",
    "storm": "⛈", "thunder": "⛈",
    "snow": "❄",
    "fog": "\U0001F32B", "mist": "\U0001F32B", "haze": "\U0001F32B",
    "wind": "\U0001F4A8",
}
DEFAULT_WEATHER_ICON = "\U0001F321"


class Display:
    """
    Owns all visual state and the render loop. Call run() to start the
    window (blocks until quit). Other code (main.py) interacts via:
      set_state(state), show_reminder(reminder), dismiss_reminder(),
      claim_wake(), try_start_alarm(reminder)
    Those are safe to call from any thread.

    Optional hooks main.py can set:
      active_speech_process  the playing speech; a tap stops it, and its
                             level_meter (from tts.py) drives the voice rings
      input_level_fn         returns mic loudness 0..1, so the orb reacts
                             to you while it listens
    """

    def __init__(self, headless=False):
        pygame.init()
        pygame.font.init()
        self.clock = pygame.time.Clock()

        if headless:  # offscreen, for tests and previews
            ctx = moderngl.create_standalone_context(backend="egl") if sys.platform.startswith("linux") else moderngl.create_standalone_context()
            self.target = ctx.simple_framebuffer((SCREEN_W, SCREEN_H))
            self.vsync = False
        else:
            flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.NOFRAME
            try:
                pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, vsync=1)  # frames locked to the screen refresh
                self.vsync = True
            except (TypeError, pygame.error):
                pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
                self.vsync = False
            ctx = moderngl.create_context()
            self.target = ctx.screen
            print(f"display: {ctx.info['GL_RENDERER']}, OpenGL {ctx.info['GL_VERSION']}, vsync {'on' if self.vsync else 'off'}")
        self.ctx = ctx
        self.renderer = Renderer(ctx, SCREEN_W, SCREEN_H)

        self.font_primary = pygame.font.Font(FONT_PATH, 38)
        self.font_secondary = pygame.font.Font(FONT_PATH, 18)
        self.font_reminder_time = pygame.font.Font(FONT_PATH, 42)
        self.font_reminder_message = pygame.font.Font(FONT_PATH, 22)
        self.font_emoji = pygame.font.Font(EMOJI_FONT_PATH, 32)  # Rubik has no emoji glyphs, needs a real color emoji font

        self.motion = OrbMotion()
        self.river = StardustRiver(SCREEN_W, SCREEN_H)
        self.rings = VoiceRings()

        # state machine. The voice and reminder threads change state while
        # this thread draws, so changes and reads of it go through this lock
        self.state_lock = threading.RLock()
        self.current_state = "sleep"
        self._drawn_state = "sleep"

        # touch pulse
        self.touch_pulse_start_time = -1e9
        self.last_touch_pulse_time = -1e9

        # orb horizontal position (for reminder slide)
        self.orb_target_x_ratio = CENTER_X_RATIO
        self.orb_current_x_ratio = CENTER_X_RATIO

        # info panel
        self.info_panel_visible = False
        self.info_panel_show_time = 0
        self.info_fade_progress = 0.0
        self.cached_weather_str = "Loading weather..."

        # reminder panel
        self.reminder_panel_visible = False
        self.reminder_data = None
        self.reminder_fade_progress = 0.0

        # animation levels
        self.voice_level = 0.0
        self.orb_visible = 1.0
        self.river_brightness = 0.0   # fades in at startup
        self.last_breath_phase = 0.0

        # frame time watchdog
        self.frame_times = deque(maxlen=180)
        self.frames_drawn = 0
        self.slow_windows = 0

        self.running = True

        # holds the live subprocess.Popen handle for whatever speech is
        # currently playing, so a tap can interrupt it (see _on_tap).
        # main.py is responsible for setting/clearing this around its
        # own speak calls.
        self.active_speech_process = None
        self.input_level_fn = None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def set_state(self, state):
        """Switch the orb to a new emotional state, crossfading from the current one."""
        if state not in STATES:
            print(f"Warning: unknown state '{state}', ignoring")
            return
        with self.state_lock:
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
        last = time.perf_counter()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_tap(event.pos[0], event.pos[1])

            t = time.perf_counter()
            dt = min(t - last, 0.1)  # a long stall shouldn't make the animation jump
            last = t
            self._render_frame(time.time(), dt)
            pygame.display.flip()
            if not self.vsync:
                self.clock.tick(FPS)
            self._watch_frame_time(dt)

        self.renderer.text.clear()
        pygame.quit()

    def _watch_frame_time(self, dt):
        """If frames run slow for ~9 seconds straight, draws the orb at a lower
        resolution. Upscaled, the soft orb looks nearly the same, and smooth
        motion matters more than the last bit of sharpness."""
        self.frames_drawn += 1
        if self.frames_drawn < 120:  # skip startup, when shaders are still warming up
            return
        self.frame_times.append(dt)
        if len(self.frame_times) < self.frame_times.maxlen:
            return
        slow = sum(self.frame_times) / len(self.frame_times) > FRAME_BUDGET
        self.slow_windows = self.slow_windows + 1 if slow else 0
        self.frame_times.clear()
        if self.slow_windows >= 3:
            self.slow_windows = 0
            index = RENDER_SCALES.index(self.renderer.scale)
            if index + 1 < len(RENDER_SCALES):
                self.renderer.set_scale(RENDER_SCALES[index + 1])
                print(f"display: frames running slow, orb resolution lowered to {RENDER_SCALES[index + 1]:.0%}")

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
                self.touch_pulse_start_time = now
                self.last_touch_pulse_time = now

        # tapping anywhere also reveals the info panel
        self.info_panel_visible = True
        self.info_panel_show_time = time.time()

    def _is_tap_on_orb(self, x, y):
        orb_center_x = SCREEN_W * self.orb_current_x_ratio
        orb_center_y = SCREEN_H / 2
        tap_radius = ORB_RADIUS * 1.3  # generous margin, easier to hit on a touchscreen
        return math.hypot(x - orb_center_x, y - orb_center_y) <= tap_radius

    # ------------------------------------------------------------------
    # ANIMATION HELPERS
    # ------------------------------------------------------------------

    def _get_touch_pulse_boost(self, now):
        progress = (now - self.touch_pulse_start_time) / TOUCH_PULSE_DURATION
        if not 0.0 <= progress < 1.0:
            return 0.0
        return math.sin(progress * math.pi) * TOUCH_PULSE_MAX_BOOST

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
                self.cached_weather_str = f"{data['temp']}°F  {data['description'].title()}"
            time.sleep(WEATHER_REFRESH_SECONDS)

    def get_sleep_brightness_multiplier_is_night(self):
        """True between 9pm and 8am, used to make the sleep orb invisible at night."""
        hour = datetime.now().hour
        return hour >= 21 or hour < 8

    def _voice_level(self, now, dt, state):
        """Loudness that drives the orb: Solu's own voice while speaking, yours while listening."""
        target = 0.0
        if state == "speak":
            meter = getattr(self.active_speech_process, "level_meter", None)
            if meter is not None:
                target = meter.level_at(now)
        elif state == "idle" and self.input_level_fn is not None:
            try:
                target = LISTEN_REACTION * float(self.input_level_fn())
            except Exception:
                target = 0.0
        rate = VOICE_ATTACK_RATE if target > self.voice_level else VOICE_RELEASE_RATE
        self.voice_level = approach(self.voice_level, min(max(target, 0.0), 1.0), rate, dt)
        return self.voice_level

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    def _render_frame(self, now, dt):
        with self.state_lock:
            state = self.current_state
        if state != self._drawn_state:
            fast = "sleep" in (state, self._drawn_state)
            self.motion.set_state(state, now, SLEEP_TRANSITION_SECONDS if fast else TRANSITION_SECONDS)
            self._drawn_state = state

        level = self._voice_level(now, dt, state)
        self.motion.update(now, dt, level)

        breath_phase = (now / BREATH_SECONDS) % 1.0
        breath = math.sin(breath_phase * TAU)
        breath_peak = self.last_breath_phase < 0.25 <= breath_phase  # top of each breath
        self.last_breath_phase = breath_phase

        night_sleep = state == "sleep" and self.get_sleep_brightness_multiplier_is_night()
        self.orb_visible = approach(self.orb_visible, 0.0 if night_sleep else 1.0, 3.0 if night_sleep else 25.0, dt)

        self.rings.update(now, dt, level, speaking=(state == "speak"), breath_peak=(state == "idle" and breath_peak))

        river_target = RIVER_NIGHT_BRIGHTNESS if night_sleep else RIVER_BRIGHTNESS.get(state, 1.0)
        self.river_brightness = approach(self.river_brightness, river_target, RIVER_FADE_IN_RATE, dt)
        self.river.update(dt, self.motion.speed, level if state == "speak" else 0.0)

        self.orb_current_x_ratio = approach(self.orb_current_x_ratio, self.orb_target_x_ratio, ORB_SLIDE_RATE, dt)
        center = (SCREEN_W * self.orb_current_x_ratio, SCREEN_H / 2)
        radius = ORB_RADIUS * (1 + BREATHING_SCALE_AMOUNT * breath + self._get_touch_pulse_boost(now) + 0.03 * level)

        uniforms = self.motion.uniforms()
        uniforms.update(self.rings.uniforms(now))
        uniforms["u_breath"] = breath
        uniforms["u_visible"] = self.orb_visible

        self.renderer.draw_orb(self.target, center, radius, uniforms)
        points = self.river.vertex_data(self.motion.colors, self.river_brightness, SCREEN_H / 2, now)
        self.renderer.draw_points(points, center, radius, self.orb_visible)
        self._update_and_draw_info_panel(now, dt)
        self._update_and_draw_reminder_panel(now, dt)

    def _text(self, font, text, color, key_prefix="t"):
        return self.renderer.text.get((key_prefix, id(font), text, color), lambda: font.render(text, True, color))

    def _update_and_draw_info_panel(self, now, dt):
        if self.info_panel_visible and (now - self.info_panel_show_time > INFO_PANEL_DURATION):
            self.info_panel_visible = False

        target = 1.0 if self.info_panel_visible else 0.0
        self.info_fade_progress = approach(self.info_fade_progress, target, INFO_FADE_RATE, dt)
        if abs(self.info_fade_progress - target) < 0.01:
            self.info_fade_progress = target
        alpha = self.info_fade_progress
        if alpha <= 0.01:
            return

        now_dt = datetime.now()
        r = self.renderer
        r.draw_text(self._text(self.font_primary, now_dt.strftime("%-I:%M %p"), COLOR_PRIMARY_TEXT), 20, 14, alpha)
        r.draw_text(self._text(self.font_secondary, now_dt.strftime("%B %d"), COLOR_SECONDARY_TEXT), 20, 64, alpha)

        weather_str = self.cached_weather_str
        icon = DEFAULT_WEATHER_ICON
        lower_desc = weather_str.lower()
        for keyword, emoji in WEATHER_ICONS.items():
            if keyword in lower_desc:
                icon = emoji
                break

        temp_number = weather_str.split("°")[0] if "°" in weather_str else "--"
        weather_desc = weather_str.split("  ", 1)[1] if "  " in weather_str else ""

        temp = self._text(self.font_primary, f"{temp_number}°", COLOR_PRIMARY_TEXT)
        icon_entry = self._icon(icon, temp[2])
        pair_width = icon_entry[1] + 8 + temp[1]
        icon_x = SCREEN_W - 20 - pair_width
        r.draw_text(icon_entry, icon_x, 14, alpha)
        r.draw_text(temp, icon_x + icon_entry[1] + 8, 14, alpha)

        if weather_desc:
            desc = self._text(self.font_secondary, weather_desc, COLOR_SECONDARY_TEXT)
            r.draw_text(desc, SCREEN_W - 20 - desc[1], 64, alpha)

    def _icon(self, icon, height):
        """NotoColorEmoji ignores both requested size and color, so the rendered emoji is scaled manually."""
        def make():
            raw = self.font_emoji.render(icon, True, COLOR_PRIMARY_TEXT)
            scale = height / raw.get_height()
            return pygame.transform.smoothscale(raw, (max(1, int(raw.get_width() * scale)), height))
        return self.renderer.text.get(("icon", icon, height), make)

    def _update_and_draw_reminder_panel(self, now, dt):
        """
        Handles the fade animation and the sequenced dismiss: text fades
        out first, and only once that fade fully completes does the orb
        slide back to center (doing both at once looked rushed/broken).
        """
        target = 1.0 if self.reminder_panel_visible else 0.0
        self.reminder_fade_progress = approach(self.reminder_fade_progress, target, REMINDER_FADE_RATE, dt)
        if abs(self.reminder_fade_progress - target) < 0.01:
            self.reminder_fade_progress = target

        with self.state_lock:
            if not self.reminder_panel_visible and self.reminder_fade_progress == 0.0:
                if self.reminder_data is not None:
                    self.orb_target_x_ratio = CENTER_X_RATIO
                self.reminder_data = None

        reminder = self.reminder_data
        alpha = self.reminder_fade_progress
        if reminder is None or alpha <= 0.01:
            return

        raw_time = reminder.get("time", "")
        try:
            display_time = datetime.strptime(raw_time, "%H:%M").strftime("%-I:%M %p")
        except ValueError:
            display_time = raw_time
        self.renderer.draw_text(self._text(self.font_reminder_time, display_time, COLOR_PRIMARY_TEXT), int(SCREEN_W * 0.62), 180, alpha)

        message = reminder.get("message", "")
        width = int(SCREEN_W * 0.33)
        entry = self.renderer.text.get(("wrapped", message, width), lambda: self._render_wrapped_text(
            message, self.font_reminder_message, COLOR_SECONDARY_TEXT, width))
        self.renderer.draw_text(entry, int(SCREEN_W * 0.62), 260, alpha)

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

        line_surfaces = [font.render(line, True, color) for line in lines] or [font.render(" ", True, color)]
        total_height = sum(s.get_height() for s in line_surfaces) + (len(line_surfaces) - 1) * 4
        combined = pygame.Surface((max_width, max(total_height, 1)), pygame.SRCALPHA)

        y = 0
        for surf in line_surfaces:
            combined.blit(surf, (0, y))
            y += surf.get_height() + 4

        return combined

# ============================================================================
# DEMO: cycles through the states with a fake voice, no rest of Solu needed
# ============================================================================


class FakeSpeech:
    """Stands in for a speech process: never finishes, and has a level_meter
    that sounds like talking (syllables with pauses between phrases)."""

    def __init__(self):
        self.level_meter = self
        self.level, self.target, self.next_change, self.last = 0.0, 0.0, 0.0, time.time()

    def poll(self):
        return None

    def terminate(self):
        pass

    def level_at(self, now):
        dt, self.last = now - self.last, now
        if now >= self.next_change:
            if random.random() < 0.12:
                self.target, hold = 0.0, random.uniform(0.25, 0.5)
            else:
                self.target, hold = random.uniform(0.35, 1.0), random.uniform(0.08, 0.2)
            self.next_change = now + hold
        rate = 18.0 if self.target > self.level else 7.0
        self.level += (self.target - self.level) * (1.0 - math.exp(-rate * max(dt, 0.0)))
        return self.level


DEMO_ORDER = ["sleep", "idle", "think", "speak", "error", "alarm"]
DEMO_SECONDS = 4.0


def _demo_state(display, start, now):
    state = DEMO_ORDER[int((now - start) / DEMO_SECONDS) % len(DEMO_ORDER)]
    if state != display.current_state:
        if state == "alarm":
            display.show_reminder({"time": "14:30", "message": "Call mom about thanksgiving plans"})
        elif display.reminder_panel_visible:
            display.reminder_panel_visible = False
        display.set_state(state)
        display.active_speech_process = FakeSpeech() if state == "speak" else None


def run_demo():
    display = Display()
    display.cached_weather_str = "54°F  Clear Sky"
    display._weather_loop = lambda: None
    display.get_sleep_brightness_multiplier_is_night = lambda: False
    start = time.time()
    original_render = display._render_frame
    report = {"t": time.perf_counter(), "frames": 0, "worst": 0.0}

    def render(now, dt):
        _demo_state(display, start, now)
        original_render(now, dt)
        report["frames"] += 1
        report["worst"] = max(report["worst"], dt)
        if time.perf_counter() - report["t"] >= 5:
            elapsed = time.perf_counter() - report["t"]
            print(f"demo: {report['frames'] / elapsed:.1f} fps, worst frame {report['worst'] * 1000:.1f}ms, orb resolution {display.renderer.scale:.0%}")
            report.update(t=time.perf_counter(), frames=0, worst=0.0)

    display._render_frame = render
    print("demo: cycling states every 4s. Taps work like normal, Esc quits")
    display.run()


def run_preview(out_dir, frames, fps=30):
    """Renders frames to PNG files offscreen (for checking the look without a screen)."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    display = Display(headless=True)
    display.cached_weather_str = "54°F  Clear Sky"
    display.get_sleep_brightness_multiplier_is_night = lambda: False
    random.seed(4)
    start = 1_000_000.0
    for i in range(frames):
        now = start + i / fps
        _demo_state(display, start, now)
        display._render_frame(now, 1 / fps)
        data = display.target.read(components=3)
        Image.frombytes("RGB", (SCREEN_W, SCREEN_H), data).transpose(Image.FLIP_TOP_BOTTOM).save(f"{out_dir}/frame_{i:04d}.png")
    print(f"wrote {frames} frames to {out_dir}")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        run_preview(sys.argv[i + 1], int(sys.argv[i + 2]) if len(sys.argv) > i + 2 else 720)
    elif "--demo" in sys.argv:
        run_demo()
    else:
        display = Display()
        display.run()
