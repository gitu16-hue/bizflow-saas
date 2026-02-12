from datetime import datetime, timedelta
from database import SessionLocal
from models import Booking, Business
from send_whatsapp import send_whatsapp_message
from date_utils import combine_booking_datetime


def run_booking_reminders():
    db = SessionLocal()
    now = datetime.utcnow()

    bookings = db.query(Booking).filter(
        Booking.status == "Booked"
    ).all()

    for b in bookings:
        business = db.query(Business).filter(
            Business.id == b.business_id
        ).first()

        if not business:
            continue

        booking_dt = combine_booking_datetime(
            b.booking_date,
            b.booking_time,
            business.timezone
        )

        # ⏰ 24 HOUR REMINDER
        if (
            not b.reminder_24h_sent
            and now >= booking_dt - timedelta(hours=24)
            and now < booking_dt - timedelta(hours=23)
        ):
            send_whatsapp_message(
                b.phone,
                (
                    f"⏰ Reminder!\n"
                    f"Your FREE trial at *{business.name}* "
                    f"is *tomorrow at {b.booking_time}* 💪"
                )
            )
            b.reminder_24h_sent = True

        # ⏰ 2 HOUR REMINDER
        elif (
            not b.reminder_2h_sent
            and now >= booking_dt - timedelta(hours=2)
            and now < booking_dt - timedelta(hours=1, minutes=50)
        ):
            send_whatsapp_message(
                b.phone,
                (
                    f"🔥 Almost time!\n"
                    f"Your FREE trial at *{business.name}* "
                    f"starts in *2 hours* 🏋️"
                )
            )
            b.reminder_2h_sent = True

        db.add(b)

    db.commit()
    db.close()


if __name__ == "__main__":
    run_booking_reminders()
