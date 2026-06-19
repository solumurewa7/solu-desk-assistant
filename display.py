import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import threading
import time
import math
from datetime import datetime

SCREEN_W = 800
SCREEN_H = 480
ORB_SIZE = 350

ORB_COLORS = {
    "sleep":  ("#0a0a0a", "#000000"),
    "idle":   ("#4db8ff", "#0a3d66"),
    "speak":  ("#b388ff", "#3d1a66"),
    "joking": ("#69f0ae", "#1a6643"),
    "think":  ("#ffb74d", "#663d0a"),
    "error":  ("#ff5252", "#660a0a"),
    "alarm":  ("#ffffff", "#666666"),
}

current_state = "idle"
canvas = None
root = None
breathing_running = False
breathing_thread = None
transition_from_state = None
transition_start_time = 0
TRANSITION_DURATION = 0.6  # half a second crossfade, adjustable
cached_weather = "Loading weather..."
last_weather_fetch = 0
info_panel_visible = False
info_panel_show_time = 0
INFO_PANEL_DURATION = 5  # seconds before auto-hiding again
COLOR_PRIMARY_TEXT = "#c0c0c0"    # lighter gray — time, temp number
COLOR_SECONDARY_TEXT = "#707070"  # darker gray — date, weather description
COLOR_BG = "#000000"              # the screen background, used as the fade starting point
info_fade_progress = 0.0  # 0.0 = fully hidden (background color), 1.0 = fully visible
orb_target_x_ratio = 0.5  # 0.5 = horizontal center, lower = further left
orb_current_x_ratio = 0.5  # the actual current position, eases toward the target
reminder_panel_visible = False
reminder_data = None
reminder_fade_progress = 0.0

#-------------------------------------------------------------------------------------------------------------------------------------------

