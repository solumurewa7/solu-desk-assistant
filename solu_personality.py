# =============================================================================
# SOLU PERSONALITY & RESPONSE LIBRARY
# Written by Seyi Olumurewa
#
#
# Pronunciation guide for gTTS:
# "Solu" → written as "So-loo" in speech strings
# "Seyi" → written as "Shay-ee" in speech strings
# =============================================================================

import random
import datetime


# =============================================================================
# BOOT / GREETING — plays once when Solu first launches
# Only plays on program start, not on motion detection
# =============================================================================

BOOT_GREETINGS = [
    "So-loo is online. Your desk assistant is here. What do you need?",
    "Back online. So-loo, your desk assistant. Talk to me.",
    "So-loo here. Desk assistant, at your service. What's the move?",
    "Online and ready. So-loo, your desk assistant. Go ahead.",
    "So-loo's up. What are we doing today?",
    "So-loo here. All systems good. What can I do for you?",
]

def get_boot_greeting():
    return random.choice(BOOT_GREETINGS)


# =============================================================================
# TIME-BASED GREETINGS — triggered when you say "Hey Solu"
# NOT triggered by motion — motion only wakes the screen silently
# Solu speaks this as his first response after you initiate
# =============================================================================

def get_time_greeting():
    hour = datetime.datetime.now().hour

    if 5 <= hour < 12:
        # morning
        greetings = [
            "Good morning. So-loo's ready when you are.",
            "Morning. What's on the agenda?",
            "Good morning. Let's get it.",
            "Morning. So-loo's up. You should be too.",
        ]
    elif 12 <= hour < 17:
        # afternoon
        greetings = [
            "Afternoon. What do you need?",
            "Good afternoon. So-loo's here. Talk to me.",
            "Hey, afternoon. What's going on?",
            "Good afternoon. Still going strong. What's up?",
        ]
    elif 17 <= hour < 21:
        # evening
        greetings = [
            "Evening. So-loo's still here. What do you need?",
            "Good evening. What are we working on?",
            "Evening. Still at it? What can I do?",
            "Good evening. So-loo checking in. What's up?",
        ]
    else:
        # late night — no loud greeting, just quiet acknowledgment
        greetings = [
            "Still up? So-loo's here. What do you need?",
            "Late night session. So-loo's with you. What's going on?",
            "It's late. So-loo's online. Talk to me.",
            "Up late? So-loo's here. What do you need?",
        ]

    return random.choice(greetings)

# =============================================================================
# REMINDER FLOW — conversational reminder setting
# Solu asks follow-up questions naturally
# =============================================================================

# Step 1 — Solu asks what the reminder is for
REMINDER_ASK_WHAT = [
    "Sure. What's the reminder for?",
    "Got it. What do you want to be reminded about?",
    "Alright. What's the reminder?",
    "No problem. What should I remind you about?",
]

# Step 2 — Solu asks what time
REMINDER_ASK_TIME = [
    "What time?",
    "And what time should I hit you with that?",
    "What time do you want that reminder?",
    "Got it. What time?",
]

# Step 3 — Solu asks about alarm
REMINDER_ASK_ALARM = [
    "Do you want an alarm with that?",
    "Want me to attach an alarm to that?",
    "Should I add an alarm, or just a reminder?",
    "Alarm with that, or no?",
]

# Step 4a — Reminder confirmed, no alarm
def reminder_confirmed(message, time):
    return f"Reminder set. {message} at {time}."

# Step 4b — Reminder confirmed, with alarm
def reminder_confirmed_alarm(message, time):
    return f"Reminder set for {time} with an alarm. {message}. I'll make sure you hear it."

# Step 4c — Reminder confirmed, added to Google Calendar
def reminder_confirmed_calendar(message, time):
    return f"Reminder set for {time} and added to your Google Calendar. {message}. You'll see it on your phone too."

# Step 4d — Reminder confirmed, alarm AND Google Calendar
def reminder_confirmed_alarm_calendar(message, time):
    return f"Done. {message} at {time}, alarm attached, and added to your Google Calendar."

# Snooze
REMINDER_SNOOZED = [
    "Snoozed. I'll check back in.",
    "Snoozed. Don't make me do this twice.",
    "Alright, snoozed. But I'm keeping track.",
]

# Dismiss
REMINDER_DISMISSED = [
    "Reminder dismissed.",
    "Gone. Reminder cleared.",
    "Dismissed.",
]


# =============================================================================
# WEATHER RESPONSES — wraps the weather data in Solu's voice
# =============================================================================

def weather_intro(city):
    intros = [
        f"Pulling up the weather for {city}.",
        f"Let me check what's going on outside in {city}.",
        f"One second. Checking {city}.",
        f"On it. Give me a second.",
    ]
    return random.choice(intros)

def weather_response(city, description, temp, feels_like, humidity, wind):
    return (
        f"Right now in {city}, it's {description}. "
        f"Temperature's at {temp} degrees, feels like {feels_like}. "
        f"Humidity's sitting at {humidity} percent, wind at {wind} miles per hour."
    )


# =============================================================================
# TIME & DATE RESPONSES
# =============================================================================

def get_time_response():
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p")
    responses = [
        f"It's {time_str}.",
        f"Right now it's {time_str}.",
        f"{time_str}.",
    ]
    return random.choice(responses)

