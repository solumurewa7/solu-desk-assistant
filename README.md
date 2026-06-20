# Solu Desk Assistant

A voice-activated physical desk assistant built from scratch using a Raspberry Pi 4 and Python. Solu responds to voice commands, delivers real-time weather updates, manages reminders, and runs on a 7-inch touchscreen display mounted on your desk, with a custom animated interface built entirely in code.

> **Demo coming soon.**

---

## Features

- **Local wake word detection** — say "Hey Solu" to activate, using a custom-trained openWakeWord model running entirely on-device
- **Voice recognition** — powered by Google Speech Recognition for command transcription
- **Text-to-speech responses** — natural voice output via gTTS
- **Real-time weather** — live conditions pulled from OpenWeatherMap API
- **Live web search** — Gemini autonomously searches the web for current information when a question requires it
- **Smart reminders** — set reminders by voice, every reminder alerts automatically, with optional Google Calendar sync
- **Motion detection** — PIR sensor wakes the screen when you enter the room
- **Animated touchscreen display** — a custom-rendered glowing orb interface with smooth color transitions, breathing animation, and touch-reactive feedback, built entirely with Pillow and tkinter
- **AI-powered conversation** — Gemini API handles open-ended questions and natural dialogue
- **Personality** — witty, confident, and knows when to be straight

---

## Hardware

| Component | Details |
|-----------|---------|
| CanaKit Raspberry Pi 4 | 4GB RAM, 32GB SD card |
| Hosyond 7" DSI Touchscreen | 800x480, capacitive touch |
| HC-SR501 PIR Motion Sensor | GPIO-connected |
| USB Microphone | Plug and play |
| Anker Speaker | USB power, 3.5mm audio |

---

## Tech Stack

**Languages:** Python

**Libraries:** SpeechRecognition, openWakeWord, gTTS, tkinter, Pillow, requests, RPi.GPIO

**APIs:** OpenWeatherMap, Gemini API (with Google Search grounding), Google Calendar API

**Hardware:** Raspberry Pi 4, PIR motion sensor, 7-inch DSI display

**Tools:** Git, GitHub, VS Code, Google Colab (for wake word model training)

---

## How It Works

Solu runs as a continuous Python process on the Raspberry Pi. A PIR motion sensor detects when someone enters the room and wakes the touchscreen display silently. From there, a custom-trained openWakeWord model continuously listens for the phrase "Hey Solu" entirely on-device, with no audio sent anywhere until the wake word is actually detected. Once triggered, the following command is transcribed using Google Speech Recognition and routed to the appropriate handler: weather retrieval, reminder management, time and date, live web search, or open-ended conversation via the Gemini API. Responses are spoken back using gTTS and played through the speaker.

The display itself is a fully custom-rendered interface: a glowing orb generated programmatically with gradient and glow effects, animated with a continuous breathing pulse, smooth color crossfades between emotional states, and a responsive touch-reactive pulse. A secondary panel reveals the time, date, and weather on tap, and slides into view automatically when a reminder is due.

All reminder data is stored locally in a JSON file. Reminders flagged for Google Calendar are synced automatically via the Google Calendar API.

---

## Project Status

Currently in development. Core architecture and display are complete; voice loop integration in progress.

**Completed:**
- Personality and response library
- Weather API integration with live Gemini-powered Google Search grounding
- Reminder system with Google Calendar sync
- Custom animated touchscreen UI (glowing orb, state transitions, touch interaction, reminder panel)
- PIR motion sensor integration
- Project architecture and planning

**In progress:**
- Custom wake word model training (openWakeWord)
- Wake word listener loop and command handler (main.py / brain.py)
- End-to-end voice command integration

---

## Author

**Oluwaseyi (Seyi) Olumurewa**
Computer Engineering, Texas A&M University

[LinkedIn](https://www.linkedin.com/in/oluwaseyi-olumurewa-61baaa395) | [GitHub](https://github.com/solumurewa7)