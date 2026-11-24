import json
import os
import threading
from datetime import datetime, date, timedelta

import solu_calendar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REMINDERS_FILE = os.path.join(BASE_DIR, "data", "reminders.json")

KEEP_COMPLETED_DAYS = 7

# the wake word thread adds reminders while the reminder thread marks them
# done, so every read-modify-write holds this lock
_lock = threading.RLock()

# ------------------------------------------------------------------
# file access
# ------------------------------------------------------------------

def load_reminders():
    with _lock:
        try:
            with open(REMINDERS_FILE, "r") as f:
                reminders = json.load(f)
            return reminders if isinstance(reminders, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as e:
            # keep the broken file for inspection instead of crashing every 10 seconds
            backup = f"{REMINDERS_FILE}.broken-{datetime.now():%Y%m%d-%H%M%S}"
            print(f"reminders: file unreadable ({e!r}), moved to {backup}, starting fresh")
            try:
                os.replace(REMINDERS_FILE, backup)
            except OSError:
                pass
            return []


def save_reminders(reminders):
    """Writes to a temp file then swaps it in, so a power cut mid-write can't corrupt the real file."""
    with _lock:
        os.makedirs(os.path.dirname(REMINDERS_FILE), exist_ok=True)
        temp = REMINDERS_FILE + ".tmp"
        with open(temp, "w") as f:
            json.dump(reminders, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, REMINDERS_FILE)


def _due_time(reminder):
    """The reminder's datetime, or None if the entry is malformed."""
    try:
        return datetime.strptime(f"{reminder['date']} {reminder['time']}", "%Y-%m-%d %H:%M")
    except (KeyError, TypeError, ValueError):
        return None


def _pending(reminders):
    return [r for r in reminders if not r.get("completed") and _due_time(r) is not None]

# ------------------------------------------------------------------

def add_reminder(message, date, time, calendar=False):
    """Saves a reminder. Returns False (never raises) if the date/time is
    invalid or already in the past."""
    try:
        when = datetime.strptime(f"{date.strip()} {time.strip()}", "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return False
    if when < datetime.now() or not str(message).strip():
        return False

    with _lock:
        reminders = load_reminders()
        reminder = {
            "id": max((r.get("id", 0) for r in reminders), default=0) + 1,
            "date": when.strftime("%Y-%m-%d"),   # normalized, e.g. 9:05 -> 09:05
            "time": when.strftime("%H:%M"),
            "message": str(message).strip(),
            "calendar": bool(calendar),
            "completed": False,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        reminders.append(reminder)
        save_reminders(reminders)

    if calendar:
        # off the main path so Solu doesn't wait on Google before answering
        threading.Thread(
            target=solu_calendar.add_event,
            args=(reminder["message"], reminder["date"], reminder["time"]),
            daemon=True,
        ).start()
    return True

# ------------------------------------------------------------------
# queries
# ------------------------------------------------------------------

def get_between(start_date, end_date):
    """Pending reminders with a date from start_date to end_date, inclusive."""
    return [r for r in _pending(load_reminders()) if start_date <= _due_time(r).date() <= end_date]


def get_today():
    return get_between(date.today(), date.today())


def get_tomorrow():
    tomorrow = date.today() + timedelta(days=1)
    return get_between(tomorrow, tomorrow)


def get_this_week():
    return get_between(date.today(), date.today() + timedelta(days=7))


def get_this_month():
    today = date.today()
    return [r for r in _pending(load_reminders())
            if (_due_time(r).year, _due_time(r).month) == (today.year, today.month)]


def get_all_reminders():
    return _pending(load_reminders())


def check_due_reminders():
    """Pending reminders whose time has come, oldest first."""
    now = datetime.now()
    due = [r for r in _pending(load_reminders()) if _due_time(r) <= now]
    return sorted(due, key=_due_time)

# ------------------------------------------------------------------
# changes
# ------------------------------------------------------------------

def delete_reminder(id):
    with _lock:
        reminders = load_reminders()
        kept = [r for r in reminders if r.get("id") != id]
        if len(kept) == len(reminders):
            return False
        save_reminders(kept)
        return True


VALID_FIELDS = ["message", "date", "time", "calendar"]

def edit_reminder(id, field, new_value):
    """Returns (found, edited)."""
    with _lock:
        reminders = load_reminders()
        for reminder in reminders:
            if reminder.get("id") == id:
                if field not in VALID_FIELDS:
                    return True, False
                reminder[field] = new_value
                save_reminders(reminders)
                return True, True
        return False, False


def mark_completed(id):
    with _lock:
        reminders = load_reminders()
        for reminder in reminders:
            if reminder.get("id") == id:
                reminder["completed"] = True
                save_reminders(reminders)
                return True
        return False


def clear_old_reminders():
    """Drops completed reminders older than a week, and entries too broken to ever fire."""
    with _lock:
        reminders = load_reminders()
        cutoff = datetime.now() - timedelta(days=KEEP_COMPLETED_DAYS)
        kept = []
        for r in reminders:
            due = _due_time(r)
            if due is None or (r.get("completed") and due < cutoff):
                continue
            kept.append(r)
        if len(kept) != len(reminders):
            save_reminders(kept)