def generate_orb(core_color, edge_color):
    img = Image.new("RGBA", (ORB_SIZE, ORB_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    core_rgb = tuple(int(core_color[i:i+2], 16) for i in (1, 3, 5))
    edge_rgb = tuple(int(edge_color[i:i+2], 16) for i in (1, 3, 5))
    
    center = ORB_SIZE // 2
    max_radius = center
    
    steps = 100
    for i in range(steps, 0, -1):
        radius = int(max_radius * (i / steps))
        blend = 1 - (i / steps)
        r = int(edge_rgb[0] + (core_rgb[0] - edge_rgb[0]) * blend)
        g = int(edge_rgb[1] + (core_rgb[1] - edge_rgb[1]) * blend)
        b = int(edge_rgb[2] + (core_rgb[2] - edge_rgb[2]) * blend)
        
        # fade alpha out only in the outermost 3% of steps now — thin edge, not a wide soft band
        if i > steps * 0.95:
            edge_fade = (steps - i) / (steps * 0.05)
            a = int(255 * edge_fade)
        else:
            a = 255
        
        draw.ellipse(
            [center - radius, center - radius, center + radius, center + radius],
            fill=(r, g, b, a)
        )
    
    return img

#-------------------------------------------------------------------------------------------------------------------------------------------

def add_glow(orb_img, core_color):
    glow_size = int(ORB_SIZE * 1.7)
    
    result = Image.new("RGBA", (glow_size, glow_size), (0, 0, 0, 0))
    
    glow_layer = orb_img.resize((int(ORB_SIZE * 1.3), int(ORB_SIZE * 1.3)))
    glow_layer = glow_layer.copy()
    alpha = glow_layer.split()[3]
    alpha = alpha.point(lambda p: int(p * 0.35))
    glow_layer.putalpha(alpha)
    
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=30))
    
    glow_pos = ((glow_size - glow_layer.width) // 2, (glow_size - glow_layer.height) // 2)
    result.paste(glow_layer, glow_pos, glow_layer)
    
    orb_pos = ((glow_size - ORB_SIZE) // 2, (glow_size - ORB_SIZE) // 2)
    result.paste(orb_img, orb_pos, orb_img)
    
    return result

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_breathing_scale():
    cycle_seconds = 4  # one full breath in-and-out takes 4 seconds
    t = time.time() % cycle_seconds
    wave = math.sin((t / cycle_seconds) * 2 * math.pi)  # -1 to 1

    scale = 1.0 + (wave * 0.02)
    return scale

#-------------------------------------------------------------------------------------------------------------------------------------------

def render_loop():
    global current_state, transition_from_state, transition_start_time
    
    cached_orb_images = {}  # cached gradient+glow image per state, generated once each
    
    while True:
        state = current_state
        
        # make sure we have a cached orb image for this state
        if state not in cached_orb_images:
            core_color, edge_color = ORB_COLORS[state]
            orb = generate_orb(core_color, edge_color)
            glowing_orb = add_glow(orb, core_color)
            cached_orb_images[state] = glowing_orb
        
        # check if we're in the middle of a transition between two states
        if transition_from_state is not None:
            elapsed = time.time() - transition_start_time
            progress = min(elapsed / TRANSITION_DURATION, 1.0)  # 0.0 to 1.0
            
            if progress >= 1.0:
                # transition finished, clean up and use the new state normally
                transition_from_state = None
                base_orb = cached_orb_images[state]
            else:
                # still mid-transition — make sure the OLD state's orb is also cached
                if transition_from_state not in cached_orb_images:
                    old_core, old_edge = ORB_COLORS[transition_from_state]
                    old_orb = generate_orb(old_core, old_edge)
                    old_glowing = add_glow(old_orb, old_core)
                    cached_orb_images[transition_from_state] = old_glowing
                
                old_orb_img = cached_orb_images[transition_from_state]
                new_orb_img = cached_orb_images[state]
                
                # blend the two orb images together based on transition progress
                # both images need to be the same size and mode for blend to work
                base_orb = Image.blend(
                    old_orb_img.convert("RGBA"),
                    new_orb_img.convert("RGBA"),
                    progress
                )
        else:
            base_orb = cached_orb_images[state]
        
        # apply breathing scale on top of whatever orb we ended up with (steady state or mid-blend)
        scale = get_breathing_scale()
        new_size = int(base_orb.width * scale)
        scaled_orb = base_orb.resize((new_size, new_size), Image.LANCZOS)
        
        # ease the orb's horizontal position toward its target, same easing technique as the info panel fade
        global orb_current_x_ratio
        orb_current_x_ratio += (orb_target_x_ratio - orb_current_x_ratio) * 0.08
        
        frame = Image.new("RGB", (SCREEN_W, SCREEN_H), "#000000")
        paste_x = int(SCREEN_W * orb_current_x_ratio) - (new_size // 2)
        paste_y = (SCREEN_H - new_size) // 2
        frame.paste(scaled_orb, (paste_x, paste_y), scaled_orb)
        
        photo = ImageTk.PhotoImage(frame)
        
        existing = canvas.find_withtag("orb_img")
        if existing:
            canvas.itemconfig(existing[0], image=photo)
        else:
            canvas.create_image(0, 0, anchor="nw", image=photo, tags="orb_img")
        canvas.image = photo


        
        

       # determine target fade progress: 1.0 if panel should be visible, 0.0 if hidden
        global info_panel_visible, info_fade_progress
        if info_panel_visible and (time.time() - info_panel_show_time > INFO_PANEL_DURATION):
            info_panel_visible = False
        
        target_progress = 1.0 if info_panel_visible else 0.0
        
        # ease the reminder panel's fade progress toward its target, same technique as the info panel
        global reminder_fade_progress
        reminder_target = 1.0 if reminder_panel_visible else 0.0
        reminder_fade_progress += (reminder_target - reminder_fade_progress) * 0.25
        if abs(reminder_fade_progress - reminder_target) < 0.01:
            reminder_fade_progress = reminder_target
        
        global reminder_data
        if not reminder_panel_visible and reminder_fade_progress == 0.0:
            reminder_data = None
        
        if reminder_data is not None:
            reminder_time_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, reminder_fade_progress)
            reminder_msg_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, reminder_fade_progress)
            
            visible_state = "normal" if reminder_fade_progress > 0.0 else "hidden"
            
            raw_time = reminder_data.get("time", "")
            try:
                parsed_time = datetime.strptime(raw_time, "%H:%M")
                display_time = parsed_time.strftime("%-I:%M %p")
            except ValueError:
                display_time = raw_time
            
            reminder_time_items = canvas.find_withtag("reminder_time")
            if reminder_time_items:
                canvas.itemconfig(reminder_time_items[0], text=display_time, fill=reminder_time_color, state=visible_state)
            else:
                canvas.create_text(SCREEN_W * 0.62, 180, anchor="nw", text=display_time, fill=reminder_time_color, font=("Rubik Medium", 42), tags="reminder_time", state=visible_state)
            
            reminder_msg_items = canvas.find_withtag("reminder_message")
            if reminder_msg_items:
                canvas.itemconfig(reminder_msg_items[0], text=reminder_data.get("message", ""), fill=reminder_msg_color, state=visible_state)
            else:
                canvas.create_text(SCREEN_W * 0.62, 260, anchor="nw", text=reminder_data.get("message", ""), fill=reminder_msg_color, font=("Rubik Light", 22), tags="reminder_message", width=int(SCREEN_W * 0.33), state=visible_state)


        # smoothly move info_fade_progress toward the target each frame
        # this is a simple "ease toward target" — moves a fraction of the remaining distance each frame
        fade_speed = 0.15  # higher = faster fade, lower = slower/smoother
        info_fade_progress += (target_progress - info_fade_progress) * fade_speed
        
        # snap to exact 0 or 1 when very close, to avoid floating point drift sitting at like 0.0001 forever
        if abs(info_fade_progress - target_progress) < 0.01:
            info_fade_progress = target_progress
        
        # calculate the actual displayed colors based on current fade progress
        time_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, info_fade_progress)
        date_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, info_fade_progress)
        temp_color = interpolate_color(COLOR_BG, COLOR_PRIMARY_TEXT, info_fade_progress)
        desc_color = interpolate_color(COLOR_BG, COLOR_SECONDARY_TEXT, info_fade_progress)
        
        time_str = datetime.now().strftime("%-I:%M %p")
        time_items = canvas.find_withtag("time_text")
        if time_items:
            canvas.itemconfig(time_items[0], text=time_str, fill=time_color)
        else:
            canvas.create_text(20, 14, anchor="nw", text=time_str, fill=time_color, font=("Rubik Medium", 38), tags="time_text")
        
        date_str = datetime.now().strftime("%B %d")
        date_items = canvas.find_withtag("date_text")
        if date_items:
            canvas.itemconfig(date_items[0], text=date_str, fill=date_color)
        else:
            canvas.create_text(20, 64, anchor="nw", text=date_str, fill=date_color, font=("Rubik Light", 18), tags="date_text")
        
        weather_data_str = get_cached_weather()
        
        weather_icons = {
            "clear": "☀️", "sunny": "☀️",
            "cloud": "☁️", "overcast": "☁️",
            "rain": "🌧️", "drizzle": "🌦️",
            "storm": "⛈️", "thunder": "⛈️",
            "snow": "❄️",
            "fog": "🌫️", "mist": "🌫️", "haze": "🌫️",
            "wind": "💨",
        }
        
        icon = "🌡️"
        lower_desc = weather_data_str.lower()
        for keyword, emoji in weather_icons.items():
            if keyword in lower_desc:
                icon = emoji
                break
        
        temp_number = weather_data_str.split("°")[0] if "°" in weather_data_str else "--"
        temp_display = f"{temp_number}° {icon}"
        weather_desc = weather_data_str.split("  ", 1)[1] if "  " in weather_data_str else ""
        
        temp_items = canvas.find_withtag("temp_text")
        if temp_items:
            canvas.itemconfig(temp_items[0], text=temp_display, fill=temp_color)
        else:
            canvas.create_text(SCREEN_W - 20, 14, anchor="ne", text=temp_display, fill=temp_color, font=("Rubik Medium", 38), tags="temp_text")
        
        desc_items = canvas.find_withtag("desc_text")
        if desc_items:
            canvas.itemconfig(desc_items[0], text=weather_desc, fill=desc_color)
        else:
            canvas.create_text(SCREEN_W - 20, 64, anchor="ne", text=weather_desc, fill=desc_color, font=("Rubik Light", 16), tags="desc_text")


        time.sleep(0.02)

