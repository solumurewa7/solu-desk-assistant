from gtts import gTTS
from pydub import AudioSegment
import subprocess
import os
import sys

AUDIO_DEVICE = "hw:0,0"

def speak(text):
    temp_filename = "temp_speech.mp3"
    sped_up_filename = "temp_speech_fast.mp3"

    try:
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(temp_filename)
        audio = AudioSegment.from_mp3(temp_filename)
        faster = audio.speedup(playback_speed=1.10)
        faster.export(sped_up_filename, format="mp3")

        subprocess.run(["mpg123", "-a", AUDIO_DEVICE, sped_up_filename])
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        if os.path.exists(sped_up_filename):
            os.remove(sped_up_filename)

def play_sound(filepath):
    subprocess.run(["mpg123", "-a", AUDIO_DEVICE, filepath])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text_to_speak = " ".join(sys.argv[1:])
        speak(text_to_speak)
    else:
        print("Usage: python3 tts.py <text to speak>")