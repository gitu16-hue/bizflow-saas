import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))


def send_email(to_email, subject, html):

    msg = EmailMessage()

    msg["From"] = f"BizFlow AI <{SMTP_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.set_content("Please view in HTML email client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:

        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)

        server.send_message(msg)
