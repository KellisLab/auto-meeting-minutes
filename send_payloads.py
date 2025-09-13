import json
import time
import datetime
import smtplib
import json
import os
from email.mime.text import MIMEText
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]

# Load events
with open("output/calendar_payloads.json") as f:
    events = json.load(f)

# Normalize keys: 'title' → 'summary'
for event in events:
    if "summary" not in event and "title" in event:
        event["summary"] = event["title"]

# OAuth setup
SCOPES = ["https://www.googleapis.com/auth/calendar"]
flow = InstalledAppFlow.from_client_config({
    "installed": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8081"]
    }
}, scopes=SCOPES)
creds = flow.run_local_server(port=8080)
service = build("calendar", "v3", credentials=creds)

created_event_ids = []

# === 2. Reminder Email ===
def send_reminder_email(from_email, app_password, to_email, summary):
    msg = MIMEText(f"Reminder: Please RSVP to the invite for '{summary}'")
    msg["Subject"] = f"RSVP Reminder: {summary}"
    msg["From"] = from_email
    msg["To"] = to_email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(from_email, app_password)
            server.send_message(msg)
            print(f"📧 Reminder sent to {to_email}")
    except Exception as e:
        print(f"Email to {to_email} failed: {e}")

# === 3. Scheduler ===
def schedule_event(event, fallback_attempt=0):
    start = event["preferred_time_range"]["start"]
    end = event["preferred_time_range"]["end"]
    attendees = event["attendees"]

    print(f"\n📌 Scheduling event: {event['summary']}")
    print(f"🕒 Time: {start} to {end}")
    print(f"👥 Attendees: {[a['email'] for a in attendees]}")

    # Check FreeBusy
    fbq = {
        "timeMin": start,
        "timeMax": end,
        "timeZone": "America/New_York",
        "items": [{"id": a["email"]} for a in attendees]
    }
    fb = service.freebusy().query(body=fbq).execute()

    conflict = False
    for a in attendees:
        email = a["email"]
        calendar = fb["calendars"].get(email)
        if not calendar:
            print(f"⚠️ Skipping {email} — no calendar data.")
            continue
        if calendar["busy"]:
            print(f"❌ {email} is busy. Skipping event: {event['summary']}")
            conflict = True
            break

    if conflict:
        if fallback_attempt < 3:
            start_dt = datetime.datetime.fromisoformat(start[:-1]) + datetime.timedelta(hours=1)
            end_dt = datetime.datetime.fromisoformat(end[:-1]) + datetime.timedelta(hours=1)
            event["preferred_time_range"]["start"] = start_dt.isoformat(timespec="seconds") + "Z"
            event["preferred_time_range"]["end"] = end_dt.isoformat(timespec="seconds") + "Z"
            print(f"🔁 Rescheduling '{event['summary']}' to next hour due to conflict.")
            return schedule_event(event, fallback_attempt + 1)
        else:
            print(f"⛔ Gave up scheduling '{event['summary']}' after 3 attempts.")
            return None

    # Create calendar event
    cal_event = {
        "summary": event["summary"],
        "description": event.get("description", ""),  # fallback to empty string
        "start": {"dateTime": event["preferred_time_range"]["start"], "timeZone": "America/New_York"},
        "end": {"dateTime": event["preferred_time_range"]["end"], "timeZone": "America/New_York"},
        "attendees": attendees
    }

    print("📦 Payload to be scheduled:")
    print(json.dumps(cal_event, indent=2))

    created = service.events().insert(
    calendarId="primary",
    sendUpdates="all",  # 👈 Add this
    body=cal_event
).execute()

    print(f"📅 Created: {created.get('htmlLink')}")
    return created["id"]

# === 4. Schedule all ===
for event in events:
    required_keys = ["summary", "preferred_time_range", "attendees"]
    if not all(key in event for key in required_keys):
        print(f"⚠️ Skipping invalid event (missing keys): {event}")
        continue

    eid = schedule_event(event)
    if eid:
        created_event_ids.append(eid)

# === 5. RSVP Polling ===
REMINDER_SENT = set()
SENDER_EMAIL = "your_email@gmail.com"       # <--- CHANGE THIS
APP_PASSWORD = "your_app_password"          # <--- AND THIS

print("\n🔁 Polling for RSVP (up to 9 hours)...")
for attempt in range(54):  # 9 hours with 10-min intervals
    all_done = True
    for eid in created_event_ids:
        ev = service.events().get(calendarId="primary", eventId=eid).execute()
        attendees = ev.get("attendees", [])
        statuses = [(a["email"], a.get("responseStatus", "needsAction")) for a in attendees]
        print(f"🕵️ RSVP statuses: {statuses}")


        for email, status in statuses:
            if status == "declined":
                print(f"❌ {email} declined. Deleting '{ev['summary']}'")
                service.events().delete(calendarId="primary", eventId=eid).execute()
                break
            elif status == "needsAction":
                all_done = False
                if attempt >= 18 and (eid, email) not in REMINDER_SENT:
                    send_reminder_email(SENDER_EMAIL, APP_PASSWORD, email, ev["summary"])
                    REMINDER_SENT.add((eid, email))

    if all_done:
        print("✅ All events confirmed by attendees.")
        break

    time.sleep(600)  # wait 10 minutes
else:
    print("⚠️ Timeout reached. Some attendees did not respond.")
