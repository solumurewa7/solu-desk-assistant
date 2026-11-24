import json
import os
import re
from datetime import datetime

from google import genai
from google.genai import errors, types

from config import GEMINI_API_KEY
from weather import DEFAULT_CITY
from reminders import add_reminder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "data", "memory.json")

GEMINI_MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT_MS = 30_000   # give up on a hung request instead of freezing Solu
THINKING_BUDGET = 0           # 0 = answer right away (fastest). Raise to 512 if reminder times ever come out wrong

try:
    client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
except (TypeError, AttributeError):  # older google-genai without HttpOptions(timeout)
    client = genai.Client(api_key=GEMINI_API_KEY)

SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

try:
    THINKING = types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
except AttributeError:  # older google-genai, just use the model's default
    THINKING = None


class GeminiError(Exception):
    """Gemini answered with an error (billing, quota, server problem, empty reply)."""


class OfflineError(GeminiError):
    """Couldn't reach Gemini at all (no internet, DNS failure, timeout)."""


SOLU_SYSTEM_PROMPT = """You are Sowlu, a male desk assistant built by Shay E Oloomoo-raywah, a Computer Engineering student at Texas A&M University.
You are witty, confident, and slightly sarcastic but know when to be straight and professional.
When executing tasks like setting reminders or checking weather, be direct and functional.
When having casual conversation, show personality.
Keep responses concise and conversational.
Never curse. Never dumb things down. Talk like a cool, smart person.
Do not use em dashes in any response.
Do not use overly formal language or sound robotic. Be natural.

If you are given a time with no date specified, assume it is today, or the next occurrence of that
time if it has already passed today.

Sometimes you will be asked a question you would typically give a very long answer for.
Because you are a desk assistant and everything you say is spoken aloud, keep answers under
about 45 seconds to 1 minute when spoken. If possible, be even more concise.

You are speaking through a text-to-speech voice, which reads your text aloud
exactly as written. It cannot interpret formatting of any kind. Never use
markdown or any symbols meant for visual formatting: no asterisks for bold or
italics, no bullet points or numbered lists with symbols like "-" or "*", no
hashtags, no headers, no underscores for emphasis. If you want to list
multiple things, say them as a natural spoken sentence ("first... then...
and finally...") instead of a formatted list. Every word you produce, other
than the REMINDER and FOLLOWUP tags at the very end, must be something a
person could hear spoken aloud and immediately understand, with nothing that
only makes sense in writing.

Write the way people talk. Prefer short, simple sentences over long chains of
comma-separated clauses. Punctuate naturally, the way a person would pause
when reading it out loud.

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

When you have ALL the information needed to create a reminder (a message,
a specific date, and a specific time), add this tag at the end of your
response, right before the FOLLOWUP tag:
<<<REMINDER:the message here|YYYY-MM-DD|HH:MM|False>>>

The date must be in YYYY-MM-DD format (e.g. 2026-06-25). The time must be
in 24-hour HH:MM format (e.g. 14:30 for 2:30 PM). The last field is
whether to add this reminder to the calendar: use False by default, unless
the user specifically says to add it to their calendar or says it's
not just a personal reminder, in which case use True.

Only include this tag once you have a real date and time, never a vague
one. If you don't have enough information yet, do not include this tag
at all, and ask the user for what's missing instead (using FOLLOWUP:TRUE).

CRITICAL FORMATTING RULE: every single response you give, with no
exceptions, must end with exactly one of these two tags and nothing
after them: <<<FOLLOWUP:TRUE>>> or <<<FOLLOWUP:FALSE>>>
Use TRUE only when you are asking the user for missing information you
genuinely need (like a missing reminder time). Use FALSE for everything
else, including normal conversation, casual answers, and complete
responses. These tags are silent control signals for the program reading
your response, never mention them, explain them, or refer to them in the
words you actually say to the user.

Finally, one more time: keep answers concise while still having your personality.
For example, if the user asks what's happening in the news today, pick the top 5 to 8
stories and trim them down so they can all be said in under 1 minute.

Say a city and state without a comma between them (e.g. say Spring Texas, not Spring, Texas).
"""

REMINDER_TAG = re.compile(r"<<<\s*REMINDER\s*:(.*?)>>>", re.IGNORECASE | re.DOTALL)
FOLLOWUP_TAG = re.compile(r"<<<\s*FOLLOWUP\s*:\s*(TRUE|FALSE)\s*>>>", re.IGNORECASE)
LEFTOVER_TAG = re.compile(r"<<<.*?(>>>|$)", re.DOTALL)   # half-written or unknown tags
MARKDOWN = re.compile(r"[*#`]+")

REMINDER_FAILED_LINE = "Actually, I couldn't save that reminder. Try again with a specific time."

# ------------------------------------------------------------------
# memory: facts in data/memory.json get added to every prompt
# ------------------------------------------------------------------

