import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import threading
import time
from datetime import datetime
import os

SCREEN_W = 800
SCREEN_H = 480
FACE_SIZE = 650

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
    now = datetime.now()
    canvas.create_text(200, 440, text=now.strftime("%I:%M %p"), fill="white" if state == "sleep" else "black", font=("Arial", 24, "bold"), tags="clock")

#-------------------------------------------------------------------------------------------------------------------------------------------

def update_clock():
    now = datetime.now()
    canvas.delete("clock")
    fill_color = "white" if current_state == "sleep" else "black"
    canvas.create_text(200, 440, text=now.strftime("%I:%M %p"), fill=fill_color, font=("Arial", 24, "bold"), tags="clock")
    root.after(1000, update_clock)

#-------------------------------------------------------------------------------------------------------------------------------------------

def fade_to_state(new_state):
    global current_state
    old_img = faces[current_state].convert("RGB")
    new_img = faces[new_state].convert("RGB")

    for i in range(15):
        alpha = i / 14
        blended_face = Image.blend(old_img, new_img, alpha)
        bg_color = get_background_color(new_state)
        bg = Image.new("RGB", (SCREEN_W, SCREEN_H), bg_color)
        face_x = (SCREEN_W - FACE_SIZE) // 2
        face_y = (SCREEN_H - FACE_SIZE) // 2 - 50
        bg.paste(blended_face, (face_x, face_y))
        photo = ImageTk.PhotoImage(bg)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.update()
        time.sleep(0.03)
    
    current_state = new_state
    draw_state(new_state)

#-------------------------------------------------------------------------------------------------------------------------------------------

def set_state(state):
    if state != current_state:
        fade_to_state(state)

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