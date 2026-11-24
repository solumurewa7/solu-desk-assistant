import os
os.environ["SDL_AUDIODRIVER"] = "dummy"  # pygame must not grab the speaker, mpg123 uses it

import random
import sys
import threading
import time
import traceback

import numpy as np
import RPi.GPIO as GPIO
import speech_recognition as sr
from openwakeword.model import Model

import gemini
import reminders
import tts
from display import Display
from mic import Mic

sys.stdout.reconfigure(line_buffering=True)  # print() shows up live in journalctl instead of sitting in a buffer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WAKE_MODEL_PATH = os.path.join(BASE_DIR, "assets", "wakeword", "hey_soh_loo.onnx")
WAKE_WORD = "hey_soh_loo"
STARTUP_SOUND = os.path.join(BASE_DIR, "sounds", "startup.mp3")
ALARM_SOUND = os.path.join(BASE_DIR, "sounds", "alarm.mp3")

WAKE_THRESHOLD = 0.4          # model confidence (0 to 1) needed to trigger: lower is easier to wake, higher means fewer false triggers
NEAR_MISS_SCORE = 0.15        # scores above this but under the threshold get logged, for tuning
MIN_ENERGY_THRESHOLD = 800    # floor for speech detection, calibration sometimes comes out too low
COMMAND_TIMEOUT = 5           # seconds to start talking after the wake word
PHRASE_TIME_LIMIT = 15        # max seconds for one command, so constant noise can't keep it listening forever
PAUSE_THRESHOLD = 1.4         # seconds of quiet that count as "done talking" (library default 0.8 cut people off mid-sentence). Lower = snappier replies, higher = more room to pause
CONTINUE_TIMEOUT = 4          # if what you said sounds unfinished ("...and"), seconds to wait for the rest
MAX_CONTINUATIONS = 3

# a command ending in one of these words clearly isn't finished yet. Only words
# that almost never end a real sentence ("turn the lights on" ends in "on", so "on" isn't here)
UNFINISHED_ENDINGS = {
    "and", "but", "or", "because", "cause", "plus", "also",
    "the", "a", "an", "my", "your", "our", "their",
    "of", "to", "with", "if",
    "um", "uh", "uhm", "umm", "hmm", "er", "erm",
}
SPEECH_SERVICE_TIMEOUT = 10   # seconds to wait on Google speech recognition
MIC_CHECK_INTERVAL = 600      # seconds between [mic check] log lines

PIR_PIN = 17
REMINDER_POLL_SECONDS = 10
ALARM_TIMEOUT_SECONDS = 15 * 60  # an alarm nobody dismisses stops itself after this long

ERROR_RESPONSES = [
    "Sorry, I didn't catch that.",
    "Hmm, I'm not sure what you said.",
    "Could you try that again?",
    "I didn't quite get that one.",
]
OFFLINE_RESPONSE = "I can't reach the internet right now."
BRAIN_RESPONSE = "My brain isn't responding right now. Try again in a bit."
ALL_PHRASES = ERROR_RESPONSES + [OFFLINE_RESPONSE, BRAIN_RESPONSE]

# ------------------------------------------------------------------
# voice thread
# ------------------------------------------------------------------

