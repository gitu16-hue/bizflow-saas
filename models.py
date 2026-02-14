from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean
)

from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


# =================================================
# BUSINESS (SAAS + MULTI TENANT + BILLING)
# =================================================

class Business(Base):

    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)

    # ---------------- BASIC INFO ----------------

    name = Column(String, nullable=False)

    goal = Column(String, default="")

    # Industry / Niche
    # gym | salon | restaurant | hotel | realestate
    business_type = Column(String, default="gym", index=True)

    address = Column(String(255), nullable=True)

    # Add these new fields
    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)


    whatsapp_number = Column(String, unique=True, nullable=False)

    flow_state = Column(String(50), default="start")


    # ---------------- AUTH ----------------

    admin_email = Column(String, unique=True, nullable=False, index=True)

    admin_password = Column(String, nullable=False)

    is_admin = Column(Boolean, default=False)


    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)



    # ---------------- BILLING ----------------

    # trial | starter | pro | expired
    plan = Column(String, default="trial")

    is_active = Column(Boolean, default=True)

    trial_ends = Column(DateTime)

    paid_until = Column(DateTime)

    plan_started = Column(DateTime)

    last_order_id = Column(String, index=True)


    # ---------------- USAGE ----------------

    chat_used = Column(Integer, default=0)

    chat_limit = Column(Integer, default=300)


    # ---------------- STATUS ----------------

    whatsapp_active = Column(Boolean, default=True)

    onboarding_done = Column(Boolean, default=False)


    # ---------------- SETTINGS ----------------

    settings_json = Column(Text, default="{}")


    # ---------------- SYSTEM ----------------

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    # ---------------- RELATIONSHIPS ----------------

    conversations = relationship(
        "Conversation",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    bookings = relationship(
        "Booking",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


# =================================================
# CONVERSATION (AI FLOW ENGINE)
# =================================================

class Conversation(Base):

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)


    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True
    )


    phone = Column(String, index=True, nullable=False)


    last_message = Column(Text)

    last_reply = Column(Text)


    # ---------------- FLOW STATE ----------------

    stage = Column(String, default="New")


    # Temp memory
    temp_date = Column(String)

    temp_time = Column(String)


    # ---------------- META ----------------

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    created_at = Column(DateTime, default=datetime.utcnow)


    # ---------------- RELATION ----------------

    business = relationship(
        "Business",
        back_populates="conversations"
    )


# =================================================
# BOOKINGS (REVENUE ENGINE)
# =================================================

class Booking(Base):

    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)


    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True
    )


    phone = Column(String, nullable=False, index=True)

    name = Column(String, nullable=False)


    booking_date = Column(String)

    booking_time = Column(String)


    # Booked | Cancelled | Completed | NoShow
    status = Column(String, default="Booked", index=True)


    # ---------------- META ----------------

    # whatsapp | manual | api
    source = Column(String, default="whatsapp")


    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    # ---------------- RELATION ----------------

    business = relationship(
        "Business",
        back_populates="bookings"
    )
