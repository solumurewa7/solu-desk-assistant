import openwakeword
from openwakeword.model import Model
import pyaudio
import numpy as np
from scipy.signal import resample
from display import Display
import threading
import time

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
            time.sleep(1)
            continue

# ------------------------------------------------------------------

if __name__ == "__main__":
    display = Display()
    t = threading.Thread(target=listen_for_wake_word, args=(display,), daemon=True)
    t.start()
    display.run()
