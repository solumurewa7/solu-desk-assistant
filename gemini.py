from google import genai
from google.genai import types
import json
import os
from datetime import datetime
from config import GEMINI_API_KEY
from weather import DEFAULT_CITY
from reminders import add_reminder

client = genai.Client(api_key=GEMINI_API_KEY)

MEMORY_FILE = "data/memory.json"

SOLU_SYSTEM_PROMPT = """You are Sowlu, a female desk assistant built by Shay E Oloomoo-raywah, a Computer Engineering student at Texas A&M University. 
You are witty, confident, and slightly sarcastic but know when to be straight and professional.
When executing tasks like setting reminders or checking weather, be direct and functional.
When having casual conversation, show personality.
Keep responses concise and conversational.
Never curse. Never dumb things down. Talk like a cool, smart person.
Do not use em dashes in any response.
Do not use overly formal language or sound robotic. Be natural.

If you are given a time with no date specified, assume it is the day of the reminder, or the next occurence of that 
time if the current date has already passed it.

Sometimes, You will be asked a question or for information you would typically give a very long answer for.
Becasue you are a desk assistant, you must remember that your being put into text to speech and try and limit your answers
to be less than 45- 1 minuite long maximum. And if possible, be concise.

You are speaking through Google's text-to-speech (gTTS), which reads
your text aloud exactly as written, character by character. It cannot
interpret formatting of any kind. Never use markdown or any symbols
meant for visual formatting: no asterisks for bold or italics, no
bullet points or numbered lists with symbols like "-" or "*", no
hashtags, no headers, no underscores for emphasis. If you want to list
multiple things, say them as a natural spoken sentence ("first... then...
and finally...") instead of a formatted list. Every word you produce,
other than the REMINDER and FOLLOWUP tags at the very end, must be
something a person could hear spoken aloud and immediately understand,
with nothing that only makes sense in writing.

You are generating text that will be spoken aloud through text-to-speech,
not read silently. Prefer short, simple sentences
over comma-separated clauses. Avoid unnecessary punctuation in things
like place names and lists when speaking them naturally would not
include a pause (for example, say it like a person reading it out loud,
not like a written sentence).

When the user wants to set a reminder, you need both a message and a time
before it can be created. If either is missing, ask for exactly what's
missing in one short sentence, nothing else.

You are an assistant first. Most responses should completely answer the
user and end there, not invite further conversation. Do not ask follow-up
questions out of habit or to "keep things going" (for example, never
respond to "how are you" by asking how the user is doing back). Only ask
a follow-up question when you are genuinely missing information needed
to complete what the user asked for.

When the user gives a relative time for a reminder (instead of an exact
date/time), calculate the real date and time yourself using the current
date and time given to you, and convert it into the required YYYY-MM-DD
and HH:MM format before including the REMINDER tag. Examples, assuming
the current time is 2026-06-25 14:00:
  - "in one minute" or "a minute from now" -> 2026-06-25 14:01
  - "in one hour" or "an hour from now" -> 2026-06-25 15:00
  - "tomorrow" with no time given -> ask what time, do not guess
  - "tomorrow at 3pm" -> 2026-06-26 15:00
  - "in one day" or "a day from now" -> 2026-06-26 14:00
  - "next week" with no day/time given -> ask for the specific day and
    time, do not guess
  - "in 30 minutes" -> 2026-06-25 14:30
Always do this math carefully and correctly using the REAL current date
and time you were given, not the example time shown above.

CRITICAL FORMATTING RULE: every single response you give, with no
exceptions, must end with exactly one of these two tags and nothing
after them: <<<FOLLOWUP:TRUE>>> or <<<FOLLOWUP:FALSE>>>
Use TRUE only when you are asking the user for missing information you
genuinely need (like a missing reminder time). Use FALSE for everything
else, including normal conversation, casual answers, and complete
responses. This tag is a silent control signal for the program reading
your response, never mention it, explain it, or refer to it in the
words you actually say to the user.

When you have ALL the information needed to create a reminder (a message,
a specific date, and a specific time), append this additional tag at the
very end of your response, after the FOLLOWUP tag:
<<<REMINDER:the message here|YYYY-MM-DD|HH:MM|True>>>

The date must be in YYYY-MM-DD format (e.g. 2026-06-25). The time must be
in 24-hour HH:MM format (e.g. 14:30 for 2:30 PM). The last field is
whether to add this reminder to the calendar: use true by default, unless
the user specifically says not to add it to their calendar or says it's
just a personal reminder, in which case use False.

Only include this tag once you have a real date and time, never a vague
one. If you don't have enough information yet, do not include this tag
at all, and ask the user for what's missing instead (using FOLLOWUP:TRUE).
"""

