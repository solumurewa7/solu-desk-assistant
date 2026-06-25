from gtts import gTTS
import subprocess
import os
import sys

AUDIO_DEVICE = "hw:0,0"


def speak(text):
    """Blocking speech playback, used for short responses like error apologies."""
    temp_filename = "temp_speech.mp3"

    try:
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(temp_filename)
        subprocess.run(["mpg123", "-a", AUDIO_DEVICE, temp_filename])
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


def start_speaking(text):
    """Non-blocking speech playback. Returns (process, temp_filename) so
    it can be interrupted (e.g. tapping the orb) and cleaned up via stop_speaking()."""
    temp_filename = f"temp_speech_{os.getpid()}_{id(text)}.mp3"
    tts = gTTS(text=text, lang="en", tld="com", slow=False)
    tts.save(temp_filename)
    process = subprocess.Popen(["mpg123", "-a", AUDIO_DEVICE, temp_filename])
    return process, temp_filename


def stop_speaking(process, temp_filename):
    """Terminates a running speech process (if still active) and removes its temp file."""
    if process is not None and process.poll() is None:
        process.terminate()
    if temp_filename and os.path.exists(temp_filename):
        os.remove(temp_filename)


def play_sound(filepath):
    """Blocking playback, for sounds where waiting for it to finish is fine (e.g. the startup chime)."""
    subprocess.run(["mpg123", "-a", AUDIO_DEVICE, filepath])


def start_alarm_sound(filepath):
    """Non-blocking playback, returns the live process handle so it can be
    interrupted instantly via stop_alarm_sound() rather than waiting for the clip to finish."""
    return subprocess.Popen(["mpg123", "-a", AUDIO_DEVICE, filepath])


def stop_alarm_sound(process):
    """Terminates a running alarm sound process. Safe to call even if it already finished."""
    if process is not None and process.poll() is None:
        process.terminate()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text_to_speak = " ".join(sys.argv[1:])
        speak(text_to_speak)
    else:
        print("Usage: python3 tts.py <text to speak>")