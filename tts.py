"""
tts.py: speech and sound playback.

Replies stream from Edge TTS straight into mpg123, so Solu starts talking as
soon as the first audio arrives instead of waiting for the whole reply to be
generated. gTTS is the fallback if Edge fails. Short fixed phrases (error
apologies) are cached to disk so Solu can still say them with no internet.
Nothing here raises: failures are logged and reported by return value.
"""

import asyncio
import hashlib
import os
import queue
import subprocess
import sys
import threading
import time

import edge_tts
import numpy as np
from gtts import gTTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "data", "tts_cache")

AUDIO_DEVICE = "hw:0,0"
PLAYER = ["mpg123", "-q", "-a", AUDIO_DEVICE]

# a second mpg123 decodes speech to raw samples so the screen can follow its loudness
DECODER = ["mpg123", "-q", "-s", "-m", "-r", "16000", "-e", "s16"]
LEVEL_RATE = 16000
LEVEL_WINDOW = 0.02         # one loudness value per 20ms of audio
LEVEL_RANGE_DB = 30         # loudness range mapped onto 0..1, below the loudest part so far
SPEECH_SYNC_OFFSET = 0.12   # seconds from handing audio to mpg123 until it's heard. Raise if rings lead the voice, lower if they lag

EDGE_VOICE = "en-GB-RyanNeural"
EDGE_RATE = "+0%"     # speed adjustment, e.g. "+8%" for slightly faster
EDGE_TIMEOUT = 8      # seconds to wait for Edge audio before giving up on it
GTTS_TIMEOUT = 10

_DONE = object()

# ------------------------------------------------------------------
# generation
# ------------------------------------------------------------------

def _edge_stream_worker(text, chunks):
    """Runs in its own thread, puts audio bytes on the queue, then _DONE or the exception."""
    async def run():
        communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk["data"]:
                chunks.put(chunk["data"])
    try:
        asyncio.run(run())
        chunks.put(_DONE)
    except Exception as e:
        chunks.put(e)


def _start_edge_stream(text):
    """Starts Edge and waits for the first audio. Returns (queue, first_bytes) or None if Edge failed."""
    chunks = queue.Queue()
    threading.Thread(target=_edge_stream_worker, args=(text, chunks), daemon=True).start()
    try:
        first = chunks.get(timeout=EDGE_TIMEOUT)
    except queue.Empty:
        print("tts: Edge timed out")
        return None
    if isinstance(first, Exception):
        print(f"tts: Edge failed: {first!r}")
        return None
    if first is _DONE:
        print("tts: Edge returned no audio")
        return None
    return chunks, first


def _gtts_to_file(text, path):
    try:
        try:
            tts = gTTS(text=text, lang="en", tld="com", slow=False, timeout=GTTS_TIMEOUT)
        except TypeError:  # older gTTS without the timeout argument
            tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(path)
        return True
    except Exception as e:
        print(f"tts: gTTS failed: {e!r}")
        return False


def generate_audio(text, path):
    """Writes speech to an mp3 file. Returns "edge", "gtts", or None if both failed."""
    started = _start_edge_stream(text)
    if started is not None:
        chunks, data = started
        try:
            with open(path, "wb") as f:
                f.write(data)
                while True:
                    data = chunks.get(timeout=EDGE_TIMEOUT)
                    if data is _DONE:
                        return "edge"
                    if isinstance(data, Exception):
                        raise data
                    f.write(data)
        except Exception as e:
            print(f"tts: Edge stopped mid-reply: {e!r}")
    return "gtts" if _gtts_to_file(text, path) else None

# ------------------------------------------------------------------
# loudness, for the screen
# ------------------------------------------------------------------