#-------------------------------------------------------------------------------------------------------------------------------------------

def start_display():
    global root, canvas
    
    root = tk.Tk()
    root.attributes('-fullscreen', True)
    root.configure(bg='black')
    
    canvas = tk.Canvas(root, width=SCREEN_W, height=SCREEN_H, bg='black', highlightthickness=0)
    canvas.pack()
    canvas.bind("<Button-1>", on_screen_tap)
    
    # render_loop runs forever, so it needs its own thread
    # daemon=True means this thread automatically dies when the main program exits
    render_thread = threading.Thread(target=render_loop, daemon=True)
    render_thread.start()
    
    root.mainloop()

#-------------------------------------------------------------------------------------------------------------------------------------------

def set_state(state):
    global current_state, transition_from_state, transition_start_time
    
    if state not in ORB_COLORS:
        print(f"Warning: unknown state '{state}', ignoring")
        return
    
    if state == current_state:
        return  # already in this state, nothing to do
    
    transition_from_state = current_state
    transition_start_time = time.time()
    current_state = state

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_cached_weather():
    global cached_weather, last_weather_fetch
    now = time.time()
    # only fetch from the API every 10 minutes — calling it every frame would hammer OpenWeatherMap for no reason
    if now - last_weather_fetch > 600:
        from weather import get_weather
        data = get_weather()
        if data:
            cached_weather = f"{data['temp']}°F  {data['description'].title()}"
        last_weather_fetch = now
    return cached_weather

