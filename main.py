# =====================================================
# BizFlow AI - ENTERPRISE SAAS PLATFORM
# PART 1/2 — CORE + BOT ENGINE
# Version 9.0
# =====================================================
# main.py - THESE MUST BE THE FIRST LINES
try:
    import patch_pydantic
    print("✅ Pydantic patch loaded successfully")
except ImportError:
    print("⚠️  Pydantic patch not found, continuing without it")
except Exception as e:
    print(f"⚠️  Error loading patch: {e}")

# =====================================================
# BizFlow AI - ENTERPRISE SAAS PLATFORM
# PART 1/2 — CORE + BOT ENGINE
# Version 9.0
# =====================================================

import os
import re
import logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# ================= FASTAPI =================

from fastapi import FastAPI, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.sessions import SessionMiddleware

# ================= SECURITY =================

from passlib.hash import bcrypt

# ================= TWILIO =================

from twilio.twiml.messaging_response import MessagingResponse

# ================= DATABASE =================

from database import SessionLocal, engine
from models import Base, Business, Booking

import sendgrid
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@bizflowai.online")

# ... rest of your main.py code ...
import os
import re
import logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# ================= FASTAPI =================

from fastapi import FastAPI, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.sessions import SessionMiddleware

# ================= SECURITY =================

from passlib.hash import bcrypt

# ================= TWILIO =================

from twilio.twiml.messaging_response import MessagingResponse

# ================= DATABASE =================

from database import SessionLocal, engine
from models import Base, Business, Booking


# =====================================================
# CONFIG
# =====================================================

APP_NAME = "BizFlow AI"

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8001")

SECRET_KEY = os.getenv("SECRET_KEY", "bizflow_secret_2026")


# =====================================================
# APP INIT
# =====================================================

app = FastAPI(title=APP_NAME, version="9.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 24 * 14
)

templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)


# =====================================================
# LOGGING
# =====================================================

