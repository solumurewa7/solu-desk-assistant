"""
voice_check.py: checks the wake word pipeline, first alone, then with the GPU screen running.

    sudo systemctl stop solu.service
    DISPLAY=:0 python3 tools/voice_check.py
    sudo systemctl start solu.service

Say "hey solu" a few times during EACH phase. Every second it prints:
  chunks   audio chunks the wake model got (should be about 12)
  behind   audio waiting in the mic buffer (should stay small, big = falling behind)
  loudest  loudest mic level that second
  score    best wake word score that second (above 0.4 wakes Solu)
"""

import os
import sys
import threading
import time

os.environ["SDL_AUDIODRIVER"] = "dummy"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

import numpy as np
from openwakeword.model import Model

from mic import Mic

WAKE_MODEL_PATH = os.path.join(BASE_DIR, "assets", "wakeword", "hey_soh_loo.onnx")
PHASE_SECONDS = 12


def wake_loop(mic, model, stop, label, results):
    second_start = time.time()
    chunks, loudest, best, behind, slowest = 0, 0.0, 0.0, 0, 0.0
    phase_best = 0.0
    while not stop.is_set():
        behind = max(behind, mic.stream.get_read_available())
        raw, chunk_16k = mic.read_wake_chunk()
        t = time.perf_counter()
        score = model.predict(chunk_16k)["hey_soh_loo"]
        slowest = max(slowest, time.perf_counter() - t)
        chunks += 1
        loudest = max(loudest, float(np.sqrt(np.mean(raw.astype(np.float32) ** 2))))
        best = max(best, score)
        phase_best = max(phase_best, score)
        if time.time() - second_start >= 1.0:
            print(f"[{label}] chunks {chunks:2d}  behind {behind:6d}  loudest {loudest:6.0f}  "
                  f"score {best:.2f}  slowest step {slowest * 1000:4.0f}ms", flush=True)
            second_start = time.time()
            chunks, loudest, best, behind, slowest = 0, 0.0, 0.0, 0, 0.0
    results[label] = phase_best


def main():
    # (the screen process must not re-run this file, see the __main__ guard at the bottom)
    print("opening mic and wake model...")
    mic = Mic()
    model = Model(wakeword_model_paths=[WAKE_MODEL_PATH])
    results = {}

    print(f"\nPHASE 1: wake word alone, {PHASE_SECONDS}s. Say 'hey solu' a few times now.")
    stop = threading.Event()
    t = threading.Thread(target=wake_loop, args=(mic, model, stop, "alone", results))
    t.start()
    time.sleep(PHASE_SECONDS)
    stop.set()
    t.join()

    print("\nstarting the GPU screen in its own process (how Solu runs it now)...")
    from display import Display
    display = Display()
    time.sleep(3)  # let the screen open

    model = Model(wakeword_model_paths=[WAKE_MODEL_PATH])
    mic.resampler.reset()
    print(f"\nPHASE 2: wake word WITH the screen, {PHASE_SECONDS}s. Say 'hey solu' a few times now.")
    stop = threading.Event()
    t = threading.Thread(target=wake_loop, args=(mic, model, stop, "screen", results))
    t.start()
    end = time.time() + PHASE_SECONDS
    states = ["idle", "think", "speak", "sleep"]
    while time.time() < end:  # keep the screen busy changing states like real use
        display.set_state(states[int(time.time() / 2) % len(states)])
        time.sleep(0.1)
    stop.set()
    t.join()
    alive = display._process.is_alive()
    display._process.terminate()

    print(f"\nscreen process was {'running' if alive else 'NOT running'} during phase 2")
    print(f"best score alone: {results.get('alone', 0):.2f}   best score with screen: {results.get('screen', 0):.2f}")


if __name__ == "__main__":
    main()
