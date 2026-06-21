import subprocess
import os
import sys

AUDIO_DEVICE = "hw:0,0"
VOICE_MODEL_PATH = "assets/voice/en_US-hfc_male-medium.onnx"

def speak(text): # Converts text to speech and plays it through the speaker.
    temp_filename = "temp_speech.wav"

    try:
        subprocess.run(["piper", "--model", VOICE_MODEL_PATH, "--output_file", temp_filename],input=text,text=True)
        subprocess.run(["aplay", "-D", AUDIO_DEVICE, temp_filename])
        
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text_to_speak = " ".join(sys.argv[1:])
        speak(text_to_speak)
    else:
        print("Usage: python3 tts.py <text to speak>")