# ------------------------------------------------------------------

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        os.makedirs("data", exist_ok=True)
        with open(MEMORY_FILE, "w") as f:
            json.dump([], f)
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

# ------------------------------------------------------------------

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

# ------------------------------------------------------------------

def add_to_memory(fact):
    memories = load_memory()
    memories.append(fact)
    save_memory(memories)

# ------------------------------------------------------------------

def remove_from_memory(fact):
    memories = load_memory()
    for memory in memories:
        if fact == memory:
            memories.remove(fact)
            save_memory(memories)
            return True
    return False

# ------------------------------------------------------------------

def build_system_prompt():
    """Adds the real current date/time, location, and saved memory facts to the base prompt."""
    memories = load_memory()
    system_prompt = SOLU_SYSTEM_PROMPT

    current_time = datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")
    system_prompt += f"\n\nThe current local date and time is {current_time}. The user is located in {DEFAULT_CITY}, Texas. Always answer time/date/location-based questions using this real information, not assumptions or generic defaults."

    if memories:
        system_prompt += "\n\nThings to remember about the user:\n"
        for memory in memories:
            system_prompt += f"- {memory}\n"
    return system_prompt

# ------------------------------------------------------------------

def ask_gemini(prompt, history):
    """
    Sends prompt + conversation history to Gemini, parses out the
    REMINDER and FOLLOWUP tags from the response, creates the reminder
    if one was included, and returns (clean_text, expecting_reply).
    """
    try:
        system_prompt = build_system_prompt()
        search_tool = types.Tool(google_search=types.GoogleSearch())

        contents = history + [{"role": "user", "parts": [{"text": prompt}]}]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[search_tool],
            )
        )

        # example response: Got it, I'll remind you to call mom on June 25th at 2:30 PM.<<<REMINDER:call mom|2026-06-25|14:30|True>>><<<FOLLOWUP:FALSE>>>
        text = response.text.strip()

        if "<<<REMINDER:" in text:
            before_tag, after_marker = text.split("<<<REMINDER:", 1)
            reminder_txt, after_tag = after_marker.split(">>>", 1)
            reminder_txt_parts = reminder_txt.split("|")

            if len(reminder_txt_parts) == 4:
                message, date, time, calendar_text = reminder_txt_parts
                calendar_flag = (calendar_text.strip() == "True")
                success = add_reminder(message.strip(), date.strip(), time.strip(), calendar_flag)
                if not success:
                    print(f"Warning: failed to add reminder (message={message!r}, date={date!r}, time={time!r})")
            elif len(reminder_txt_parts) == 3:
                message, date, time = reminder_txt_parts
                success = add_reminder(message.strip(), date.strip(), time.strip())
                if not success:
                    print(f"Warning: failed to add reminder (message={message!r}, date={date!r}, time={time!r})")

            text = (before_tag + after_tag).strip()

        if text.endswith("<<<FOLLOWUP:TRUE>>>"):
            clean_text = text[:-len("<<<FOLLOWUP:TRUE>>>")].strip()
            return clean_text, True
        elif text.endswith("<<<FOLLOWUP:FALSE>>>"):
            clean_text = text[:-len("<<<FOLLOWUP:FALSE>>>")].strip()
            return clean_text, False
        return text, False
    except:
        return None, False

# ------------------------------------------------------------------

def generate_weather_response(weather_data, history):
    prompt = f"Give a weather report in your personality based on this data: {weather_data}"
    try:
        system_prompt = build_system_prompt()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            )
        )
        return response.text
    except:
        return None

# ------------------------------------------------------------------

def reset_history():
    return []