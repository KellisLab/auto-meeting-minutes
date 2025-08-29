import smtplib
from email.mime.text import MIMEText

# Define sender credentials
from_email = "kamchettysadhika10@gmail.com"
app_password = "dewh lzfu ztee uoum"       # Replace with your 16-digit app password

# Define recipients
recipients = ["ksadhika10@gmail.com", "chegga903@gmail.com"]

# Create email
msg = MIMEText("This is a test email for collaboration.")
msg["Subject"] = "Mantis Collaboration Test"
msg["From"] = from_email
msg["To"] = ", ".join(recipients)  # SINGLE To header

# Send email
try:
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(from_email, app_password)
        server.sendmail(from_email, recipients, msg.as_string())
        print("✅ Email sent to:", ", ".join(recipients))
except Exception as e:
    print("❌ Error sending email:", e)
