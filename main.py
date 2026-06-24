import os
os.environ["SDL_AUDIODRIVER"] = "dummy"
import openwakeword
from openwakeword.model import Model
import pyaudio
import numpy as np
from scipy.signal import resample
from display import Display
import threading
import time
import speech_recognition as sr
import random
from tts import speak, play_sound
import gemini
import reminders

ERROR_RESPONSES = [
    "Sorry, I didn't catch that.",
    "Hmm, I'm not sure what you said.",
    "Could you try that again?",
    "I didn't quite get that one.",
]

model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])

# ------------------------------------------------------------------

def listen_for_wake_word(display):
    global model
    display.set_state("think")
    recognizer = sr.Recognizer()
    with sr.Microphone(device_index=1) as source:
        print("Calibrating for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=3)
        MIN_ENERGY_THRESHOLD = 800
        if recognizer.energy_threshold < MIN_ENERGY_THRESHOLD:
            print(f"Calibrated threshold {recognizer.energy_threshold:.1f} too low, raising to floor of {MIN_ENERGY_THRESHOLD}")
            recognizer.energy_threshold = MIN_ENERGY_THRESHOLD
        print("Energy threshold set to:", recognizer.energy_threshold)
    display.set_state("sleep")

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
    while True:
        try:
            audio_array = stream.read(3528)
        except OSError as e:
            print("Mic read error, recovering:", e)
            try:
                stream.stop_stream()
                stream.close()
            except OSError:
                pass
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
            continue

        audio_array_int16 = np.frombuffer(audio_array, dtype=np.int16)
        resampled = resample(audio_array_int16, 1280).astype(np.int16)
        score = model.predict(resampled)
        if score["hey_soh_loo"] > 0.3:
            display.set_state("idle")
            play_sound("sounds/startup.mp3")
            stream.stop_stream()
            stream.close()

            history = []

            while True:
                command_text = listen_for_command(display, recognizer)
                print("Command was:", command_text)

                if command_text == None:
                    display.set_state("error")
                    speak(random.choice(ERROR_RESPONSES))
                    time.sleep(3)
                    display.set_state("sleep")
                    break
                response, follow_up = gemini.ask_gemini(command_text, history)
                if response == None:
                    display.set_state("error")
                    speak(random.choice(ERROR_RESPONSES))
                    time.sleep(3)
                    display.set_state("sleep")
                    break

                history.append({"role": "user", "parts": [{"text": command_text}]})
                history.append({"role": "model", "parts": [{"text": response}]})

                display.set_state("speak")
                speak(response)

                if follow_up:
                    display.set_state("idle")
                    time.sleep(3)
                    continue
                else:
                    time.sleep(3)
                    display.set_state("sleep")
                    break

            model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
            continue


# ------------------------------------------------------------------

def listen_for_command(display, recognizer):
    with sr.Microphone(device_index=1) as source:
        try:
            audio = recognizer.listen(source, timeout=5)
            display.set_state("think")
            text = recognizer.recognize_google(audio)
            return text
        except:
            return None

# ------------------------------------------------------------------

def check_reminders_loop(display):
    while True:
        if display.current_state == "sleep":
            due = reminders.check_due_reminders()
            for reminder in due:
                while display.current_state != "sleep":
                    time.sleep(1)
                display.show_reminder(reminder)
                display.set_state("alarm")
                while display.reminder_data is not None:
                    play_sound("sounds/alarm.mp3")
                reminders.mark_completed(reminder["id"])
        time.sleep(30)


# ------------------------------------------------------------------
if __name__ == "__main__":
    display = Display()
    t = threading.Thread(target=listen_for_wake_word, args=(display,), daemon=True)
    t.start()
    t2 = threading.Thread(target=check_reminders_loop, args=(display,), daemon=True)
    t2.start()
    display.run()