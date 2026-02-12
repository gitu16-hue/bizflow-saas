from datetime import datetime, timedelta
from sqlalchemy import func
from database import SessionLocal
from models import Conversation, Booking


def get_business_analytics(business_id: int):
    db = SessionLocal()
    now = datetime.utcnow()
    today = now.date()

    total_conversations = db.query(Conversation).filter(
        Conversation.business_id == business_id
    ).count()

    interested = db.query(Conversation).filter(
        Conversation.business_id == business_id,
        Conversation.stage.in_(["Interested", "Followup_1", "Followup_2"])
    ).count()

    bookings = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.status == "Booked"
    ).count()

    cancelled = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.status == "Cancelled"
    ).count()

    today_bookings = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.created_at >= datetime.combine(today, datetime.min.time())
    ).count()

    upcoming = db.query(Booking).filter(
        Booking.business_id == business_id,
        Booking.status == "Booked"
    ).count()

    conversion_rate = (
        round((bookings / total_conversations) * 100, 2)
        if total_conversations > 0 else 0
    )

    db.close()

    return {
        "total_conversations": total_conversations,
        "interested": interested,
        "bookings": bookings,
        "cancelled": cancelled,
        "today_bookings": today_bookings,
        "upcoming_bookings": upcoming,
        "conversion_rate": conversion_rate
    }
