# test_models.py
import patch_pydantic
from models import Business, Booking
from pydantic import BaseModel

print("\n=== Testing Models with Patch ===\n")

try:
    # Test Business model creation
    test_business = Business(
        name="Test Business",
        whatsapp_number="1234567890",
        admin_email="test@example.com",
        business_type="restaurant"
    )
    print("✅ Business model created successfully")
except Exception as e:
    print(f"❌ Business model failed: {e}")

try:
    # Test Booking model creation
    test_booking = Booking(
        business_id=1,
        name="Test User",
        phone="1234567890",
        booking_date="2026-02-14",
        booking_time="3PM"
    )
    print("✅ Booking model created successfully")
except Exception as e:
    print(f"❌ Booking model failed: {e}")

print("\n=== Test complete ===")