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

ERROR_RESPONSES = [
    "Sorry, I didn't catch that.",
    "Hmm, I'm not sure what you said.",
    "Could you try that again?",
    "I didn't quite get that one.",
]

model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])

# ------------------------------------------------------------------

def listen_for_wake_word(display):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
    while True:
        audio_array = stream.read(3528)
        audio_array_int16 = np.frombuffer(audio_array, dtype=np.int16)
        resampled = resample(audio_array_int16, 1280).astype(np.int16)
        score = model.predict(resampled)
        if score["hey_soh_loo"] > 0.5:
            display.set_state("idle")
            stream.stop_stream()
            stream.close()
            command_text = listen_for_command(display)
            print("Command was:", command_text)
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
            if command_text == None:
                display.set_state("error")
                speak(random.choice(ERROR_RESPONSES))
                display.set_state("sleep")
                continue
            response = gemini.ask_gemini(command_text, [])
            if response == None:
                display.set_state("error")
                speak(random.choice(ERROR_RESPONSES))
                display.set_state("sleep")
                continue
            display.set_state("speak")
            speak(response)
            display.set_state("sleep")
            continue

# ------------------------------------------------------------------

def listen_for_command(display):
    r = sr.Recognizer()
    with sr.Microphone(device_index=1) as source:       
        try:
            audio = r.listen(source, timeout=5)
            display.set_state("think")
            text = r.recognize_google(audio)
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
