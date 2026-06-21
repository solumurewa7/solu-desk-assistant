"""
display.py — Solu's full visual layer, Pygame version.

This is the real, final display module (not a throwaway test like
fps_test.py was). It ports every feature that existed in the original
tkinter+Pillow display.py, rebuilt on the validated Pygame foundation
(orb.py + starfield.py) from this rewrite:

  - 7 emotional states (sleep/idle/speak/joking/think/error/alarm), each
    with its own orb color, smooth crossfade between any two states
  - Starfield background, tinted to match the orb's current color,
    hidden during alarm
  - Breathing animation (sine-wave scale pulse)
  - Touch-reactive pulse when tapping directly on the orb, with a
    cooldown to prevent spam-tap stacking
  - Tap-to-reveal info panel (time, date, temperature, weather
    description), auto-hides after a few seconds, gray-scale visual
    hierarchy (brighter for primary text, dimmer for secondary)
  - Full reminder panel: orb slides left, reminder time + message fade
    in on the right, tap-to-dismiss (or programmatic dismiss for a
    future voice command) triggers a SEQUENCED fade-out-then-slide-back,
    not simultaneous, matching what was confirmed to look right in the
    original version

Key porting decisions from tkinter to Pygame:
  - tkinter's canvas.create_text/itemconfig persistent-item pattern is
    replaced by just re-rendering text surfaces each frame Pygame has no
    persistent canvas items the way tkinter does, but since we already
    proved the orb pipeline easily holds 60fps, re-rendering small text
    surfaces every frame is trivial by comparison — no need for the
    same "create once, update in place" trick that mattered for tkinter.
  - The "text fades to background color, which leaves a ghost over a
    non-uniform background" bug that was found and fixed in tkinter
    (text needs explicit hiding, not just color matching, once fully
    faded) does NOT apply here, since Pygame draws fresh each frame from
    scratch — there's no persistent canvas item to leave a ghost. We
    still gate on a visibility/alpha check before rendering text at all
    rather than rendering invisible text for no reason, but it's a
    performance choice now, not a correctness fix.
  - Rubik font loaded directly from a bundled .ttf via pygame.font.Font
    (no system font installation needed, unlike tkinter). Visual weight
    hierarchy (originally "Rubik Medium" vs "Rubik Light") is now
    achieved with one font file plus Pygame's synthetic bold flag,
    since the static weight variants no longer exist at their old
    download path upstream — confirmed via two separate failed
    downloads before falling back to this approach.
"""

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
ORB_SIZE = 340  # confirmed final size against the real screen

FONT_PATH = "assets/fonts/Rubik.ttf"
EMOJI_FONT_PATH = "assets/fonts/NotoColorEmoji.ttf"

ORB_COLORS = {
    "sleep":  ((255, 255, 255), (180, 180, 180)),
    "idle":   ((77, 184, 255),  (10, 61, 102)),
    "speak":  ((179, 136, 255), (61, 26, 102)),
    "joking": ((105, 240, 174), (26, 102, 67)),
    "think":  ((255, 183, 77),  (102, 61, 10)),
    "error":  ((255, 82, 82),   (102, 10, 10)),
    "alarm":  ((255, 255, 255), (102, 102, 102)),
}

# gray-scale text hierarchy, carried over directly from the tkinter version
COLOR_PRIMARY_TEXT = (192, 192, 192)    # #c0c0c0 — time, temp number
COLOR_SECONDARY_TEXT = (112, 112, 112)  # #707070 — date, weather description
COLOR_BG = (0, 0, 0)
STAR_COLOR = (255, 255, 255)  # fixed neutral white — stars no longer follow
                               # the orb's state color, only the orb and the
                               # orbiting particles do that now

INFO_PANEL_DURATION = 5       # seconds the info panel stays visible after a tap
INFO_FADE_SPEED = 0.15        # easing factor, same value confirmed to feel right in tkinter

REMINDER_FADE_SPEED = 0.3     # faster than the info panel, confirmed snappier dismiss feel
ORB_POSITION_EASE_SPEED = 0.08  # slower, more deliberate slide for the reminder panel

REMINDER_LEFT_X_RATIO = 0.28   # how far left the orb slides when showing a reminder
CENTER_X_RATIO = 0.5