def voice_loop(display):
    """Calibrates the mic, then listens for the wake word forever."""
    mic = Mic()
    recognizer = sr.Recognizer()
    recognizer.operation_timeout = SPEECH_SERVICE_TIMEOUT
    recognizer.pause_threshold = PAUSE_THRESHOLD

    # calibrate once at startup, orange (think) so the user knows not to talk yet
    display.set_state("think")
    print("Calibrating for ambient noise...")
    with mic.command_source() as source:
        recognizer.adjust_for_ambient_noise(source, duration=3)
    if recognizer.energy_threshold < MIN_ENERGY_THRESHOLD:
        print(f"Calibrated threshold {recognizer.energy_threshold:.1f} too low, raising to floor of {MIN_ENERGY_THRESHOLD}")
        recognizer.energy_threshold = MIN_ENERGY_THRESHOLD
    print(f"Energy threshold set to: {recognizer.energy_threshold:.1f}")
    display.input_level_fn = lambda: mic.level(recognizer.energy_threshold)  # the orb reacts to your voice while listening
    display.set_state("sleep")

    model = Model(wakeword_model_paths=[WAKE_MODEL_PATH])
    mic.resampler.reset()

    peak_level = max_score = slowest_chunk = 0.0
    last_mic_check = time.time()

    while True:
        raw, chunk_16k = mic.read_wake_chunk()
        started = time.perf_counter()
        score = model.predict(chunk_16k)[WAKE_WORD]
        slowest_chunk = max(slowest_chunk, time.perf_counter() - started)

        peak_level = max(peak_level, float(np.sqrt(np.mean(raw.astype(np.float32) ** 2))))
        max_score = max(max_score, score)
        if NEAR_MISS_SCORE < score <= WAKE_THRESHOLD:
            print(f"wake word near miss: score {score:.2f} (threshold {WAKE_THRESHOLD})")
        if time.time() - last_mic_check >= MIC_CHECK_INTERVAL:
            print(f"[mic check] loudest level: {peak_level:.0f}, highest wake score: {max_score:.2f}, "
                  f"slowest model step: {slowest_chunk * 1000:.0f}ms (budget 80ms)")
            peak_level = max_score = slowest_chunk = 0.0
            last_mic_check = time.time()

        if score <= WAKE_THRESHOLD:
            continue

        print(f"wake word heard (score {score:.2f})")
        if display.claim_wake() == "alarm":
            handle_alarm_wake(display, mic, recognizer)
        else:
            mic.pause()  # so the chime isn't heard as the command
            run_conversation(display, mic, recognizer)

        # a fresh model clears its rolling buffer, otherwise the speech that
        # just happened can trigger a false wake right after this
        model = Model(wakeword_model_paths=[WAKE_MODEL_PATH])
        mic.resampler.reset()
        mic.start()


def handle_alarm_wake(display, mic, recognizer):
    """Wake word during an alarm: the alarm mutes (see ring_alarm) while we
    listen for "stop". The mic keeps running so "hey solu stop" in one breath works."""
    text, problem = listen_for_command(display, mic, recognizer)
    print(f"heard during alarm: {text!r}")
    if text and ("stop" in text.lower() or "alarm" in text.lower()):
        display.dismiss_reminder()
    elif display.reminder_panel_visible:
        display.set_state("alarm")  # back to ringing
    else:
        display.set_state("sleep")  # a tap dismissed it while we were listening


def run_conversation(display, mic, recognizer):
    """Startup chime, then command -> Gemini -> spoken reply, looping while Gemini expects a follow-up."""
    tts.play_sound(STARTUP_SOUND)
    history = []
    while True:
        text, problem = listen_for_command(display, mic, recognizer)
        print(f"heard: {text!r}")
        if text is None:
            apologize(display, problem)
            return

        try:
            reply, follow_up = gemini.ask_gemini(text, history)
        except gemini.OfflineError:
            apologize(display, "offline")
            return
        except gemini.GeminiError:
            apologize(display, "brain")
            return

        history.append({"role": "user", "parts": [{"text": text}]})
        history.append({"role": "model", "parts": [{"text": reply}]})

        if not speak_reply(display, reply):
            return  # tapped to stop, or speech failed
        if not follow_up:
            display.set_state("sleep")
            return
        display.set_state("idle")


def sounds_unfinished(text):
    words = text.lower().replace("'", "").rstrip(" .,!?").split()
    return bool(words) and words[-1] in UNFINISHED_ENDINGS


def listen_for_command(display, mic, recognizer):
    """Listens for one command. Returns (text, None) or (None, problem) where
    problem is "no_speech", "unclear", or "offline".

    The mic keeps recording in the background while Google transcribes, so
    nothing said during that moment is lost. If the transcript sounds
    unfinished ("tell me about the weather and..."), it keeps listening for
    the rest and joins the pieces."""
    recognizer.energy_threshold = max(recognizer.energy_threshold, MIN_ENERGY_THRESHOLD)  # dynamic adjustment can drift under the floor
    mic.start_recording()
    try:
        with mic.command_source() as source:
            try:
                audio = recognizer.listen(source, timeout=COMMAND_TIMEOUT, phrase_time_limit=PHRASE_TIME_LIMIT)
            except sr.WaitTimeoutError:
                print("listen: heard no speech before the timeout")
                return None, "no_speech"
            display.set_state("think")
            text, problem = transcribe(recognizer, audio)
            if text is None:
                return None, problem

            for _ in range(MAX_CONTINUATIONS):
                if not sounds_unfinished(text):
                    break
                print(f"listen: {text!r} sounds unfinished, waiting for the rest")
                display.set_state("idle")
                try:
                    audio = recognizer.listen(source, timeout=CONTINUE_TIMEOUT, phrase_time_limit=PHRASE_TIME_LIMIT)
                except sr.WaitTimeoutError:
                    break  # they stopped there, go with what we have
                display.set_state("think")
                more, problem = transcribe(recognizer, audio)
                if more is None:
                    if problem == "offline":
                        return None, problem
                    break
                text = f"{text} {more}"
            display.set_state("think")
            return text, None
    finally:
        mic.pause()  # nothing to hear while waiting on Gemini or while Solu talks


