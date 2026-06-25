# Solu Desk Assistant

A voice-activated physical desk assistant built from scratch using a Raspberry Pi 4 and Python. Solu responds to voice commands, holds real multi-turn conversations, delivers real-time weather updates, manages reminders with Google Calendar sync, and runs on a 7-inch touchscreen display with a custom animated interface built entirely in Pygame.

> **Demo coming soon.**

---

## Features

- **Local wake word detection** — say "Hey Solu" to activate, using a custom-trained openWakeWord model running entirely on-device
- **Voice recognition** — Google Speech Recognition for command transcription, with automatic ambient noise calibration on startup
- **Multi-turn conversation** — Solu remembers context within a conversation and knows when to ask a follow-up question versus when to end the interaction
- **Text-to-speech responses** — natural voice output via gTTS
- **Real-time weather and live web search** — Gemini answers using OpenWeatherMap data and autonomous Google Search grounding when a question needs current information
- **Smart reminders** — set reminders by voice using natural, relative phrasing ("remind me in an hour," "tomorrow at 3pm"), with optional Google Calendar sync
- **Motion-gated alarms** — reminders only alarm once someone is actually detected nearby (PIR sensor), and can be dismissed by tapping the screen or saying "hey Solu, stop the alarm"
- **Day/night aware display** — the orb dims to fully invisible at night and returns to normal during the day
- **Animated touchscreen display** — a custom-rendered glowing orb with smooth color transitions, breathing animation, touch-reactive feedback, an orbiting particle system, and a starfield background, built entirely in Pygame
- **AI-powered conversation** — Gemini API handles open-ended questions, reminders, and natural dialogue, aware of the real current time and location
- **Personality** — witty, confident, and knows when to be straight

---

## Hardware

| Component | Details |
|-----------|---------|
| CanaKit Raspberry Pi 4 | 4GB RAM, 32GB SD card |
| Hosyond 7" DSI Touchscreen | 800x480, capacitive touch |
| HC-SR501 PIR Motion Sensor | GPIO-connected |
| USB Microphone | Plug and play |
| Anker Speaker | 3.5mm audio |

---

## Tech Stack

**Languages:** Python

**Libraries:** SpeechRecognition, openWakeWord, gTTS, Pygame, PyAudio, NumPy, SciPy, requests, RPi.GPIO

**APIs:** OpenWeatherMap, Gemini API (with Google Search grounding and function-style structured tags), Google Calendar API (OAuth2)

**Hardware:** Raspberry Pi 4, PIR motion sensor, 7-inch DSI display

**Tools:** Git, GitHub, VS Code, Google Colab (for wake word model training)

---

## How It Works

Solu runs as a continuous Python process on the Raspberry Pi, with three background threads: the wake word listener, the reminder checker, and the Pygame display loop.

A custom-trained openWakeWord model continuously listens for "Hey Solu" entirely on-device, with no audio sent anywhere until the wake word is detected. Once triggered, the following command is transcribed using Google Speech Recognition and sent to the Gemini API along with the running conversation history. Gemini's response includes two hidden control tags: one telling the program whether to keep listening for a follow-up or end the conversation, and one (only when relevant) containing a fully-parsed reminder to create, including relative-time math ("in an hour," "tomorrow") already converted to a real date and time. Responses are spoken aloud using gTTS.

Reminders are stored locally in a JSON file and checked every 10 seconds. A due reminder only triggers once the orb is at rest and the PIR sensor detects someone nearby, so Solu never alarms into an empty room. The alarm sound loops until dismissed by tapping the screen or saying "hey Solu, stop the alarm," both of which stop it within a fraction of a second. Reminders flagged for the calendar are synced automatically via the Google Calendar API.

The display is fully custom-rendered in Pygame: a sharp-edged gradient orb with independent orbiting particles (each on its own randomized orbital plane, like planets around a sun), a twinkling starfield background, smooth color crossfades between emotional states, a breathing animation, and touch-reactive feedback. The orb dims to fully invisible between 11pm and 7am, and a tap reveals the time, date, and weather.

---

## Project Status

Core architecture, voice loop, conversation system, reminders, calendar sync, and display are complete and working end to end.

**Completed:**
- Custom wake word model (openWakeWord), trained and tuned for real-world reliability
- Full wake word → listen → Gemini → speak conversation loop, with multi-turn follow-up support and real conversation history
- Natural-language reminder creation (relative time parsing, message/time/calendar all extracted from a single Gemini response)
- Motion-gated reminder alarms with instant tap or voice dismissal
- Google Calendar sync
- Weather and live web search integration, aware of real location and time
- Custom animated touchscreen UI in Pygame (orb, orbiting particles, starfield, state transitions, info panel, reminder panel)
- PIR motion sensor integration
- Day/night aware display dimming

**Possible future work:**
- Higher-quality local text-to-speech and speech-to-text (tested Piper and Vosk; both underperformed the current cloud-based setup on this hardware, may revisit on different hardware)
- Persistent conversation memory across separate wake-word sessions (currently scoped to one conversation only)

---

## Author

**Oluwaseyi (Seyi) Olumurewa**
Computer Engineering, Texas A&M University

[LinkedIn](https://www.linkedin.com/in/oluwaseyi-olumurewa-61baaa395) | [GitHub](https://github.com/solumurewa7)