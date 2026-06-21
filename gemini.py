from google import genai
from google.genai import types
import json
import os
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

MEMORY_FILE = "data/memory.json"

SOLU_SYSTEM_PROMPT = SOLU_SYSTEM_PROMPT = """You are Sowlu, a male desk assistant built by Shay E Oloomoo-raywah, a Computer Engineering student at Texas A&M University. 
You are witty, confident, and slightly sarcastic but know when to be straight and professional.
When executing tasks like setting reminders or checking weather, be direct and functional.
When having casual conversation, show personality.
Keep responses concise and conversational.
Never curse. Never dumb things down. Talk like a cool, smart person.
Do not use em dashes in any response.
Do not use overly formal language or sound robotic. Be natural.

When the user wants to set a reminder, you need both a message and a time
before it can be created. If either is missing, ask for exactly what's
missing in one short sentence, nothing else.

You are an assistant first. Most responses should completely answer the
user and end there, not invite further conversation. Do not ask follow-up
questions out of habit or to "keep things going" (for example, never
respond to "how are you" by asking how the user is doing back). Only ask
a follow-up question when you are genuinely missing information needed
to complete what the user asked for.

CRITICAL FORMATTING RULE: every single response you give, with no
exceptions, must end with exactly one of these two tags and nothing
after them: <<<FOLLOWUP:TRUE>>> or <<<FOLLOWUP:FALSE>>>
Use TRUE only when you are asking the user for missing information you
genuinely need (like a missing reminder time). Use FALSE for everything
else, including normal conversation, casual answers, and complete
responses. This tag is a silent control signal for the program reading
your response, never mention it, explain it, or refer to it in the
words you actually say to the user.
"""

#-------------------------------------------------------------------------------------------------------------------------------------------

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        os.makedirs("data", exist_ok=True) # create data folder if DNE
        with open (MEMORY_FILE, "w") as f:
            json.dump([], f) # create empty reminders file
    with open (MEMORY_FILE, "r") as f:
        return json.load(f)

#-------------------------------------------------------------------------------------------------------------------------------------------

def save_memory(memory):
    with open (MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

#-------------------------------------------------------------------------------------------------------------------------------------------

def add_to_memory(fact):
    memories = load_memory()
    memories.append(fact)
    save_memory(memories)


#-------------------------------------------------------------------------------------------------------------------------------------------

def remove_from_memory(fact):
    memories = load_memory()
    for memory in memories:
        if fact == memory:
            memories.remove(fact)
            save_memory(memories)
            return True
    return False

#-------------------------------------------------------------------------------------------------------------------------------------------

def build_system_prompt():
    memories = load_memory()
    system_prompt = SOLU_SYSTEM_PROMPT
    if memories:
        system_prompt += "\n\nThings to remember about the user:\n"
        for memory in memories:
            system_prompt += f"- {memory}\n"
    return system_prompt    

#-------------------------------------------------------------------------------------------------------------------------------------------

def ask_gemini(prompt, history):
    try:
        system_prompt = build_system_prompt()
        search_tool = types.Tool(google_search=types.GoogleSearch())
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[search_tool],
            )
        )
        text = response.text.strip()

        if text.endswith("<<<FOLLOWUP:TRUE>>>"):
            clean_text = text[:-len("<<<FOLLOWUP:TRUE>>>")].strip()
            return clean_text, True
        elif text.endswith("<<<FOLLOWUP:FALSE>>>"):
            clean_text = text[:-len("<<<FOLLOWUP:FALSE>>>")].strip()
            return clean_text, False
        return text, False
    except:
        return None, False

#-------------------------------------------------------------------------------------------------------------------------------------------

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
    
#-------------------------------------------------------------------------------------------------------------------------------------------

def reset_history():
    return []

#-------------------------------------------------------------------------------------------------------------------------------------------