BREATHING_CYCLE_SECONDS = 4
BREATHING_SCALE_AMOUNT = 0.02  # orb scales between 0.98x and 1.02x

TOUCH_PULSE_DURATION = 0.4
TOUCH_PULSE_COOLDOWN = 0.5
TOUCH_PULSE_MAX_BOOST = 0.06


def interpolate_color(color_a, color_b, progress):
    """Blends from color_a to color_b based on progress (0.0 to 1.0). Same helper as tkinter version."""
    r = int(color_a[0] + (color_b[0] - color_a[0]) * progress)
    g = int(color_a[1] + (color_b[1] - color_a[1]) * progress)
    b = int(color_a[2] + (color_b[2] - color_a[2]) * progress)
    return (r, g, b)


class Display:
    """
    Owns all visual state and the render loop. Call run() to start the
    Pygame window and enter the main loop (blocks until quit). External
    code (eventually brain.py / main.py) interacts via the public methods:
      set_state(state), show_reminder(reminder), dismiss_reminder()
    """

    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
        self.clock = pygame.time.Clock()

        self.font_primary = pygame.font.Font(FONT_PATH, 38)  # regular weight — this was the preferred one from the comparison
        self.font_secondary = pygame.font.Font(FONT_PATH, 18)
        self.font_secondary.set_bold(False)
        self.font_reminder_time = pygame.font.Font(FONT_PATH, 42)
        self.font_reminder_message = pygame.font.Font(FONT_PATH, 22)

        # dedicated emoji font for weather icons — Rubik has no emoji glyphs
        # at all (confirmed by direct glyph-table inspection, every weather
        # icon character came back MISSING), so icons need a real color
        # emoji font rather than the text font
        self.font_emoji = pygame.font.Font(EMOJI_FONT_PATH, 32)

        self.starfield = Starfield(SCREEN_W, SCREEN_H)
        self.orb = Orb(ORB_SIZE, ORB_COLORS)
        self.orbit_system = OrbitSystem()

        # ---- state machine ----
        self.current_state = "sleep"
        self.transition_from_state = None
        self.transition_start_time = 0
        self.transition_duration = 0.6

        # ---- breathing ----
        # (pure function of time.time(), no instance state needed)

        # ---- touch pulse ----
        self.touch_pulse_active = False
        self.touch_pulse_start_time = 0
        self.last_touch_pulse_time = 0

        # ---- orb horizontal position (for reminder slide) ----
        self.orb_target_x_ratio = CENTER_X_RATIO
        self.orb_current_x_ratio = CENTER_X_RATIO

        # ---- info panel ----
        self.info_panel_visible = False
        self.info_panel_show_time = 0
        self.info_fade_progress = 0.0

        # cached weather, refreshed at most every 10 minutes
        self.cached_weather_str = "Loading weather..."
        self.last_weather_fetch = 0

        # ---- reminder panel ----
        self.reminder_panel_visible = False
        self.reminder_data = None
        self.reminder_fade_progress = 0.0

        self.running = True

    # ------------------------------------------------------------------
    # PUBLIC API — these are what brain.py / main.py will call
    # ------------------------------------------------------------------

    def set_state(self, state):
        if state not in ORB_COLORS:
            print(f"Warning: unknown state '{state}', ignoring")
            return
        if state == self.current_state:
            return
        self.transition_from_state = self.current_state
        self.transition_start_time = time.time()
        self.current_state = state

    def show_reminder(self, reminder):
        """
        reminder: a dict matching reminders.py's actual schema —
        expects at least 'time' (e.g. "14:30") and 'message' keys.
        """
        self.reminder_data = reminder
        self.reminder_panel_visible = True
        self.orb_target_x_ratio = REMINDER_LEFT_X_RATIO

    def dismiss_reminder(self):
        """
        Starts the dismiss sequence: text fades out first, and ONLY once
        that fade fully completes does the orb slide back to center.
        This sequencing (rather than doing both simultaneously) was
        specifically confirmed to look right in the tkinter version,
        after an earlier version that moved both at once looked broken.
        The actual sequencing logic lives in _update_reminder_panel(),
        which watches for the fade to hit exactly 0.0 and only then
        triggers the slide-back — see that method for the full
        explanation.
        """
        self.reminder_panel_visible = False
        self.set_state("idle")

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
        if self.reminder_panel_visible:
            # any tap while a reminder is showing dismisses it, same as tkinter version
            self.dismiss_reminder()
            return

        if self._is_tap_on_orb(x, y):
            now = time.time()
            if now - self.last_touch_pulse_time > TOUCH_PULSE_COOLDOWN:
                self.touch_pulse_active = True
                self.touch_pulse_start_time = now
                self.last_touch_pulse_time = now

        # tapping anywhere (orb or not) also reveals the info panel,
        # same behavior as the tkinter version
        self.info_panel_visible = True
        self.info_panel_show_time = time.time()

    def _is_tap_on_orb(self, x, y):
        orb_center_x = SCREEN_W * self.orb_current_x_ratio
        orb_center_y = SCREEN_H // 2
        # generous margin (30%) makes it easier to actually hit on a touchscreen,
        # same reasoning as the tkinter version
        tap_radius = (ORB_SIZE / 2) * 1.3
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
        boost_curve = math.sin(progress * math.pi)  # rises then falls smoothly
        return boost_curve * TOUCH_PULSE_MAX_BOOST

    def _get_cached_weather(self):
        now = time.time()
        if now - self.last_weather_fetch > 600:
            try:
                from weather import get_weather
                data = get_weather()
                if data:
                    self.cached_weather_str = f"{data['temp']}\u00b0F  {data['description'].title()}"
            except Exception:
                pass  # keep showing the last known value if the fetch fails
            self.last_weather_fetch = now
        return self.cached_weather_str

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    def get_sleep_brightness_multiplier_is_night(self):
        hour = datetime.now().hour
        return hour >= 23 or hour < 7

    def _render_frame(self, now, dt):
        self.screen.fill(COLOR_BG)

        core_rgb = self._get_current_core_rgb_for_drawing(now)

        # starfield, drawn before the orb so the orb naturally occludes
        # whatever stars sit behind it. Fixed white now (was core_rgb) —
        # per request, only the orb and the orbiting particles should
        # carry/crossfade the state color, so stars read as clearly
        # distinct background elements rather than tinting along with
        # everything else.
        self.starfield.update(dt, now)
        if self.current_state != "alarm":
            self.starfield.draw(self.screen, STAR_COLOR, now, alpha_multiplier=1.0)

        self.orb.refresh_sleep_frame(self.get_sleep_brightness_multiplier_is_night())
        self._draw_orb(now, dt, core_rgb)
        self._update_and_draw_info_panel(now)
        self._update_and_draw_reminder_panel(now)

    def _get_current_core_rgb_for_drawing(self, now):
        target_core, _ = ORB_COLORS[self.current_state]

        if self.transition_from_state is not None:
            elapsed = now - self.transition_start_time
            progress = min(elapsed / self.transition_duration, 1.0)
            from_core, _ = ORB_COLORS[self.transition_from_state]
            result = interpolate_color(from_core, target_core, progress)
        else:
            result = target_core

        return result

    def _draw_orb(self, now, dt, core_rgb):
        state = self.current_state

        if self.transition_from_state is not None:
            elapsed = now - self.transition_start_time
            progress = min(elapsed / self.transition_duration, 1.0)

            if progress >= 1.0:
                self.transition_from_state = None
                base_orb = self.orb.get_current_frame(state, core_rgb)
            else:
                old_frame = self.orb.get_current_frame(self.transition_from_state, core_rgb)
                new_frame = self.orb.get_current_frame(state, core_rgb)
                base_orb = old_frame.copy()
                # pygame surfaces don't have a direct "blend two surfaces"
                # the way Pillow's Image.blend did — fastest faithful
                # equivalent is drawing the new frame on top of the old
                # one at partial alpha, using BLEND_ALPHA_SDL2 for a true
                # crossfade rather than the new frame just occluding the old
                temp = new_frame.copy()
                temp.set_alpha(int(255 * progress))
                base_orb.set_alpha(255)
                base_orb.blit(temp, (0, 0))
        else:
            base_orb = self.orb.get_current_frame(state, core_rgb)

        scale = self._get_breathing_scale() + self._get_touch_pulse_boost()

        # ease the orb's horizontal position toward its target
        self.orb_current_x_ratio += (self.orb_target_x_ratio - self.orb_current_x_ratio) * ORB_POSITION_EASE_SPEED

        new_size = int(base_orb.get_width() * scale)
        scaled_orb = pygame.transform.smoothscale(base_orb, (new_size, new_size))

        orb_center_x = int(SCREEN_W * self.orb_current_x_ratio)
        orb_center_y = SCREEN_H // 2
        paste_x = orb_center_x - (new_size // 2)
        paste_y = orb_center_y - (new_size // 2)

        # orbiting particles: drawn in three passes around the orb blit so
        # draw order itself produces correct occlusion — particles "behind"
        # the orb this frame are drawn first (and get covered by the orb),
        # particles "in front" are drawn last (and sit visibly on top)
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
            return  # nothing visible, skip rendering text entirely

        primary_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, self.info_fade_progress)
        secondary_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, self.info_fade_progress)

        # time — top-left, primary weight
        time_str = datetime.now().strftime("%-I:%M %p")
        time_surf = self.font_primary.render(time_str, True, primary_color)
        self.screen.blit(time_surf, (20, 14))

        # date — subheading below time, secondary weight
        date_str = datetime.now().strftime("%B %d")
        date_surf = self.font_secondary.render(date_str, True, secondary_color)
        self.screen.blit(date_surf, (20, 64))

        # temperature + weather icon — top-right, primary weight.
        # Icon rendered SEPARATELY with the emoji font and blitted next to
        # the temp number — Rubik has no emoji glyphs at all (confirmed via
        # direct glyph-table inspection), so trying to render the icon
        # character through font_primary just produced nothing visible.
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

        # NotoColorEmoji ignores the requested point size entirely and
        # always returns a fixed 136x128px bitmap glyph (confirmed by
        # direct testing — requesting 16px through 48px all produced the
        # identical 136x128 surface). That's why the icon rendered nearly
        # 4x bigger than the temp text next to it. Scaling it down
        # manually to match the temp text's height fixes this regardless
        # of whatever native size the font happens to return.
        # NotoColorEmoji ignores the requested point size (confirmed
        # earlier) AND ignores the requested render color entirely (just
        # confirmed too: rendering the same glyph with color=(255,255,255)
        # vs color=(20,20,20) produced byte-identical pixels). That's
        # exactly why this icon wasn't fading along with everything
        # else — primary_color was being passed in but silently discarded
        # by the font itself, so the icon always rendered at full native
        # brightness no matter what info_fade_progress said. The fix is
        # applying alpha directly to the rendered SURFACE (which Pygame
        # does respect, verified directly), rather than relying on the
        # render() color argument this font doesn't honor.
        icon_raw = self.font_emoji.render(icon, True, primary_color)
        icon_target_height = temp_surf.get_height()
        icon_scale = icon_target_height / icon_raw.get_height()
        icon_surf = pygame.transform.smoothscale(
            icon_raw,
            (max(1, int(icon_raw.get_width() * icon_scale)), icon_target_height),
        )
        icon_surf.set_alpha(int(255 * self.info_fade_progress))

        # lay out icon to the left of the temp number, right-aligned as a pair
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
        Handles BOTH the fade animation and the sequenced dismiss logic.

        The sequencing rule (ported directly from the confirmed-working
        tkinter version): when reminder_panel_visible goes False, the
        text fade-out starts immediately, but the orb does NOT start
        sliding back to center until that fade has fully reached 0.0.
        An earlier version moved both simultaneously and it looked
        wrong/rushed — text and orb overlapping mid-transition read as
        broken rather than intentional. We watch for the exact frame the
        fade completes and only then re-target the orb's position.
        """
        target_progress = 1.0 if self.reminder_panel_visible else 0.0
        self.reminder_fade_progress += (target_progress - self.reminder_fade_progress) * REMINDER_FADE_SPEED
        if abs(self.reminder_fade_progress - target_progress) < 0.01:
            self.reminder_fade_progress = target_progress

        # the exact moment the fade-out finishes, trigger the slide-back —
        # this only fires once, since reminder_data gets cleared right after
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
        """
        Pygame has no built-in text-wrapping the way tkinter's
        width= parameter on create_text did, so this does it manually:
        breaks the message into lines that each fit within max_width,
        then renders all lines onto one combined surface.
        """
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