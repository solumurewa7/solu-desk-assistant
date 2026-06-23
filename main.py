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
from tts import speak
import gemini
import wave

ERROR_RESPONSES = [
    "Sorry, I didn't catch that.",
    "Hmm, I'm not sure what you said.",
    "Could you try that again?",
    "I didn't quite get that one.",
]

model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])
recognizer = sr.Recognizer()
with sr.Microphone(device_index=1) as source:
    print("Calibrating for ambient noise...")
    recognizer.adjust_for_ambient_noise(source, duration=1)
    print("Energy threshold set to:", recognizer.energy_threshold)

# ------------------------------------------------------------------

def listen_for_wake_word(display):
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
        if score["hey_soh_loo"] > 0.4:
            print(f"[{time.time():.2f}] WAKE WORD DETECTED, score={score['hey_soh_loo']:.4f}")
            wf = wave.open(f"trigger_audio_{int(time.time())}.wav", "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes = 16-bit
            wf.setframerate(44100)
            wf.writeframes(audio_array)  # the raw bytes read this exact chunk, before resampling
            wf.close()
            display.set_state("idle")
            stream.stop_stream()
            stream.close()

            while True:
                command_text = listen_for_command(display, recognizer)
                print(f"[{time.time():.2f}] Command was:", command_text)

                if command_text == None:
                    print(f"[{time.time():.2f}] Timeout/error branch entered")
                    display.set_state("error")
                    speak(random.choice(ERROR_RESPONSES))
                    time.sleep(3)
                    display.set_state("sleep")
                    print(f"[{time.time():.2f}] Set to sleep, breaking conversation loop")
                    break 
                response, follow_up = gemini.ask_gemini(command_text, [])
                print(f"[{time.time():.2f}] Gemini response, follow_up={follow_up}")
                if response == None:
                    display.set_state("error")
                    print("displayed error")
                    speak(random.choice(ERROR_RESPONSES))
                    time.sleep(3)
                    display.set_state("sleep")
                    print("displayed sleep")
                    break

                display.set_state("speak")
                print("displayed speak")
                speak(response)

                if follow_up:
                    display.set_state("idle")
                    print("displayed followup")
                    time.sleep(3)
                    continue
                else:
                    time.sleep(3)
                    display.set_state("sleep")
                    print("displayed sleep")
                    break
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

# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ------------------------------------------------------------------
if __name__ == "__main__":
    display = Display()
    t = threading.Thread(target=listen_for_wake_word, args=(display,), daemon=True)
    t.start()
    display.run()
