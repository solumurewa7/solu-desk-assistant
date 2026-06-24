from gtts import gTTS
import subprocess
import os
import sys

AUDIO_DEVICE = "hw:0,0"

def speak(text): # Converts text to speech and plays it through the speaker.
    temp_filename = "temp_speech.mp3"

    try:
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(temp_filename)
        subprocess.run(["mpg123", "-a", AUDIO_DEVICE, temp_filename])
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

def play_sound(filepath):
    subprocess.run(["mpg123", "-a", AUDIO_DEVICE, filepath])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text_to_speak = " ".join(sys.argv[1:])
        speak(text_to_speak)
    else:
        print("Usage: python3 tts.py <text to speak>")