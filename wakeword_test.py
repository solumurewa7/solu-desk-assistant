import pyaudio
import numpy as np
from openwakeword.model import Model
from scipy.signal import resample

model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])

def listen_for_wake_word():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
    while True:
        audio_array = stream.read(3528)
        audio_array_int16 = np.frombuffer(audio_array, dtype=np.int16)
        resampled = resample(audio_array_int16, 1280).astype(np.int16)
        score = model.predict(resampled)
        print(score)
        if score["hey_soh_loo"] > 0.5: break
    stream.stop_stream()
    stream.close()
    p.terminate()



if __name__ == "__main__":
    listen_for_wake_word()
    print("Wake word detected!")