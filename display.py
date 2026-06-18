import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import threading
import time
from datetime import datetime
import os

cached_weather = "Loading weather..."
last_weather_fetch = 0

SCREEN_W = 800
SCREEN_H = 480
FACE_SIZE = 520

FACE_FILES = {
    "sleep":  "assets/sleep.png",
    "idle":   "assets/listen.png",
    "speak":  "assets/speak.png",
    "joking": "assets/witty.png",
    "think":  "assets/think.png",
    "error":  "assets/error.png",
    "alarm":  "assets/alarm.png",
}

BG_COLORS = {
    "sleep":  "#000000",
    "idle":   "#f0f0f0",
    "speak":  "#f0f0f0",
    "joking": "#f0f0f0",
    "think":  "#f0f0f0",
    "error":  "#f0f0f0",
    "alarm":  "#6a0dad",
}

current_state = "sleep"
canvas = None
root = None
faces = {}
current_image_id = None

def load_faces():
    for state, filepath in FACE_FILES.items():
        img = Image.open(filepath)
        img = img.resize((FACE_SIZE, FACE_SIZE), Image.NEAREST)
        faces[state] = img

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_background_color(state):
    try:
        return BG_COLORS[state]
    except:
        return None
    
#-------------------------------------------------------------------------------------------------------------------------------------------

def draw_state(state):
    background_color = get_background_color(state)
    canvas.delete("all")
    canvas.configure(bg=background_color)
    bg_img = Image.new("RGB", (SCREEN_W, SCREEN_H), background_color)
    hour = datetime.now().hour

    if state == "sleep" and (hour >= 22 or hour < 7):
        return
    
    face_x = (SCREEN_W - FACE_SIZE) // 2
    face_y = (SCREEN_H - FACE_SIZE) // 2 - 50
    bg_img.paste(faces[state], (face_x, face_y), faces[state])
    photo = ImageTk.PhotoImage(bg_img)
    canvas.create_image(0, 0, anchor="nw", image=photo)
    canvas.image = photo
    if state != "alarm":
        now = datetime.now()
        canvas.create_text(250, 450, text=now.strftime("%I:%M %p"), fill="white" if state == "sleep" else "black", font=("Arial", 24, "bold"), tags="clock")
        canvas.create_text(550, 450, text=get_cached_weather(), fill="white" if state == "sleep" else "black", font=("Arial", 24), tags="weather")

#-------------------------------------------------------------------------------------------------------------------------------------------

def update_clock():
    now = datetime.now()
    canvas.delete("clock")
    canvas.delete("weather")
    if current_state != "alarm":
        fill_color = "white" if current_state == "sleep" else "black"
        canvas.create_text(250, 450, text=now.strftime("%I:%M %p"), fill=fill_color, font=("Arial", 24, "bold"), tags="clock")
        canvas.create_text(550, 450, text=get_cached_weather(), fill=fill_color, font=("Arial", 24), tags="weather")
    root.after(1000, update_clock)

#-------------------------------------------------------------------------------------------------------------------------------------------

