from database import SessionLocal
from models import Business

def authenticate_business(email: str, password: str):
    db = SessionLocal()
    business = db.query(Business).filter(
        Business.admin_email == email,
        Business.admin_password == password
    ).first()
    db.close()
    return business