logging.basicConfig(
    filename="bizflow.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("bizflow")


# =====================================================
# DATABASE DEP
# =====================================================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# =====================================================
# AUTH HELPERS
# =====================================================

def is_logged(req):

    return bool(req.session.get("business_id"))


def get_user(req, db):

    bid = req.session.get("business_id")

    if not bid:
        return None

    return db.query(Business).get(bid)


def require_admin(req, db):

    user = get_user(req, db)

    if not user or not user.is_admin:
        return None

    return user

def send_reset_email(to_email: str, reset_link: str):
    """Send password reset email using SendGrid"""
    print("="*50)
    print(f"📧 ENTERING SEND_RESET_EMAIL FUNCTION")
    print(f"📧 To: {to_email}")
    print(f"📧 Reset link: {reset_link}")
    print(f"📧 SendGrid API Key present: {bool(SENDGRID_API_KEY)}")
    print(f"📧 From email: {FROM_EMAIL}")
    
    if not SENDGRID_API_KEY:
        print("❌ CRITICAL: SendGrid API key not configured or empty")
        print("📧 Please check Railway environment variables")
        return False
    
    try:
        print("📧 Creating email message...")
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject='Reset Your BizFlow AI Password',
            html_content=f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #2563eb, #60a5fa); color: white; padding: 40px 20px; text-align: center; }}
                    .content {{ background: white; padding: 40px 20px; }}
                    .button {{ display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 12px 30px; border-radius: 8px; font-weight: 600; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>BizFlow AI</h1>
                        <p>Password Reset Request</p>
                    </div>
                    <div class="content">
                        <h2>Hello!</h2>
                        <p>Click the button below to reset your password:</p>
                        <div style="text-align: center;">
                            <a href="{reset_link}" class="button">Reset Password</a>
                        </div>
                        <p>Or copy this link: {reset_link}</p>
                        <p>This link expires in 24 hours.</p>
                    </div>
                </div>
            </body>
            </html>
            '''
        )
        print("📧 Message created successfully")
        
        print("📧 Initializing SendGrid client...")
        sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
        print("📧 SendGrid client initialized")
        
        print("📧 Sending email...")
        response = sg.send(message)
        print(f"📧 SendGrid response received")
        print(f"📧 Status code: {response.status_code}")
        print(f"📧 Response body: {response.body}")
        print(f"📧 Response headers: {response.headers}")
        
        if response.status_code == 202:
            print(f"✅ EMAIL SENT SUCCESSFULLY to {to_email}")
            print("="*50)
            return True
        else:
            print(f"❌ SendGrid returned non-202 status: {response.status_code}")
            print("="*50)
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION in send_reset_email: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*50)
        return False

# =====================================================
# UTILITIES
# =====================================================

def clean_phone(phone: str):

    if not phone:
        return ""

    phone = phone.replace("whatsapp:", "")
    phone = phone.replace("+", "")
    phone = phone.replace(" ", "")
    phone = phone.replace("-", "")
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")

    phone = "".join(filter(str.isdigit, phone))

    if len(phone) == 10:
        phone = "91" + phone

    return phone


def validate_password(pwd):

    if len(pwd) < 8:
        return False

    return (
        any(x.isdigit() for x in pwd) and
        any(x.isupper() for x in pwd)
    )


# =====================================================
# INDUSTRY MENU
# =====================================================

def get_industry_menu(business):

    name = business.name
    industry = business.business_type.lower()


    # RESTAURANT
    if "restaurant" in industry:

        return f"""
👋 Welcome to *{name}* 🍽️

1️⃣ Book Table
2️⃣ View Menu
3️⃣ Location
4️⃣ Order Help
5️⃣ Exit

Reply 1-5 👇
"""


    # CLINIC
    if "clinic" in industry:

        return f"""
👋 Welcome to *{name}* 🏥

1️⃣ Book Appointment
2️⃣ Fees
3️⃣ Timings
4️⃣ Doctor Info
5️⃣ Exit

Reply 1-5 👇
"""


    # SALON
    if "salon" in industry:

        return f"""
👋 Welcome to *{name}* 💇

1️⃣ Book Slot
2️⃣ Services
3️⃣ Location
4️⃣ Stylist
5️⃣ Exit

Reply 1-5 👇
"""


    # GYM
    if "gym" in industry:

        return f"""
👋 Welcome to *{name}* 🏋️

1️⃣ Book Session
2️⃣ Pricing
3️⃣ Timings
4️⃣ Trainer
5️⃣ Exit

Reply 1-5 👇
"""


    # DEFAULT
    return f"""
👋 Welcome to *{name}*

1️⃣ Book Appointment
2️⃣ Pricing
3️⃣ Location
4️⃣ Support
5️⃣ Exit

Reply 1-5 👇
"""


# =====================================================
# BOOKING NLP PARSER
# =====================================================

MONTHS = {
    "jan":"01","feb":"02","mar":"03","apr":"04",
    "may":"05","jun":"06","jul":"07","aug":"08",
    "sep":"09","oct":"10","nov":"11","dec":"12"
}


def parse_booking(text):

    try:

        text = text.lower().strip()

        text = text.replace("\\", "/")
        text = text.replace("-", "/")

        text = re.sub(r"\s+", " ", text)

        parts = text.split(" ")

        if len(parts) < 3:
            return None


        # DATE

        day = ""
        month = ""


        # 12/02
        if "/" in parts[0]:

            d = parts[0].split("/")

            if len(d) != 2:
                return None

            day, month = d


        # 12 feb
        elif parts[0].isdigit() and parts[1][:3] in MONTHS:

            day = parts[0]
            month = MONTHS.get(parts[1][:3])

            parts.pop(1)


        else:
            return None


        if not day.isdigit() or not month:
            return None


        year = datetime.now().year

        date_final = f"{day.zfill(2)}-{month.zfill(2)}-{year}"


        # TIME

        time = parts[1].upper().replace(" ", "")

        if not re.match(r"\d{1,2}(:\d{2})?(AM|PM)", time):
            return None


        # NAME

        name = " ".join(parts[2:]).title()

        if len(name) < 2:
            return None


        return {
            "date": date_final,
            "time": time,
            "name": name
        }


    except Exception:

        return None


# =====================================================
# BOT ENGINE
# =====================================================

def reset_flow(business, db):

    business.flow_state = "menu"
    db.commit()


def whatsapp_bot(phone, msg, business, db):

    msg = msg.strip()
    low = msg.lower()

    name = business.name
    industry = business.business_type.lower()

    state = business.flow_state or "start"


    # ================= RESET =================

    if low in ["reset","restart","help"]:

        reset_flow(business, db)

        return "🔄 Reset Done\n\n" + get_industry_menu(business)


    # ================= GREETING =================

    if low in ["hi","hello","hey","hii","hy","start","menu"]:

        business.flow_state = "menu"
        db.commit()

        return get_industry_menu(business)


    # ================= MENU =================

    if state in ["start","menu"]:


        # BOOK

        if low in ["1","book","booking","appointment"]:

            business.flow_state = "booking"
            db.commit()

            return (
                "📅 Send booking like:\n"
                "12 Feb 5PM Rahul\n"
                "12/02 3PM Rahul\n\n"
                "Or type Cancel"
            )


        # OPTION 2

        if low == "2":

            if "restaurant" in industry:
                reply = "📖 Menu:\nPizza ₹199\nBurger ₹99\nPasta ₹149"

            elif "clinic" in industry:
                reply = "💰 Consultation ₹500"

            elif "salon" in industry:
                reply = "💇 Haircut ₹199\nFacial ₹799"

            elif "gym" in industry:
                reply = "🏋️ Monthly ₹999\nYearly ₹7999"

            else:
                reply = "💰 Contact Office"


            business.flow_state = "menu"
            db.commit()

            return reply + "\n\nReply 1-5 👇"


        # LOCATION

        if low in ["3","location","address"]:

            addr = getattr(business, "address", None) or "Main Road"

            return f"""
📍 {addr}
🕒 9AM - 9PM
"""


        # SUPPORT

        if low in ["4","staff","support"]:

            business.flow_state = "menu"
            db.commit()

            return "📞 Our team will contact you shortly."


        # EXIT

        if low in ["5","exit","bye"]:

            business.flow_state = "start"
            db.commit()

            return "👋 Thank you!"


        return "❌ Reply 1-5"


    # ================= BOOKING =================

    if state == "booking":


        # CANCEL

        if low in ["cancel","back","exit"]:

            reset_flow(business, db)

            return "❌ Cancelled\n\n" + get_industry_menu(business)


        data = parse_booking(msg)


        if not data:

            business.flow_state = "booking"
            db.commit()

            return (
                "❌ Invalid format ❗\n\n"
                "Try:\n"
                "12 Feb 5PM Rahul\n"
                "12/02 3PM Rahul\n"
                "12-02 3PM Rahul\n\n"
                "Or type Cancel"
            )


        # SAVE

        booking = Booking(

            business_id=business.id,

            name=data["name"],
            phone=phone,

            booking_date=data["date"],
            booking_time=data["time"],

            status="pending"
        )

        db.add(booking)


        business.flow_state = "menu"

        db.commit()


        return f"""
✅ Booking Confirmed!

👤 {data['name']}
📅 {data['date']}
⏰ {data['time']}

Type Hi 👋
"""


    # ================= FALLBACK =================

    reset_flow(business, db)

    return "Type Hi to start 👋"


# =====================================================
# WHATSAPP WEBHOOK
# =====================================================

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request, db=Depends(get_db)):

    form = await req.form()

    raw = form.get("From","")
    msg = form.get("Body","")

    phone = clean_phone(raw)

    logger.info(f"WA | {phone} | {msg}")


    business = db.query(Business)\
        .filter(Business.whatsapp_number==phone)\
        .first()


    if not business:

        reply = (
            "👋 Hello!\n"
            "Your number is not registered.\n"
            "Please contact admin."
        )

    else:

        try:
            business.chat_used = (business.chat_used or 0) + 1
            db.commit()

        except:
            db.rollback()


        reply = whatsapp_bot(phone, msg, business, db)


    resp = MessagingResponse()

    resp.message(reply)

    return Response(
        content=str(resp),
        media_type="application/xml"
    )

# =====================================================
# PART 2/2 — AUTH + DASHBOARD + BILLING + ADMIN
# =====================================================

import razorpay
from datetime import timedelta

# =====================================================
# RAZORPAY CONFIG
# =====================================================

RAZORPAY_KEY = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = None

if RAZORPAY_KEY and RAZORPAY_SECRET:
    razorpay_client = razorpay.Client(
        auth=(RAZORPAY_KEY, RAZORPAY_SECRET)
    )


# =====================================================
# PLANS
# =====================================================

PLANS = {
    "starter": {
        "price": 999,
        "chats": 300
    },
    "pro": {
        "price": 2499,
        "chats": 999999
    }
}


# =====================================================
# HOME
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home(req: Request):

    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "logged": is_logged(req)
        }
    )


# =====================================================
# LOGIN / LOGOUT
# =====================================================

@app.get("/login", response_class=HTMLResponse)
def login(req: Request):

    if is_logged(req):
        return RedirectResponse("/dashboard", 302)

    return templates.TemplateResponse(
        "login.html",
        {"request": req}
    )


@app.post("/login")
def login_post(
    req: Request,
    email: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db)
):

    email = email.lower().strip()

    user = db.query(Business)\
        .filter(Business.admin_email == email)\
        .first()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": req, "error": "Invalid login"}
        )

    if not bcrypt.verify(password, user.admin_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": req, "error": "Invalid login"}
        )

    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": req, "error": "Account disabled"}
        )

    req.session["business_id"] = user.id

    logger.info(f"LOGIN | {email}")

    return RedirectResponse("/dashboard", 302)


@app.get("/logout")
def logout(req: Request):

    req.session.clear()

    return RedirectResponse("/login", 302)


# =====================================================
# SIGNUP
# =====================================================

@app.get("/signup", response_class=HTMLResponse)
def signup(req: Request):

    return templates.TemplateResponse(
        "signup.html",
        {"request": req}
    )


@app.post("/signup")
def signup_post(
    req: Request,

    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_type: str = Form(...),

    db=Depends(get_db)
):

    phone = clean_phone(phone)
    email = email.lower().strip()

    if not validate_password(password):

        return templates.TemplateResponse(
            "signup.html",
            {
                "request": req,
                "error": "Password must be 8+ chars with number & uppercase"
            }
        )


    if db.query(Business)\
        .filter(Business.admin_email == email)\
        .first():

        return templates.TemplateResponse(
            "signup.html",
            {
                "request": req,
                "error": "Email already registered"
            }
        )


    user = Business(

        name=name,
        whatsapp_number=phone,

        admin_email=email,
        admin_password=bcrypt.hash(password),

        business_type=business_type,

        plan="trial",
        is_active=True,

        chat_used=0,
        chat_limit=1000,

        onboarding_done=True,

        created_at=datetime.utcnow()
    )


    db.add(user)
    db.commit()


    req.session["business_id"] = user.id

    logger.info(f"SIGNUP | {email}")

    return RedirectResponse("/dashboard", 302)


# =====================================================
# DASHBOARD
# =====================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(req: Request, db=Depends(get_db)):

    if not is_logged(req):
        return RedirectResponse("/login", 302)

    user = get_user(req, db)

    if not user:
        req.session.clear()
        return RedirectResponse("/login", 302)


    bookings = db.query(Booking)\
        .filter(Booking.business_id == user.id)\
        .order_by(Booking.created_at.desc())\
        .all()


    analytics = {

        "conversations": user.chat_used or 0,

        "bookings": len(bookings),

        "interested": 0,

        "cancelled": len([
            b for b in bookings if b.status == "cancelled"
        ]),

        "conversion": (
            round((len(bookings) / max(user.chat_used, 1)) * 100, 1)
        )
    }


    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": req,
            "business": user,
            "bookings": bookings,
            "analytics": analytics,
            "now": datetime.utcnow()
        }
    )


# =====================================================
# ADMIN PANEL
# =====================================================

@app.get("/admin", response_class=HTMLResponse)
def admin(req: Request, db=Depends(get_db)):

    admin = require_admin(req, db)

    if not admin:
        return RedirectResponse("/dashboard", 302)


    users = db.query(Business)\
        .order_by(Business.created_at.desc())\
        .all()


    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": req,
            "admin": admin,
            "users": users
        }
    )


# =====================================================
# EXPORT BOOKINGS
# =====================================================

@app.get("/export/bookings")
def export(req: Request, db=Depends(get_db)):

    user = get_user(req, db)

    if not user:
        return RedirectResponse("/login", 302)


    bookings = db.query(Booking)\
        .filter(Booking.business_id == user.id)\
        .all()


    def gen():

        yield "Name,Phone,Date,Time,Status\n"

        for b in bookings:

            yield f"{b.name},{b.phone},{b.booking_date},{b.booking_time},{b.status}\n"


    return StreamingResponse(gen(), media_type="text/csv")


@app.get("/privacy", response_class=HTMLResponse)
def privacy(req: Request):
    return templates.TemplateResponse(
        "privacy.html",
        {"request": req, "now": datetime.utcnow()}
    )


@app.get("/terms", response_class=HTMLResponse)
def terms(req: Request):
    return templates.TemplateResponse(
        "terms.html",
        {"request": req, "now": datetime.utcnow()}
    )


@app.get("/refund", response_class=HTMLResponse)
def refund(req: Request):
    return templates.TemplateResponse(
        "refund.html",
        {"request": req, "now": datetime.utcnow()}
    )


@app.get("/about", response_class=HTMLResponse)
def about(req: Request):
    return templates.TemplateResponse(
        "about.html",
        {"request": req, "now": datetime.utcnow()}
    )

# =====================================================
# BILLING PAGE
# =====================================================

@app.get("/billing", response_class=HTMLResponse)
def billing(req: Request, db=Depends(get_db)):

    if not is_logged(req):
        return RedirectResponse("/login", 302)

    user = get_user(req, db)
    
    if not user:
        return RedirectResponse("/login", 302)

    return templates.TemplateResponse(
        "billing.html",
        {
            "request": req,
            "business": user,  # This was missing!
            "user": user,
            "razorpay_key": RAZORPAY_KEY
        }
    )

# =====================================================
# CONVERSATIONS PAGE
# =====================================================
@app.get("/conversations", response_class=HTMLResponse)
def conversations(req: Request, db=Depends(get_db)):
    if not is_logged(req):
        return RedirectResponse("/login", 302)
    
    user = get_user(req, db)
    if not user:
        return RedirectResponse("/login", 302)
    
    # Fetch bookings for analytics
    bookings = db.query(Booking)\
        .filter(Booking.business_id == user.id)\
        .all()
    
    # Calculate analytics (same as dashboard)
    analytics = {
        "conversations": user.chat_used or 0,
        "bookings": len(bookings),
        "interested": 0,
        "cancelled": len([b for b in bookings if b.status == "cancelled"]),
        "conversion": round((len(bookings) / max(user.chat_used, 1)) * 100, 1)
    }
    
    return templates.TemplateResponse(
        "conversations.html",
        {
            "request": req,
            "business": user,
            "analytics": analytics,  # This was missing!
            "bookings": bookings
        }
    )

# =====================================================
# BOOKINGS PAGE
# =====================================================
@app.get("/bookings", response_class=HTMLResponse)
def bookings_page(req: Request, db=Depends(get_db)):
    if not is_logged(req):
        return RedirectResponse("/login", 302)
    
    user = get_user(req, db)
    if not user:
        return RedirectResponse("/login", 302)
    
    # Fetch all bookings for this business
    bookings = db.query(Booking)\
        .filter(Booking.business_id == user.id)\
        .order_by(Booking.created_at.desc())\
        .all()
    
    # Calculate analytics (same as dashboard)
    analytics = {
        "conversations": user.chat_used or 0,
        "bookings": len(bookings),
        "interested": 0,
        "cancelled": len([b for b in bookings if b.status == "cancelled"]),
        "conversion": round((len(bookings) / max(user.chat_used, 1)) * 100, 1)
    }
    
    return templates.TemplateResponse(
        "bookings.html",
        {
            "request": req,
            "business": user,
            "analytics": analytics,  # This was missing!
            "bookings": bookings
        }
    )

# =====================================================
# SETTINGS PAGE
# =====================================================
@app.get("/settings", response_class=HTMLResponse)
def settings_page(req: Request, db=Depends(get_db)):
    if not is_logged(req):
        return RedirectResponse("/login", 302)
    
    user = get_user(req, db)
    if not user:
        return RedirectResponse("/login", 302)
    
    return templates.TemplateResponse(
        "settings.html",  # You'll need to create this template
        {
            "request": req,
            "business": user
        }
    )


# =====================================================
# CREATE PAYMENT ORDER
# =====================================================

@app.post("/api/create-order")
async def create_order(req: Request, db=Depends(get_db)):

    if not razorpay_client:
        return {"error": "Payment disabled"}


    data = await req.json()

    plan = data.get("plan")


    if plan not in PLANS:
        return {"error": "Invalid plan"}


    user = get_user(req, db)

    if not user:
        return {"error": "Auth"}


    amount = PLANS[plan]["price"] * 100


    order = razorpay_client.order.create({

        "amount": amount,

        "currency": "INR",

        "payment_capture": 1

    })


    return {

        "order_id": order["id"],

        "amount": amount,

        "key": RAZORPAY_KEY,

        "name": user.name,

        "email": user.admin_email,

        "phone": user.whatsapp_number
    }


# =====================================================
# PAYMENT SUCCESS
# =====================================================

@app.post("/api/payment-success")
async def payment_success(req: Request, db=Depends(get_db)):

    if not razorpay_client:
        return {"status": "disabled"}


    data = await req.json()


    user = get_user(req, db)

    if not user:
        return {"status": "failed"}


    try:

        razorpay_client.utility.verify_payment_signature(data)


        # UPGRADE PLAN

        user.plan = "pro"

        user.chat_limit = PLANS["pro"]["chats"]

        user.paid_until = datetime.utcnow() + timedelta(days=30)

        db.commit()


        logger.info(f"PAYMENT SUCCESS | {user.admin_email}")


        return {"status": "success"}


    except Exception as e:

        logger.error(f"PAYMENT FAIL | {str(e)}")

        return {"status": "failed"}

# =====================================================
# FORGOT PASSWORD PAGE
# =====================================================
@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password(req: Request):
    return templates.TemplateResponse(
        "forgot_password.html",
        {"request": req}
    )

@app.post("/forgot-password")
def forgot_password_post(req: Request, email: str = Form(...), db=Depends(get_db)):
    print(f"🔍 FORGOT PASSWORD REQUEST for email: {email}")
    print(f"🔍 SENDGRID_API_KEY exists: {bool(SENDGRID_API_KEY)}")
    print(f"🔍 FROM_EMAIL: {FROM_EMAIL}")
    print(f"🔍 BASE_URL: {BASE_URL}")
    
    # Check if email exists
    user = db.query(Business).filter(Business.admin_email == email).first()
    
    if user:
        print(f"✅ User found: {user.id} - {user.admin_email}")
        
        # Generate reset token
        import secrets
        reset_token = secrets.token_urlsafe(32)
        print(f"✅ Generated reset token: {reset_token[:10]}...")
        
        user.reset_token = reset_token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.commit()
        print(f"✅ Token saved to database")
        
        # Create reset link
        reset_link = f"{BASE_URL}/reset-password/{reset_token}"
        print(f"✅ Reset link: {reset_link}")
        
        # Send email
        print(f"📧 Attempting to send email to {user.admin_email}...")
        email_result = send_reset_email(user.admin_email, reset_link)
        print(f"📧 Email send result: {email_result}")
    else:
        print(f"❌ No user found with email: {email}")
    
    # Always show same message (security best practice)
    return templates.TemplateResponse(
        "forgot_password.html",
        {
            "request": req,
            "success": "If an account exists with this email, you will receive password reset instructions."
        }
    )

@app.get("/debug-razorpay")
def debug_razorpay():
    """Debug endpoint to check Razorpay configuration"""
    return {
        "key_id_present": bool(RAZORPAY_KEY),
        "key_id_value": RAZORPAY_KEY if RAZORPAY_KEY else "MISSING",
        "key_id_prefix": RAZORPAY_KEY[:15] + "..." if RAZORPAY_KEY and len(RAZORPAY_KEY) > 15 else RAZORPAY_KEY,
        "key_id_length": len(RAZORPAY_KEY) if RAZORPAY_KEY else 0,
        "secret_present": bool(RAZORPAY_SECRET),
        "secret_length": len(RAZORPAY_SECRET) if RAZORPAY_SECRET else 0,
        "client_initialized": razorpay_client is not None,
        "key_type": "test" if RAZORPAY_KEY and RAZORPAY_KEY.startswith("rzp_test") else 
                   "live" if RAZORPAY_KEY and RAZORPAY_KEY.startswith("rzp_live") else "unknown"
    }
# =====================================================
# RESET PASSWORD PAGE
# =====================================================
@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password(req: Request, token: str, db=Depends(get_db)):
    # Verify token
    user = db.query(Business).filter(
        Business.reset_token == token,
        Business.reset_token_expiry > datetime.utcnow()
    ).first()
    
    if not user:
        return templates.TemplateResponse(
            "reset_password.html",
            {
                "request": req,
                "error": "Invalid or expired reset link. Please request a new one."
            }
        )
    
    return templates.TemplateResponse(
        "reset_password.html",
        {
            "request": req,
            "token": token,
            "valid_token": True
        }
    )

@app.post("/reset-password/{token}")
def reset_password_post(
    req: Request,
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
    db=Depends(get_db)
):
    # Verify token
    user = db.query(Business).filter(
        Business.reset_token == token,
        Business.reset_token_expiry > datetime.utcnow()
    ).first()
    
    if not user:
        return templates.TemplateResponse(
            "reset_password.html",
            {
                "request": req,
                "error": "Invalid or expired reset link. Please request a new one."
            }
        )
    
    # Validate passwords
    if password != confirm_password:
        return templates.TemplateResponse(
            "reset_password.html",
            {
                "request": req,
                "token": token,
                "error": "Passwords do not match."
            }
        )
    
    # Validate password strength
    if not validate_password(password):
        return templates.TemplateResponse(
            "reset_password.html",
            {
                "request": req,
                "token": token,
                "error": "Password must be 8+ characters with at least 1 uppercase letter and 1 number."
            }
        )
    
    # Update password
    user.admin_password = bcrypt.hash(password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    
    return templates.TemplateResponse(
        "reset_password.html",
        {
            "request": req,
            "success": "Password reset successful! You can now login with your new password."
        }
    )

@app.get("/test-sendgrid")
def test_sendgrid():
    """Test SendGrid connectivity and configuration"""
    results = {
        "sendgrid_key_exists": bool(SENDGRID_API_KEY),
        "sendgrid_key_length": len(SENDGRID_API_KEY) if SENDGRID_API_KEY else 0,
        "sendgrid_key_prefix": SENDGRID_API_KEY[:15] + "..." if SENDGRID_API_KEY else None,
        "from_email": FROM_EMAIL,
        "base_url": BASE_URL,
    }
    
    # Test direct API call
    try:
        import requests
        print("Testing SendGrid API directly...")
        
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # This is just a test to verify the API key works - won't actually send
        response = requests.get("https://api.sendgrid.com/v3/scopes", headers=headers)
        results["api_key_valid"] = response.status_code == 200
        results["api_response"] = response.status_code
        results["api_scopes"] = response.json() if response.status_code == 200 else None
        
    except Exception as e:
        results["api_test_error"] = str(e)
    
    return results

# =====================================================
# HEALTH
# =====================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "version": "9.0",
        "time": datetime.utcnow().isoformat()
    }