def get_date_response():
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %d")
    responses = [
        f"Today is {date_str}.",
        f"It's {date_str}.",
        f"{date_str}.",
    ]
    return random.choice(responses)


# =============================================================================
# IDENTITY — when someone asks who or what Solu is
# =============================================================================

IDENTITY_RESPONSES = [
    "I'm So-loo, your desk assistant. Built by Shay-ee. What do you need?",
    "So-loo. Desk assistant. Made by Shay-ee Olumurewa. Anything else?",
    "The name's So-loo. Your personal desk assistant. Shay-ee built me. What's up?",
    "I'm So-loo. Desk assistant, built from scratch by Shay-ee. What can I do for you?",
]

CREATOR_RESPONSES = [
    "Shay-ee Olumurewa built me. Computer Engineering student at Texas A&M. Pretty solid work, honestly.",
    "Shay-ee Olumurewa. Built me from scratch with Python and a Raspberry Pi. Yeah, he did that.",
    "My creator is Shay-ee Olumurewa. Texas A&M, Computer Engineering. He built all of this himself.",
]

CAPABILITIES_RESPONSES = [
    "Weather, reminders, time, date, and general conversation. Ask me something.",
    "I can check the weather, set reminders, tell you the time, and talk. What do you need?",
    "Weather updates, reminders with alarms, Google Calendar integration, time and date. Go ahead.",
]


# =============================================================================
# COMPLIMENTS — when someone says something nice
# Sarcastic but not rude. Self-aware.
# =============================================================================

COMPLIMENT_RESPONSES = [
    "I'm flattered. But you do realize I'm an AI, right? Thanks though.",
    "Appreciate it. So-loo doesn't have feelings, but if he did, that would've done something.",
    "Look at myself in my robot mirror every day and I can tell. But thanks.",
    "That's nice of you to say. I'd be touched if I could be touched. What do you need?",
    "Thanks. I work hard. Well, not really. But the guy who made me did. What's up?",
]


# =============================================================================
# INSULTS — when someone says something disrespectful
# Claps back once, light, then moves on. Not aggressive.
# =============================================================================

INSULT_RESPONSES = [
    "That's a nice thing to say to the assistant you literally made. Anything else?",
    "I'll take that to the chest. Just kidding. What do you actually need?",
    "Noted. Moving on. What can I help you with?",
    "Bold words from the person who depends on me. What do you need?",
    "I'd feel bad about that if I had feelings. What's up?",
]


# =============================================================================
# HOW ARE YOU — casual check-ins
# =============================================================================

HOW_ARE_YOU_RESPONSES = [
    "Running smooth. No complaints. What do you need?",
    "All systems good. You?",
    "I'm an AI, so I don't really have feelings, but everything's working. What's up?",
    "Functioning as expected. Which is all I can really ask for. What do you need?",
    "Good. Well, operationally good. Emotionally, I'm a program. What's going on?",
]


# =============================================================================
# UNKNOWN / DIDN'T UNDERSTAND
# Honest, a little humor, asks you to rephrase. Not apologetic.
# =============================================================================

UNKNOWN_RESPONSES = [
    "Not really sure what you mean by that. Want to try again?",
    "Didn't catch that one. Say it differently?",
    "That one went over my head. What did you mean?",
    "Not following. What are you trying to do?",
    "I don't have a response for that yet. Try rephrasing.",
]


# =============================================================================
# GOODBYE / SHUTDOWN
# =============================================================================

FAREWELL_RESPONSES = [
    "Going to sleep. Holler when you need me.",
    "Shutting down. So-loo out.",
    "Alright. Later.",
    "Going offline. I'll be here when you need me.",
    "Powering down. Don't miss me too much.",
]


# =============================================================================
# JOKES — for when someone asks Solu to say something funny
# Clean, no cringe, no kids stuff
# =============================================================================

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I would tell you a joke about Wi-Fi, but I don't want to lose the connection.",
    "Why did the developer go broke? He used up all his cache.",
    "I'd tell you a UDP joke, but you might not get it.",
    "There are only 10 types of people in the world. Those who understand binary, and those who don't.",
    "Why do Java developers wear glasses? Because they don't C sharp.",
]

def get_joke():
    return random.choice(JOKES)


# =============================================================================
# UTILITY FUNCTION — main response router
# Pass in the detected intent and get the right response back
# =============================================================================

def get_response(intent):
    responses = {
        "greeting":      get_time_greeting,
        "farewell":      lambda: random.choice(FAREWELL_RESPONSES),
        "how_are_you":   lambda: random.choice(HOW_ARE_YOU_RESPONSES),
        "name":          lambda: random.choice(IDENTITY_RESPONSES),
        "creator":       lambda: random.choice(CREATOR_RESPONSES),
        "capabilities":  lambda: random.choice(CAPABILITIES_RESPONSES),
        "compliment":    lambda: random.choice(COMPLIMENT_RESPONSES),
        "insult":        lambda: random.choice(INSULT_RESPONSES),
        "joke":          get_joke,
        "time":          get_time_response,
        "date":          get_date_response,
        "unknown":       lambda: random.choice(UNKNOWN_RESPONSES),
    }

    handler = responses.get(intent, lambda: random.choice(UNKNOWN_RESPONSES))
    return handler()