#-------------------------------------------------------------------------------------------------------------------------------------------

def on_screen_tap(event):
    global info_panel_visible, info_panel_show_time
    
    if reminder_panel_visible:
        # if a reminder is currently showing, any tap dismisses it instead of revealing info
        dismiss_reminder()
    else:
        info_panel_visible = True
        info_panel_show_time = time.time()

#-------------------------------------------------------------------------------------------------------------------------------------------

def hex_to_rgb(hex_color):
    return tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))

#-------------------------------------------------------------------------------------------------------------------------------------------

def interpolate_color(color_a, color_b, progress):
    # blends from color_a to color_b based on progress (0.0 to 1.0)
    rgb_a = hex_to_rgb(color_a)
    rgb_b = hex_to_rgb(color_b)
    r = int(rgb_a[0] + (rgb_b[0] - rgb_a[0]) * progress)
    g = int(rgb_a[1] + (rgb_b[1] - rgb_a[1]) * progress)
    b = int(rgb_a[2] + (rgb_b[2] - rgb_a[2]) * progress)
    return f"#{r:02x}{g:02x}{b:02x}"

#-------------------------------------------------------------------------------------------------------------------------------------------

def set_orb_position(x_ratio):
    global orb_target_x_ratio
    safe_min = get_safe_min_x_ratio()
    orb_target_x_ratio = max(x_ratio, safe_min)  # never let it go further left than the safe boundary

#-------------------------------------------------------------------------------------------------------------------------------------------


def get_safe_min_x_ratio():
    orb_radius = ORB_SIZE / 2  # half-width of just the solid orb, not including glow
    min_pixel_x = orb_radius + 10  # 10px safety margin around the solid orb only
    return min_pixel_x / SCREEN_W

#-------------------------------------------------------------------------------------------------------------------------------------------

def show_reminder(reminder):
    global reminder_data, reminder_panel_visible
    reminder_data = reminder
    reminder_panel_visible = True
    set_orb_position(0.2)

#-------------------------------------------------------------------------------------------------------------------------------------------

def dismiss_reminder():
    global reminder_panel_visible
    reminder_panel_visible = False  # this triggers the fade-out in render_loop
    set_orb_position(0.5)
    set_state("idle")
    # reminder_data itself gets cleared automatically inside render_loop once the fade-out completes

#-------------------------------------------------------------------------------------------------------------------------------------------


#-------------------------------------------------------------------------------------------------------------------------------------------


#-------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    start_display()