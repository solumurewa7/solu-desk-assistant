# Solu Desk Assistant

A voice-activated physical desk assistant built from scratch using a Raspberry Pi 4 and Python. Solu responds to voice commands, delivers real-time weather updates, manages reminders, and runs on a 7-inch touchscreen display mounted on your desk.

> **Demo coming soon.**

---

## Features

- **Wake word detection** — say "Hey Solu" to activate
- **Voice recognition** — powered by Google Speech Recognition
- **Text-to-speech responses** — natural voice output via gTTS
- **Real-time weather** — live conditions pulled from OpenWeatherMap API
- **Smart reminders** — set reminders by voice with optional alarms and Google Calendar sync
- **Motion detection** — PIR sensor wakes the screen when you enter the room
- **Touchscreen display** — shows time, weather, and reminders on a 7-inch screen
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
| Anker Mini Speaker | 3.5mm audio output |

---

## Tech Stack

**Languages:** Python

**Libraries:** SpeechRecognition, gTTS, pygame, tkinter, Pillow, requests, RPi.GPIO

**APIs:** OpenWeatherMap, Gemini API, Google Calendar API

**Hardware:** Raspberry Pi 4, PIR motion sensor, 7-inch DSI display

**Tools:** Git, GitHub, VS Code

---

## How It Works

Solu runs as a continuous Python process on the Raspberry Pi. A PIR motion sensor detects when someone enters the room and wakes the touchscreen display. From there, Solu listens for the wake word "Hey Solu" using Google Speech Recognition. Once activated, voice commands are processed and routed to the appropriate function: weather retrieval, reminder management, time and date, or open-ended conversation via the Gemini API. Responses are spoken back using gTTS and played through the speaker.

All reminder data is stored locally in a JSON file. Reminders flagged for Google Calendar are synced automatically via the Google Calendar API.

---

## Project Status

Currently in development. Hardware setup and core feature building in progress.

**Completed:**
- Personality and response library
- Weather API integration
- Voice recognition and TTS pipeline
- Project architecture and planning

**In progress:**
- Raspberry Pi hardware setup
- Wake word listener loop
- Reminder system
- Touchscreen UI with tkinter

---

## Author

**Oluwaseyi (Seyi) Olumurewa**
Computer Engineering, Texas A&M University

[LinkedIn](https://www.linkedin.com/in/oluwaseyi-olumurewa-61baaa395) | [GitHub](https://github.com/solumurewa7)