import json
import os
from datetime import datetime, date, timedelta

REMINDERS_FILE = "data/reminders.json"

#-------------------------------------------------------------------------------------------------------------------------------------------

def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        os.makedirs("data", exist_ok=True) # create data folder if DNE
        with open (REMINDERS_FILE, "w") as f:
            json.dump([], f) # create empty reminders file
    with open (REMINDERS_FILE, "r") as f:
        return json.load(f)

#-------------------------------------------------------------------------------------------------------------------------------------------

def save_reminders(reminders):
    with open (REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

#-------------------------------------------------------------------------------------------------------------------------------------------

def add_reminder(message, date, time, calendar=True):
    loaded_reminders = load_reminders()
    reminder_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    if reminder_datetime < datetime.now():
        return False  # can't set a reminder in the past, now checks the actual date+time together, not just the date
    id = (max((r["id"] for r in loaded_reminders), default=0)) + 1  # robust against deletions/reordering, always takes the true max across all reminders rather than assuming the last item has the highest id
    reminder = {"id": id, "date": date, "time": time, "message": message, "calendar": calendar, "completed": False, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    loaded_reminders.append(reminder)
    save_reminders(loaded_reminders)
    return True

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_today():
    reminders = load_reminders()
    today_reminders = []
    today = date.today()
    for reminder in reminders:
        if reminder["completed"]:
            continue
        reminder_date = datetime.strptime(reminder["date"], "%Y-%m-%d")
        if reminder_date.date() == today:
            today_reminders.append(reminder)
    return today_reminders

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_tomorrow():
    reminders = load_reminders()
    tomorrow_reminders = []
    tomorrow = date.today() + timedelta(days=1)
    for reminder in reminders:
        if reminder["completed"]:
            continue
        reminder_date = datetime.strptime(reminder["date"], "%Y-%m-%d")
        if reminder_date.date() == tomorrow:
            tomorrow_reminders.append(reminder)
    return tomorrow_reminders    


#-------------------------------------------------------------------------------------------------------------------------------------------

def get_this_week():
    reminders = load_reminders()
    week_reminders = []
    end_of_week = date.today() + timedelta(days=7)
    today = date.today()
    
    for reminder in reminders:
        if reminder["completed"]:
            continue
        reminder_date = datetime.strptime(reminder["date"], "%Y-%m-%d")
        if reminder_date.date() >= today and reminder_date.date() <= end_of_week :
            week_reminders.append(reminder)
    return week_reminders

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_this_month():
    reminders = load_reminders()
    month_reminders = []
    month = date.today().month
    for reminder in reminders:
        if reminder["completed"]:
            continue
        reminder_date = datetime.strptime(reminder["date"], "%Y-%m-%d")
        if reminder_date.month == month:
            month_reminders.append(reminder)
    return month_reminders

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_all_reminders():
    reminders = load_reminders()
    all_reminders = []
    for reminder in reminders:
        if not reminder["completed"]:
            all_reminders.append(reminder)
    return all_reminders

#-------------------------------------------------------------------------------------------------------------------------------------------

def delete_reminder(id):
    reminders = load_reminders()
    for i in range(len(reminders)):
        if reminders[i]["id"] == id:
            del reminders[i]
            save_reminders(reminders)
            return True
    return False

#-------------------------------------------------------------------------------------------------------------------------------------------

VALID_FIELDS = ["message", "date", "time", "calendar"]

def edit_reminder(id, field, new_value):
    reminders = load_reminders()
    for reminder in reminders:
        if reminder["id"] == id:
            if field in VALID_FIELDS:
                reminder[field] = new_value
                save_reminders(reminders)
                return True, True
            else:
                return True, False
    return False, False

#-------------------------------------------------------------------------------------------------------------------------------------------

def check_due_reminders():
    reminders = load_reminders()
    date_and_time = datetime.now()
    due_reminders = []
    for reminder in reminders:
        if reminder["completed"] == True:
            continue
        string_reminder_date_and_time = f"{reminder['date']} {reminder['time']}"
        reminder_date_and_time = datetime.strptime(string_reminder_date_and_time, "%Y-%m-%d %H:%M")
        if reminder_date_and_time <= date_and_time:
            due_reminders.append(reminder)
    return due_reminders

#-------------------------------------------------------------------------------------------------------------------------------------------

def mark_completed(id):
    reminders = load_reminders()
    for reminder in reminders:
        if reminder["id"] == id:
            reminder["completed"] = True
            save_reminders(reminders)
            return True
    return False
        
#-------------------------------------------------------------------------------------------------------------------------------------------

def clear_old_reminders():
    reminders = load_reminders()
    cutoff = datetime.now() - timedelta(days=7)
    reminders_to_keep = []
    changed = False
    for reminder in reminders:
        if reminder["completed"] == True and datetime.strptime(reminder["date"], "%Y-%m-%d") < cutoff:
            changed = True
            continue
        reminders_to_keep.append(reminder)
    if changed:
        save_reminders(reminders_to_keep)