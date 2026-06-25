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
from tts import speak, play_sound, start_alarm_sound, stop_alarm_sound, start_speaking, stop_speaking
import gemini
import reminders
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN)

ERROR_RESPONSES = [
    "Sorry, I didn't catch that.",
    "Hmm, I'm not sure what you said.",
    "Could you try that again?",
    "I didn't quite get that one.",
]

model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])

# ------------------------------------------------------------------

def listen_for_wake_word(display):
    """Listens for the wake word forever. On detection, either handles
    an active alarm (listens for a stop phrase) or starts a normal
    conversation (listens for a command, asks Gemini, speaks the reply,
    loops on follow-ups)."""
    global model

    # calibrate ambient noise once at startup, with a visual cue (think
    # state) so the user knows not to talk yet
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
        except OSError:
            # mic stream occasionally overflows on this hardware -- known,
            # harmless (only affects wake-word listening, never the actual
            # command capture), just reopen and keep going
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

            # an alarm is currently going off -- skip the normal
            # conversation flow, just listen for a stop phrase
            if display.current_state == "alarm":
                display.set_state("idle")
                stream.stop_stream()
                stream.close()

                command_text = listen_for_command(display, recognizer)

                if command_text is not None and ("stop" in command_text.lower() or "alarm" in command_text.lower()):
                    display.dismiss_reminder()
                else:
                    display.set_state("alarm")

                # recreate the model to clear its internal rolling buffer,
                # otherwise leftover recent speech can cause a false
                # wake-word retrigger right after this
                model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])
                stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
                continue

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
                    display.set_state("sleep")
                    break

                response, follow_up = gemini.ask_gemini(command_text, history)
                if response == None:
                    display.set_state("error")
                    speak(random.choice(ERROR_RESPONSES))
                    display.set_state("sleep")
                    break

                history.append({"role": "user", "parts": [{"text": command_text}]})
                history.append({"role": "model", "parts": [{"text": response}]})

                display.set_state("speak")
                process, temp_filename = start_speaking(response)
                display.active_speech_process = process

                # wait for speech to finish naturally OR be interrupted by
                # a tap (display._on_tap terminates the process and sets
                # state to sleep directly, which is what ends this loop early)
                was_interrupted = False
                while process.poll() is None and display.current_state == "speak":
                    time.sleep(0.1)
                if display.current_state == "sleep":
                    was_interrupted = True

                stop_speaking(process, temp_filename)
                display.active_speech_process = None

                # a tap to stop speech always ends the conversation, even
                # if this response would otherwise have asked a follow-up
                if was_interrupted:
                    break

                if follow_up:
                    display.set_state("idle")
                    continue
                else:
                    display.set_state("sleep")
                    break

            model = Model(wakeword_model_paths=["assets/wakeword/hey_soh_loo.onnx"])
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, input_device_index=1, frames_per_buffer=3528)
            continue


# ------------------------------------------------------------------

def listen_for_command(display, recognizer):
    """Listens for one spoken command, returns the transcribed text or None on timeout/failure."""
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
    """Checks for due reminders every 10 seconds. Only fires one once the
    orb is at rest AND motion is detected nearby, so it never alarms into
    an empty room. Plays the alarm sound on a loop until dismissed
    (screen tap or the wake-word stop-phrase path above)."""
    reminders.clear_old_reminders()
    while True:
        if display.current_state == "sleep":
            due = reminders.check_due_reminders()
            for reminder in due:
                while display.current_state != "sleep":
                    time.sleep(1)
                while GPIO.input(17) == 0:
                    time.sleep(1)

                display.show_reminder(reminder)
                display.set_state("alarm")

                alarm_process = start_alarm_sound("sounds/alarm.mp3")
                while display.reminder_data is not None:
                    if alarm_process.poll() is not None:
                        alarm_process = start_alarm_sound("sounds/alarm.mp3")
                    time.sleep(0.8)

                stop_alarm_sound(alarm_process)
                reminders.mark_completed(reminder["id"])
        time.sleep(10)


# ------------------------------------------------------------------
if __name__ == "__main__":
    display = Display()
    t = threading.Thread(target=listen_for_wake_word, args=(display,), daemon=True)
    t.start()
    t2 = threading.Thread(target=check_reminders_loop, args=(display,), daemon=True)
    t2.start()
    display.run()