def transcribe(recognizer, audio):
    """Google speech-to-text. Returns (text, None) or (None, "unclear" / "offline")."""
    try:
        return recognizer.recognize_google(audio), None
    except sr.UnknownValueError:
        print("listen: heard audio but could not make out words")
        return None, "unclear"
    except sr.RequestError as e:
        print(f"listen: speech service error: {e}")
        return None, "offline"
    except Exception as e:
        print(f"listen: speech service failed: {e!r}")
        return None, "offline"


def speak_reply(display, text):
    """Speaks a reply. Returns True if it played to the end, False if the
    user tapped to cut it off or no speech could be generated."""
    display.set_state("speak")
    process = tts.start_speaking(text)
    if process is None:
        apologize(display, "offline")
        return False

    display.active_speech_process = process
    try:
        while process.poll() is None and display.current_state == "speak":
            time.sleep(0.05)
    finally:
        tts.stop_speaking(process)
        display.active_speech_process = None
    return display.current_state == "speak"  # a tap switches it to sleep


def apologize(display, problem):
    if problem == "offline":
        phrase = OFFLINE_RESPONSE
    elif problem == "brain":
        phrase = BRAIN_RESPONSE
    else:
        phrase = random.choice(ERROR_RESPONSES)
    display.set_state("error")
    tts.speak(phrase)
    display.set_state("sleep")

# ------------------------------------------------------------------
# reminder thread
# ------------------------------------------------------------------

def reminder_loop(display):
    """Checks for due reminders and rings them one at a time."""
    last_cleanup = 0.0
    while True:
        if time.time() - last_cleanup > 3600:
            reminders.clear_old_reminders()
            last_cleanup = time.time()

        due = reminders.check_due_reminders()
        if due:
            ring_alarm(display, due[0])
            continue  # check right away in case another one is due too
        time.sleep(REMINDER_POLL_SECONDS)


def ring_alarm(display, reminder):
    """Waits until Solu is at rest AND someone is nearby, so it never alarms
    into an empty room or over a conversation. Then rings until dismissed by
    a tap, "hey solu stop", or ALARM_TIMEOUT_SECONDS passing."""
    while not (GPIO.input(PIR_PIN) and display.try_start_alarm(reminder)):
        time.sleep(0.5)
    print(f"alarm: {reminder['message']!r}")

    alarm = None
    started = time.time()
    try:
        while display.reminder_panel_visible:
            if time.time() - started > ALARM_TIMEOUT_SECONDS and display.current_state == "alarm":
                print("alarm: nobody dismissed it, stopping after timeout")
                display.dismiss_reminder()
                break
            if display.current_state == "alarm":
                if alarm is None or alarm.poll() is not None:
                    alarm = tts.start_alarm_sound(ALARM_SOUND)  # loops the clip
            elif alarm is not None:
                tts.stop_alarm_sound(alarm)  # muted while listening for "stop"
                alarm = None
            time.sleep(0.1)
    finally:
        tts.stop_alarm_sound(alarm)
    reminders.mark_completed(reminder["id"])

# ------------------------------------------------------------------

def start_guarded_thread(target, *args):
    """Runs target in a background thread. If it ever crashes, the whole
    program exits so systemd restarts Solu, instead of the screen staying
    up while Solu is secretly deaf."""
    def guard():
        try:
            target(*args)
        except BaseException:
            traceback.print_exc()
        print(f"FATAL: {target.__name__} stopped, exiting so systemd restarts Solu", flush=True)
        os._exit(1)
    threading.Thread(target=guard, name=target.__name__, daemon=True).start()


if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)
    display = Display()
    start_guarded_thread(voice_loop, display)
    start_guarded_thread(reminder_loop, display)
    threading.Thread(target=tts.prepare_phrases, args=(ALL_PHRASES,), daemon=True).start()
    try:
        display.run()
    finally:
        GPIO.cleanup()
