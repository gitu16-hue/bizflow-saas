import os
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Business")
BUSINESS_GOAL = os.getenv("BUSINESS_GOAL", "Convert lead")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "dev_secret_change_me"
)

ENV = os.getenv("ENV", "development")

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# ===============================
# APP SETTINGS
# ===============================

ENV = "development"   # change to "production" later

SESSION_SECRET = "super_secure_secret_12345_change_me"

BASE_URL = os.getenv("BASE_URL")

