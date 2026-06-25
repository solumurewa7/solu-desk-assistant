from gtts import gTTS
import subprocess
import os
import sys

AUDIO_DEVICE = "hw:0,0"


def speak(text):
    temp_filename = "temp_speech.mp3"

    try:
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(temp_filename)
        subprocess.run(["mpg123", "-a", AUDIO_DEVICE, temp_filename])
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


def play_sound(filepath):
    """Blocking playback, used for things like the startup chime where
    waiting for it to finish before continuing is fine/expected."""
    subprocess.run(["mpg123", "-a", AUDIO_DEVICE, filepath])


def start_alarm_sound(filepath):
    """
    Non-blocking alarm playback. Returns the live subprocess.Popen handle
    immediately, WITHOUT waiting for the sound to finish -- this is what
    makes it possible to actually interrupt the alarm mid-clip the moment
    someone dismisses it (tap or "stop" voice command), rather than being
    stuck waiting for whatever clip is currently playing to finish on its
    own, the way the old blocking play_sound() in a loop behaved.
    """
    return subprocess.Popen(["mpg123", "-a", AUDIO_DEVICE, filepath])


def stop_alarm_sound(process):
    """
    Immediately terminates a running alarm sound process. Safe to call
    even if the process has already finished on its own (terminate() is
    a no-op on an already-dead process, and poll() lets us check first to
    avoid any race-condition weirdness).
    """
    if process is not None and process.poll() is None:
        process.terminate()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text_to_speak = " ".join(sys.argv[1:])
        speak(text_to_speak)
    else:
        print("Usage: python3 tts.py <text to speak>")