class LevelMeter:
    """How loud the speech is at each moment, so the orb can pulse with it.
    The same mp3 audio goes to a second mpg123 that decodes it (much faster
    than real time) instead of playing it, and every 20ms of audio becomes
    one loudness value from 0 to 1. level_at(time.time()) looks up the value
    for the moment being heard right now."""

    def __init__(self, path=None):
        """path: an mp3 file to read, or None to have audio fed in with feed()."""
        self.levels = []
        self.start_time = None
        self.peak_db = -22.0   # typical loudest speech, adapts upward to the real voice
        self.process = subprocess.Popen(
            DECODER + ([path] if path else ["-"]),
            stdin=subprocess.DEVNULL if path else subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=self._read_levels, daemon=True).start()

    @classmethod
    def create(cls, path=None):
        """A meter, or None if the decoder can't start. The orb just won't pulse then."""
        try:
            return cls(path)
        except OSError as e:
            print(f"tts: no level meter: {e!r}")
            return None

    def mark_started(self):
        self.start_time = time.time() + SPEECH_SYNC_OFFSET

    def feed(self, data):
        try:
            self.process.stdin.write(data)
        except (OSError, ValueError):
            pass

    def finish(self):
        try:
            self.process.stdin.close()
        except (OSError, ValueError, AttributeError):
            pass

    def stop(self):
        self.finish()
        _terminate(self.process)

    def _read_levels(self):
        window_bytes = int(LEVEL_RATE * LEVEL_WINDOW) * 2
        try:
            while True:
                data = self.process.stdout.read(window_bytes)
                if len(data) < 2:
                    break
                samples = np.frombuffer(data[:len(data) // 2 * 2], dtype=np.int16).astype(np.float32)
                db = 20 * np.log10(np.sqrt(np.mean(samples * samples)) / 32768 + 1e-9)
                self.peak_db = max(self.peak_db, db)
                self.levels.append(float(np.clip((db - self.peak_db + LEVEL_RANGE_DB) / LEVEL_RANGE_DB, 0.0, 1.0)))
        except (OSError, ValueError):
            pass

    def level_at(self, now):
        if self.start_time is None:
            return 0.0
        i = int((now - self.start_time) / LEVEL_WINDOW)
        levels = self.levels
        return levels[i] if 0 <= i < len(levels) else 0.0

# ------------------------------------------------------------------
# replies (non-blocking, interruptible)
# ------------------------------------------------------------------

def _feed_player(process, chunks, meter):
    """Pipes the rest of the Edge stream into mpg123 (and the level meter), then closes their inputs so they can finish."""
    try:
        while True:
            data = chunks.get(timeout=EDGE_TIMEOUT)
            if data is _DONE or isinstance(data, Exception):
                break
            if meter is not None:
                meter.feed(data)
            process.stdin.write(data)
    except (queue.Empty, OSError, ValueError):
        pass  # Edge stalled, or the player was stopped by a tap
    finally:
        if meter is not None:
            meter.finish()
        try:
            process.stdin.close()
        except (OSError, ValueError):
            pass


def start_speaking(text):
    """Starts speaking without blocking. Returns the player process (poll() it
    to see when speech ends, terminate() it to cut speech off), or None if no
    speech could be generated. The process carries a level_meter the screen
    reads to pulse with the voice (None if it couldn't start)."""
    started = _start_edge_stream(text)
    if started is not None:
        chunks, first = started
        meter = LevelMeter.create()
        try:
            process = subprocess.Popen(PLAYER + ["-"], stdin=subprocess.PIPE)
            if meter is not None:
                meter.feed(first)
            process.stdin.write(first)
        except OSError as e:
            print(f"tts: could not start player: {e!r}")
            if meter is not None:
                meter.stop()
            return None
        process.level_meter = meter
        if meter is not None:
            meter.mark_started()
        threading.Thread(target=_feed_player, args=(process, chunks, meter), daemon=True).start()
        return process

    path = os.path.join(BASE_DIR, f"temp_speech_{os.getpid()}.mp3")
    if not _gtts_to_file(text, path):
        return None
    meter = LevelMeter.create(path)
    process = _popen(PLAYER + [path])
    if process is None:
        if meter is not None:
            meter.stop()
        return None
    process.level_meter = meter
    if meter is not None:
        meter.mark_started()
    threading.Thread(target=_remove_when_done, args=(process, path), daemon=True).start()
    return process


def stop_speaking(process):
    """Stops a speech process (and its level meter) if still running. Safe on finished or None processes."""
    _terminate(process)
    meter = getattr(process, "level_meter", None)
    if meter is not None:
        meter.stop()


def _remove_when_done(process, path):
    process.wait()
    try:
        os.remove(path)
    except OSError:
        pass

# ------------------------------------------------------------------
# short phrases (blocking, cached)
# ------------------------------------------------------------------

def _cache_path(text):
    key = hashlib.sha1(f"{EDGE_VOICE}|{EDGE_RATE}|{text}".encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{key}.mp3")


def _cache_phrase(text):
    """Saves an Edge recording of text to the cache. Returns its path, or None."""
    path = _cache_path(text)
    if os.path.exists(path):
        return path
    os.makedirs(CACHE_DIR, exist_ok=True)
    temp = path + ".part"
    if generate_audio(text, temp) == "edge":
        os.replace(temp, path)
        return path
    if os.path.exists(temp):
        os.remove(temp)
    return None


def prepare_phrases(phrases):
    """Pre-records fixed phrases so they work offline. Run once in the background at startup."""
    for text in phrases:
        _cache_phrase(text)


def speak(text):
    """Blocking speech for short fixed phrases like apologies. Uses the cache
    when possible, so it still works with no internet."""
    path = _cache_path(text)
    if not os.path.exists(path):
        path = _cache_phrase(text)
    if path is None:  # Edge is down, try gTTS without caching it
        path = os.path.join(BASE_DIR, "temp_phrase.mp3")
        if not _gtts_to_file(text, path):
            print(f"tts: could not say {text!r}")
            return
        play_sound(path)
        os.remove(path)
        return
    play_sound(path)

# ------------------------------------------------------------------
# sound files
# ------------------------------------------------------------------

def _popen(cmd):
    try:
        return subprocess.Popen(cmd)
    except OSError as e:
        print(f"tts: could not start {cmd[0]}: {e!r}")
        return None


def _terminate(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()


def play_sound(filepath):
    """Blocking playback, for sounds where waiting is fine (e.g. the startup chime)."""
    process = _popen(PLAYER + [filepath])
    if process is not None:
        process.wait()


def start_alarm_sound(filepath):
    """Non-blocking playback, returns the process so it can be stopped instantly."""
    return _popen(PLAYER + [filepath])


def stop_alarm_sound(process):
    """Stops an alarm sound. Safe to call if it already finished or is None."""
    _terminate(process)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        process = start_speaking(" ".join(sys.argv[1:]))
        if process is not None:
            process.wait()
    else:
        print("Usage: python3 tts.py <text to speak>")
