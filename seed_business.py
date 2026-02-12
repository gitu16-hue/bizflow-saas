from passlib.hash import bcrypt
from datetime import datetime, timedelta

from database import SessionLocal
from models import Business


# --------------------------------------------
# CONFIG
# --------------------------------------------

EMAIL = "gym@demo.com"
PASSWORD = "123456"

TRIAL_DAYS = 7
CHAT_LIMIT = 300


# --------------------------------------------
# DB
# --------------------------------------------

db = SessionLocal()


# --------------------------------------------
# CHECK EXISTING
# --------------------------------------------

existing = db.query(Business)\
    .filter(Business.admin_email == EMAIL)\
    .first()


if existing:

    print("⚠️ Business already exists:", existing.name)
    print("Plan:", existing.plan)
    print("Trial ends:", existing.trial_ends)

else:

    now = datetime.utcnow()

    business = Business(

        # Basic Info
        name="Demo Gym",
        goal="Book free trials automatically",

        whatsapp_number="whatsapp:+14155238886",

        # Auth
        admin_email=EMAIL,
        admin_password=bcrypt.hash(PASSWORD),

        # Trial Setup
        plan="trial",
        is_active=True,

        trial_ends=now + timedelta(days=TRIAL_DAYS),
        plan_started=now,

        paid_until=None,

        last_order_id=None,

        # Usage
        chat_used=0,
        chat_limit=CHAT_LIMIT,

        # Status
        whatsapp_active=True,
        onboarding_done=False,

        # Settings
        settings_json="{}"
    )

    db.add(business)
    db.commit()

    print("✅ Business created with TRIAL")
    print("Email:", EMAIL)
    print("Password:", PASSWORD)
    print("Trial ends:", business.trial_ends)


db.close()