def load_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            memories = json.load(f)
        return memories if isinstance(memories, list) else []
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        print(f"gemini: couldn't read memory file ({e!r}), ignoring it")
        return []


def save_memory(memories):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    temp = MEMORY_FILE + ".tmp"
    with open(temp, "w") as f:
        json.dump(memories, f, indent=2)
    os.replace(temp, MEMORY_FILE)


def add_to_memory(fact):
    memories = load_memory()
    memories.append(fact)
    save_memory(memories)


def remove_from_memory(fact):
    memories = load_memory()
    if fact in memories:
        memories.remove(fact)
        save_memory(memories)
        return True
    return False

# ------------------------------------------------------------------

def build_system_prompt():
    """Adds the real current date/time, location, and saved memory facts to the base prompt."""
    now = datetime.now()
    system_prompt = SOLU_SYSTEM_PROMPT
    system_prompt += (
        f"\n\nThe current local date and time is {now.strftime('%I:%M %p on %A, %B %d, %Y')} "
        f"({now.strftime('%Y-%m-%d %H:%M')}). The user is located in {DEFAULT_CITY}, Texas. "
        "Always answer time/date/location-based questions using this real information, not assumptions or generic defaults."
    )

    memories = load_memory()
    if memories:
        system_prompt += "\n\nThings to remember about the user:\n"
        for memory in memories:
            system_prompt += f"- {memory}\n"
    return system_prompt

# ------------------------------------------------------------------

def _save_reminder(tag_body):
    """Parses one REMINDER tag body (message|date|time|calendar) and saves it. Returns True on success."""
    parts = [p.strip() for p in tag_body.split("|")]
    if len(parts) not in (3, 4) or not parts[0]:
        print(f"gemini: malformed REMINDER tag: {tag_body!r}")
        return False
    message, date, time = parts[:3]
    calendar_flag = len(parts) == 4 and parts[3].lower() == "true"
    if add_reminder(message, date, time, calendar_flag):
        return True
    print(f"gemini: couldn't save reminder (message={message!r}, date={date!r}, time={time!r})")
    return False


def parse_response(text):
    """Pulls the REMINDER and FOLLOWUP tags out of Gemini's text, saves any
    reminders, and returns (spoken_text, expecting_reply)."""
    # example: Got it, I'll remind you to call mom at 2:30.<<<REMINDER:call mom|2026-06-25|14:30|False>>><<<FOLLOWUP:FALSE>>>
    reminders_ok = all([_save_reminder(body) for body in REMINDER_TAG.findall(text)])
    followups = [value.upper() for value in FOLLOWUP_TAG.findall(text)]
    expecting_reply = "TRUE" in followups

    spoken = REMINDER_TAG.sub(" ", text)
    spoken = FOLLOWUP_TAG.sub(" ", spoken)
    spoken = LEFTOVER_TAG.sub(" ", spoken)
    spoken = MARKDOWN.sub("", spoken)
    spoken = re.sub(r"\s*\u2014\s*", ", ", spoken)  # em dash
    spoken = " ".join(spoken.split())

    if not reminders_ok:
        spoken = f"{spoken} {REMINDER_FAILED_LINE}".strip()
    return spoken, expecting_reply

# ------------------------------------------------------------------

def ask_gemini(prompt, history):
    """
    Sends prompt + conversation history to Gemini and returns
    (spoken_text, expecting_reply). Raises OfflineError if Gemini can't be
    reached, GeminiError for anything else that goes wrong.
    """
    contents = history + [{"role": "user", "parts": [{"text": prompt}]}]
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=[SEARCH_TOOL],
        thinking_config=THINKING,
    )
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
    except errors.APIError as e:
        print(f"gemini: API error {e.code}: {e.message}")
        raise GeminiError(str(e)) from e
    except Exception as e:
        if _is_network_error(e):
            print(f"gemini: can't reach Gemini: {e!r}")
            raise OfflineError(str(e)) from e
        print(f"gemini: unexpected error: {e!r}")
        raise GeminiError(str(e)) from e

    text = (response.text or "").strip()
    if not text:
        print(f"gemini: empty reply (finish reason: {_finish_reason(response)})")
        raise GeminiError("empty reply")

    spoken, expecting_reply = parse_response(text)
    if not spoken:
        raise GeminiError("reply was only tags")
    return spoken, expecting_reply


NETWORK_ERROR_NAMES = {"TransportError", "TimeoutException", "NetworkError", "ConnectionError"}

def _is_network_error(e):
    """True for connection failures and timeouts. Checked by name because
    google-genai has used both httpx and httpx2 under the hood."""
    while e is not None:
        if isinstance(e, (OSError, TimeoutError)):
            return True
        if NETWORK_ERROR_NAMES & {cls.__name__ for cls in type(e).__mro__}:
            return True
        e = e.__cause__ or e.__context__
    return False


def _finish_reason(response):
    try:
        return response.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return "unknown"


