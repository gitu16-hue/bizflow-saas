from database import SessionLocal
from models import Business

db = SessionLocal()

biz = db.query(Business).first()

if biz:
    biz.name = "BizFlow AI"
    biz.goal = "Automate leads & grow revenue"
    biz.business_type = "multi-business"
    db.commit()
    print("Updated!")

db.close()
