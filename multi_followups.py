from datetime import datetime, timedelta
from database import SessionLocal
from models import Conversation, Booking, Business
from send_whatsapp import send_whatsapp_message

FOLLOWUPS = [
    {
        "stage": "Interested",
        "after_days": 1,
        "next_stage": "Followup_1",
        "message": (
            "Hi! 👋 Just checking in 😊\n"
            "Would you like to book your FREE trial at {business}? 💪"
        ),
    },
    {
        "stage": "Followup_1",
        "after_days": 3,
        "next_stage": "Followup_2",
        "message": (
            "Hey! 😊 Our FREE trial slots are filling fast 💪\n"
            "Shall I reserve one for you at {business}?"
        ),
    },
    {
        "stage": "Followup_2",
        "after_days": 7,
        "next_stage": "Closed",
        "message": (
            "Last reminder 😊\n"
            "If you’d still like a FREE session at {business}, just reply *hi* 💪"
        ),
    },
]


def run_multi_followups():
    db = SessionLocal()
    now = datetime.utcnow()

    for f in FOLLOWUPS:
        cutoff = now - timedelta(days=f["after_days"])

        conversations = db.query(Conversation).filter(
            Conversation.stage == f["stage"],
            Conversation.updated_at < cutoff,
            Conversation.followups_stopped == False,
        ).all()

        for convo in conversations:
            # 🔒 STOP if user already booked
            booking_exists = db.query(Booking).filter(
                Booking.phone == convo.phone,
                Booking.business_id == convo.business_id,
                Booking.status == "Booked"
            ).first()

            if booking_exists:
                convo.followups_stopped = True
                convo.stage = "Booked"
                db.add(convo)
                continue

            business = db.query(Business).filter(
                Business.id == convo.business_id
            ).first()

            message = f["message"].format(
                business=business.name
            )

            send_whatsapp_message(convo.phone, message)

            convo.stage = f["next_stage"]
            convo.updated_at = now
            db.add(convo)

    db.commit()
    db.close()


if __name__ == "__main__":
    run_multi_followups()