def fade_to_state(new_state):
    global current_state
    old_bg_color = get_background_color(current_state)
    new_bg_color = get_background_color(new_state)

    old_base = Image.new("RGBA", (FACE_SIZE, FACE_SIZE), old_bg_color)
    old_base.paste(faces[current_state], (0, 0), faces[current_state])
    old_img = old_base.convert("RGB")

    new_base = Image.new("RGBA", (FACE_SIZE, FACE_SIZE), new_bg_color)
    new_base.paste(faces[new_state], (0, 0), faces[new_state])
    new_img = new_base.convert("RGB")

    face_x = (SCREEN_W - FACE_SIZE) // 2
    face_y = (SCREEN_H - FACE_SIZE) // 2 - 50

    old_shows_text = current_state != "alarm"
    new_shows_text = new_state != "alarm"
    time_str = datetime.now().strftime("%I:%M %p")
    weather_str = get_cached_weather()

    # set up persistent canvas items ONCE — reused every frame via itemconfig
    canvas.delete("all")
    initial_bg = Image.new("RGB", (SCREEN_W, SCREEN_H), old_bg_color)
    initial_bg.paste(old_img, (face_x, face_y))
    photo = ImageTk.PhotoImage(initial_bg)
    img_id = canvas.create_image(0, 0, anchor="nw", image=photo)
    canvas.image = photo

    old_text_color = "white" if current_state == "sleep" else "black"
    clock_id = canvas.create_text(250, 450, text=time_str, fill=old_text_color, font=("Arial", 24, "bold"), tags="clock")
    weather_id = canvas.create_text(550, 450, text=weather_str, fill=old_text_color, font=("Arial", 24), tags="weather")
    if not old_shows_text:
        canvas.itemconfig(clock_id, state="hidden")
        canvas.itemconfig(weather_id, state="hidden")

    def render_frame(bg_img, text_alpha, target_text_color, show_text):
        nonlocal_photo = ImageTk.PhotoImage(bg_img)
        canvas.itemconfig(img_id, image=nonlocal_photo)
        canvas.image = nonlocal_photo
        if show_text:
            canvas.itemconfig(clock_id, state="normal", fill=target_text_color)
            canvas.itemconfig(weather_id, state="normal", fill=target_text_color)
        else:
            canvas.itemconfig(clock_id, state="hidden")
            canvas.itemconfig(weather_id, state="hidden")
        canvas.update_idletasks()

    new_text_color = "white" if new_state == "sleep" else "black"

    # PHASE 1: fade old face OUT, fade text out too if it was showing
    for i in range(10):
        alpha = i / 9
        old_solid = Image.new("RGB", (FACE_SIZE, FACE_SIZE), old_bg_color)
        blended_face = Image.blend(old_img, old_solid, alpha)
        bg = Image.new("RGB", (SCREEN_W, SCREEN_H), old_bg_color)
        bg.paste(blended_face, (face_x, face_y))
        show_text_now = old_shows_text and alpha < 0.6  # text fades out in first 60% of phase 1
        render_frame(bg, alpha, old_text_color, show_text_now)
        time.sleep(0.02)

    # PHASE 2: background color crossfades, text stays hidden
    old_r, old_g, old_b = int(old_bg_color[1:3], 16), int(old_bg_color[3:5], 16), int(old_bg_color[5:7], 16)
    new_r, new_g, new_b = int(new_bg_color[1:3], 16), int(new_bg_color[3:5], 16), int(new_bg_color[5:7], 16)
    for i in range(8):
        alpha = i / 7
        r = int(old_r + (new_r - old_r) * alpha)
        g = int(old_g + (new_g - old_g) * alpha)
        b = int(old_b + (new_b - old_b) * alpha)
        blended_bg_color = f"#{r:02x}{g:02x}{b:02x}"
        bg = Image.new("RGB", (SCREEN_W, SCREEN_H), blended_bg_color)
        render_frame(bg, alpha, new_text_color, False)
        time.sleep(0.02)

    # PHASE 3: fade new face IN with scale pop, fade text in toward the end
    for i in range(12):
        alpha = i / 11
        new_solid = Image.new("RGB", (FACE_SIZE, FACE_SIZE), new_bg_color)
        blended_face = Image.blend(new_solid, new_img, alpha)
        scale = 0.9 + (0.1 * alpha)
        scaled_size = int(FACE_SIZE * scale)
        scaled_face = blended_face.resize((scaled_size, scaled_size), Image.NEAREST)
        bg = Image.new("RGB", (SCREEN_W, SCREEN_H), new_bg_color)
        scaled_x = (SCREEN_W - scaled_size) // 2
        scaled_y = (SCREEN_H - scaled_size) // 2 - 50
        bg.paste(scaled_face, (scaled_x, scaled_y))
        show_text_now = new_shows_text and alpha > 0.4  # text fades in during last 60% of phase 3
        render_frame(bg, alpha, new_text_color, show_text_now)
        time.sleep(0.02)

    current_state = new_state
    draw_state(new_state)

#-------------------------------------------------------------------------------------------------------------------------------------------

def set_state(state):
    if state != current_state:
        fade_to_state(state)

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_cached_weather():
    global cached_weather, last_weather_fetch
    now = time.time()
    if now - last_weather_fetch > 600:  # 600 seconds = 10 minutes
        from weather import get_weather
        data = get_weather()
        if data:
            cached_weather = f"{data['temp']}°F  {data['description'].title()}"
        last_weather_fetch = now
    return cached_weather

#-------------------------------------------------------------------------------------------------------------------------------------------

def start_display():
    global root, canvas
    
    root = tk.Tk()
    root.attributes('-fullscreen', True)
    root.configure(bg='black')
    
    canvas = tk.Canvas(root, width=SCREEN_W, height=SCREEN_H, bg='black', highlightthickness=0)
    canvas.pack()
    
    load_faces()
    draw_state(current_state)
    update_clock()
    
    root.mainloop()

#-------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    start_display()