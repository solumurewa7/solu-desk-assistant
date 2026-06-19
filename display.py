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
        
        frame = Image.new("RGB", (SCREEN_W, SCREEN_H), "#000000")
        paste_x = (SCREEN_W - new_size) // 2
        paste_y = (SCREEN_H - new_size) // 2
        frame.paste(scaled_orb, (paste_x, paste_y), scaled_orb)
        
        photo = ImageTk.PhotoImage(frame)
        
        existing = canvas.find_withtag("orb_img")
        if existing:
            canvas.itemconfig(existing[0], image=photo)
        else:
            canvas.create_image(0, 0, anchor="nw", image=photo, tags="orb_img")
        canvas.image = photo

        date_str = datetime.now().strftime("%B %d")
        weather_str = get_cached_weather()
        
        date_items = canvas.find_withtag("date_text")
        if date_items:
            canvas.itemconfig(date_items[0], text=date_str)
        else:
            canvas.create_text(20, 20, anchor="nw", text=date_str, fill="white", font=("Rubik", 20, "bold"), tags="date_text")
        
        weather_items = canvas.find_withtag("weather_text")
        if weather_items:
            canvas.itemconfig(weather_items[0], text=weather_str)
        else:
            canvas.create_text(SCREEN_W - 20, 20, anchor="ne", text=weather_str, fill="white", font=("Rubik", 20, "bold"), tags="weather_text")
        time.sleep(0.02)

#-------------------------------------------------------------------------------------------------------------------------------------------

def start_display():
    global root, canvas
    
    root = tk.Tk()
    root.attributes('-fullscreen', True)
    root.configure(bg='black')
    
    canvas = tk.Canvas(root, width=SCREEN_W, height=SCREEN_H, bg='black', highlightthickness=0)
    canvas.pack()
    
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


#-------------------------------------------------------------------------------------------------------------------------------------------


#-------------------------------------------------------------------------------------------------------------------------------------------


#-------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    start_display()