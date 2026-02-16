from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Float,
    JSON
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

    # Add business hours for better customer info
    business_hours = Column(String, nullable=True)

    whatsapp_number = Column(String, unique=True, nullable=False)

    flow_state = Column(String(50), default="start")


    # ---------------- AUTH ----------------

    admin_email = Column(String, unique=True, nullable=False, index=True)

    admin_password = Column(String, nullable=False)

    is_admin = Column(Boolean, default=False)


    # Password reset fields (already present, just keeping one copy)
    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)


    # ---------------- BILLING ----------------

    # trial | starter | pro | expired
    plan = Column(String, default="trial")

    is_active = Column(Boolean, default=True)

    trial_ends_at = Column(DateTime, nullable=True)  # Renamed for consistency

    paid_until = Column(DateTime, nullable=True)

    plan_started = Column(DateTime, nullable=True)

    last_order_id = Column(String, index=True, nullable=True)


    # ---------------- USAGE ----------------

    chat_used = Column(Integer, default=0)

    chat_limit = Column(Integer, default=300)


    # ---------------- STATUS ----------------

    whatsapp_active = Column(Boolean, default=True)

    onboarding_done = Column(Boolean, default=False)


    # ---------------- SETTINGS ----------------

    settings_json = Column(Text, default="{}")


    # ---------------- TIMESTAMPS ----------------

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    last_login = Column(DateTime, nullable=True)


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

    payments = relationship(
        "Payment",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


# =================================================
# PAYMENT MODEL (NEW)
# =================================================

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to business
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Payment gateway identifiers
    payment_id = Column(String, unique=True, nullable=False, index=True)  # Razorpay payment ID
    order_id = Column(String, unique=True, nullable=False, index=True)    # Razorpay order ID
    signature = Column(String, nullable=True)  # Razorpay signature for verification
    
    # Payment details
    amount = Column(Float, nullable=False)  # In INR
    currency = Column(String, default="INR")
    status = Column(String, default="pending")  # pending, success, failed, refunded
    plan = Column(String, nullable=False)  # starter, pro
    
    # Payment method (card, upi, netbanking, etc.)
    payment_method = Column(String, nullable=True)
    
    # Store full payment response from Razorpay for audit
    payment_data = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    business = relationship("Business", back_populates="payments")
    
    def __repr__(self):
        return f"<Payment {self.id}: {self.payment_id} - ₹{self.amount}>"


# =================================================
# AUDIT LOG MODEL (NEW)
# =================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User who performed the action (can be null for system actions)
    user_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Action details
    action = Column(String, nullable=False, index=True)  # e.g., "login", "payment", "admin_action"
    details = Column(JSON, nullable=True)  # Store additional context
    
    # Request metadata
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationship (optional - to get user info)
    user = relationship("Business")
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action}>"


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
    
    email = Column(String, nullable=True)  # Added email field


    booking_date = Column(String)

    booking_time = Column(String)


    # Booked | Cancelled | Completed | NoShow
    status = Column(String, default="Booked", index=True)


    # ---------------- META ----------------

    # whatsapp | manual | api
    source = Column(String, default="whatsapp")
    
    notes = Column(Text, nullable=True)  # Added notes field


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