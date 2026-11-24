"""
mic.py: one shared USB mic stream for wake word listening and command capture.

The stream is opened once and only paused/resumed, never closed and reopened,
so there is no gap or device re-init between hearing "hey solu" and listening
for the command.
"""

import queue
import threading
import time

import numpy as np
import pyaudio
import speech_recognition as sr
from scipy.signal import resample_poly

MIC_DEVICE_INDEX = 1
MIC_RATE = 44100      # the CM108's native rate
WAKE_CHUNK = 3528     # 80ms at 44.1kHz, becomes exactly 1280 samples at 16kHz
COMMAND_CHUNK = 1024  # same chunk size sr.Microphone used

# ------------------------------------------------------------------


class StreamResampler:
    """Resamples 44.1kHz chunks to 16kHz as one continuous stream. Resampling
    each 80ms chunk on its own (like scipy's resample does) treats the chunk as
    a loop and puts a click at every chunk edge, which the wake model hears."""

    UP, DOWN = 160, 441   # 16000 / 44100 reduced
    PAD = 441             # context samples kept on each side of the chunk

    def __init__(self):
        self.reset()

    def reset(self):
        self.buffer = np.zeros(2 * self.PAD, dtype=np.float32)

    def process(self, chunk):
        self.buffer = np.concatenate((self.buffer, chunk.astype(np.float32)))
        out = resample_poly(self.buffer, self.UP, self.DOWN)
        start = self.PAD * self.UP // self.DOWN
        result = out[start:start + len(chunk) * self.UP // self.DOWN]
        self.buffer = self.buffer[len(chunk):]
        return np.clip(np.round(result), -32768, 32767).astype(np.int16)

# ------------------------------------------------------------------


class Mic:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.stream = None
        self.resampler = StreamResampler()
        self.rms = 0.0   # loudness of the latest audio read, 0 while paused
        self._recorder = None
        self._recording = False
        self._recorded = queue.Queue()
        self._pending = b""
        self._open()

    def _open(self):
        self.stream = self.pa.open(
            format=pyaudio.paInt16, channels=1, rate=MIC_RATE, input=True,
            input_device_index=MIC_DEVICE_INDEX, frames_per_buffer=WAKE_CHUNK,
        )

    def _reopen(self):
        """Last resort if the device errors out (e.g. a USB hiccup)."""
        try:
            self.stream.close()
        except Exception:
            pass
        time.sleep(0.5)
        self._open()
        self.resampler.reset()

    def start(self):
        """Resumes the stream. Audio from while it was paused is never delivered."""
        if self.stream.is_stopped():
            try:
                self.stream.start_stream()
            except OSError:
                self._reopen()

    def start_recording(self):
        """Keeps reading the mic in a background thread into a buffer, so audio
        isn't lost while the caller is busy (e.g. waiting on Google)."""
        if self._recording:
            return
        self.start()
        self._recorded = queue.Queue()
        self._pending = b""
        self._recording = True
        self._recorder = threading.Thread(target=self._record, daemon=True)
        self._recorder.start()

    def _record(self):
        try:
            while self._recording:
                self._recorded.put(self.read(COMMAND_CHUNK))
        except OSError as e:
            print(f"mic: background recording stopped: {e}")
            self._recording = False

    def stop_recording(self):
        self._recording = False
        if self._recorder is not None:
            self._recorder.join(timeout=1)
            self._recorder = None

    def read_command(self, frames):
        """Reads command audio: from the background buffer while recording, else straight from the mic."""
        if not self._recording and self._recorded.empty() and not self._pending:
            return self.read(frames)
        needed = frames * 2
        while len(self._pending) < needed:
            try:
                self._pending += self._recorded.get(timeout=2)
            except queue.Empty:
                raise OSError("mic: no audio arriving")
        data, self._pending = self._pending[:needed], self._pending[needed:]
        return data

    def pause(self):
        """Stops capture (e.g. while Solu talks) without releasing the device."""
        self.stop_recording()
        self._recorded = queue.Queue()
        self._pending = b""
        self.rms = 0.0
        if not self.stream.is_stopped():
            try:
                self.stream.stop_stream()
            except OSError:
                self._reopen()
                self.stream.stop_stream()

    def read(self, frames):
        """Reads raw bytes. Overflow never raises: a late read just keeps the
        newest audio instead of throwing the chunk away."""
        for attempt in range(3):
            try:
                data = self.stream.read(frames, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                self.rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
                return data
            except OSError as e:
                print(f"mic: read failed ({e}), reopening")
                self._reopen()
        raise OSError("mic: stream keeps failing")

    def read_wake_chunk(self):
        """Returns (raw 44.1kHz int16 samples, 16kHz int16 samples for the wake model)."""
        raw = np.frombuffer(self.read(WAKE_CHUNK), dtype=np.int16)
        return raw, self.resampler.process(raw)

    def level(self, speech_threshold):
        """Loudness from 0 (background noise) to 1 (talking), relative to the calibrated speech threshold."""
        return min(max((self.rms - 0.7 * speech_threshold) / (3.0 * speech_threshold), 0.0), 1.0)

    def command_source(self):
        """A speech_recognition source that reads from this same stream."""
        return _CommandSource(self)

# ------------------------------------------------------------------


class _CommandSource(sr.AudioSource):
    """Drop-in for sr.Microphone, backed by the shared stream."""

    def __init__(self, mic):
        self.mic = mic
        self.SAMPLE_RATE = MIC_RATE
        self.SAMPLE_WIDTH = 2
        self.CHUNK = COMMAND_CHUNK
        self.stream = None

    def __enter__(self):
        self.mic.start()
        self.stream = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream = None

    def read(self, size):
        return self.mic.read_command(size)
