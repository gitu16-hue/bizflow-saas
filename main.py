# =====================================================
# BIZFLOW AI - ENTERPRISE SAAS PLATFORM
# VERSION 10.0 - PRODUCTION READY
# =====================================================

import sys
import traceback

try:
    # ================= PATCHES =================
    try:
        import patch_pydantic
        print("✅ Pydantic patch loaded successfully")
    except ImportError:
        print("⚠️ Pydantic patch not found, continuing without it")
    except Exception as e:
        print(f"⚠️ Error loading patch: {e}")

    # ================= STANDARD LIBRARY =================
    import os
    import re
    import logging
    import secrets
    import hmac
    import hashlib
    from datetime import datetime, timedelta
    from typing import Optional, Dict, Any, List, Union
    from contextlib import contextmanager
    import json
    import traceback as tb
    from functools import wraps

    # ================= THIRD PARTY =================
    from dotenv import load_dotenv
    load_dotenv()

    # FastAPI & Related
    from fastapi import FastAPI, Request, Form, Depends, Response, HTTPException, status, Cookie
    from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    from starlette.middleware.sessions import SessionMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware

    # Security
    from passlib.hash import bcrypt
    import bcrypt as bcrypt_lib

    # Database
    from database import SessionLocal, engine
    from models import Base, Business, Booking, Payment, AuditLog, Conversation

    # Email
    import sendgrid
    from sendgrid.helpers.mail import Mail

    # Payments
    import razorpay

    # Utilities
    import pytz
    import aiofiles
    import csv
    from io import StringIO
    from twilio.twiml.messaging_response import MessagingResponse
    from sqlalchemy.exc import SQLAlchemyError, IntegrityError

    print("✅ Starting BizFlow AI...")
    print(f"Python version: {sys.version}")

    # =====================================================
    # CONFIGURATION & ENVIRONMENT
    # =====================================================
    APP_NAME = "BizFlow AI"
    APP_VERSION = "10.1"
    BASE_URL = os.getenv("BASE_URL", "https://bizflowai.online")
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    DEBUG = ENVIRONMENT == "development"

    # Email Configuration
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@bizflowai.online")
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@bizflowai.online")

    # Payment Configuration
    RAZORPAY_KEY = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    # WhatsApp Configuration
    WHATSAPP_WEBHOOK_TOKEN = os.getenv("WHATSAPP_WEBHOOK_TOKEN", secrets.token_urlsafe(16))

    # Rate Limiting
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_TIMEOUT_MINUTES = 15

    # =====================================================
    # PLANS CONFIGURATION
    # =====================================================
    PLANS = {
        "starter": {
            "name": "Starter",
            "price": 999,
            "chats": 300,
            "features": ["WhatsApp Bot", "300 Chats/Month", "Booking System", "Basic Analytics", "Email Support"]
        },
        "pro": {
            "name": "Pro",
            "price": 2499,
            "chats": 999999,
            "features": ["Unlimited Chats", "Advanced AI", "Auto Reminders", "Calendar Sync", "Priority Support", "Lead Optimization"]
        }
    }

    # [Rest of your code continues here... ALL OF IT must be inside the try block]

except Exception as e:
    print(f"❌ FATAL STARTUP ERROR: {str(e)}")
    traceback.print_exc()
    sys.exit(1)
# =====================================================
# LOGGING CONFIGURATION
# =====================================================

class CustomFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""
    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: grey,
        logging.INFO: blue,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red
    }

    def format(self, record):
        log_fmt = f"{self.FORMATS.get(record.levelno)}%(asctime)s - %(name)s - %(levelname)s - %(message)s{self.reset}"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# File handler for all logs
file_handler = logging.FileHandler("logs/bizflow.log")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Console handler with colors
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
console_handler.setFormatter(CustomFormatter())

# Error file handler
error_handler = logging.FileHandler("logs/error.log")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(file_formatter)

# Setup logger
logger = logging.getLogger("bizflow")
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.addHandler(error_handler)

# =====================================================
# FASTAPI APP INITIALIZATION
# =====================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Enterprise WhatsApp Business Automation Platform",
    docs_url="/api/docs" if DEBUG else None,
    redoc_url="/api/redoc" if DEBUG else None,
    openapi_url="/api/openapi.json" if DEBUG else None,
)

# Security Middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["bizflowai.online", "*.railway.app", "localhost", "127.0.0.1"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bizflowai.online",
        "http://localhost:8001",
        "http://127.0.0.1:8001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 24 * 14,  # 14 days
    same_site="lax",
    https_only=ENVIRONMENT == "production",
)

# Add GZip compression for better performance
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Create database tables
Base.metadata.create_all(bind=engine)

# =====================================================
# DATABASE DEPENDENCY
# =====================================================

@contextmanager
def get_db_context():
    """Context manager for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db():
    """FastAPI dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =====================================================
# PAYMENT CLIENT INITIALIZATION
# =====================================================

razorpay_client = None
if RAZORPAY_KEY and RAZORPAY_SECRET:
    try:
        razorpay_client = razorpay.Client(
            auth=(RAZORPAY_KEY.strip(), RAZORPAY_SECRET.strip())
        )
        logger.info("✅ Razorpay client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Razorpay client initialization failed: {str(e)}")
        razorpay_client = None

# =====================================================
# DECORATORS & MIDDLEWARE
# =====================================================

def login_required(func):
    """Decorator to require login"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not is_logged(request):
            request.session["next"] = request.url.path
            return RedirectResponse("/login", 302)
        return await func(request, *args, **kwargs)
    return wrapper

def admin_required(func):
    """Decorator to require admin privileges"""
    @wraps(func)
    async def wrapper(request: Request, db=Depends(get_db), *args, **kwargs):
        if not is_logged(request):
            request.session["next"] = request.url.path
            return RedirectResponse("/login", 302)
        
        user = get_user(request, db)
        if not user or not user.is_admin:
            return RedirectResponse("/dashboard", 302)
        
        return await func(request, db, *args, **kwargs)
    return wrapper

# =====================================================
# SECURITY UTILITIES
# =====================================================

def hash_password(password: str) -> str:
    """Hash password with bcrypt"""
    return bcrypt.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.verify(password, hashed)

def generate_token() -> str:
    """Generate secure random token"""
    return secrets.token_urlsafe(32)

def validate_password_strength(password: str) -> tuple:
    """
    Validate password strength
    Returns (is_valid, message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"

def sanitize_input(text: str) -> str:
    """Sanitize user input"""
    if not text:
        return ""
    # Remove any potential malicious characters
    return re.sub(r'[<>\'"]', '', text)

# =====================================================
# AUTHENTICATION HELPERS
# =====================================================

def is_logged(req: Request) -> bool:
    """Check if user is logged in"""
    return bool(req.session.get("business_id"))

def get_user(req: Request, db):
    """Get current user from session"""
    bid = req.session.get("business_id")
    if not bid:
        return None
    return db.query(Business).get(bid)

def require_admin(req: Request, db):
    """Check if user is admin"""
    user = get_user(req, db)
    if not user or not user.is_admin:
        return None
    return user

def log_audit(user_id: int, action: str, details: dict = None, db=None):
    """Log audit event"""
    if db:
        try:
            audit = AuditLog(
                user_id=user_id,
                action=action,
                details=details or {},
                created_at=datetime.utcnow()
            )
            db.add(audit)
            db.commit()
        except Exception as e:
            logger.error(f"Audit log error: {str(e)}")

# =====================================================
# RATE LIMITING MIDDLEWARE
# =====================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = datetime.utcnow()
        
        # Clean old entries
        self.requests = {
            ip: times for ip, times in self.requests.items()
            if times and (now - times[-1]).seconds < self.window_seconds
        }
        
        # Check rate limit
        if client_ip in self.requests:
            if len(self.requests[client_ip]) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"error": "Too many requests", "retry_after": self.window_seconds}
                )
            self.requests[client_ip].append(now)
        else:
            self.requests[client_ip] = [now]
        
        return await call_next(request)

# Enable rate limiting in production
if ENVIRONMENT == "production":
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# =====================================================
# EMAIL SERVICE
# =====================================================

class EmailService:
    """Enterprise email service with templates"""
    
    @staticmethod
    async def send_email(to_email: str, subject: str, template_name: str, context: dict = None) -> bool:
        """Send email using template"""
        if not SENDGRID_API_KEY:
            logger.error("SendGrid API key not configured")
            return False
        
        try:
            # Load email template
            template = EmailService._get_template(template_name, context or {})
            
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=template
            )
            
            sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            
            if response.status_code == 202:
                logger.info(f"✅ Email sent to {to_email}: {subject}")
                return True
            else:
                logger.error(f"❌ Email failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Email error: {str(e)}")
            return False
    
    @staticmethod
    def _get_template(name: str, context: dict) -> str:
        """Get email template with context"""
        templates = {
            "welcome": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background: linear-gradient(135deg, #2563eb, #60a5fa); color: white; padding: 40px 20px; text-align: center; }}
                        .content {{ background: white; padding: 40px 20px; }}
                        .button {{ display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 12px 30px; border-radius: 8px; font-weight: 600; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to BizFlow AI!</h1>
                        </div>
                        <div class="content">
                            <h2>Hello {context.get('name', 'there')}!</h2>
                            <p>Thank you for joining BizFlow AI. We're excited to help you automate your business with WhatsApp.</p>
                            <p>Get started by visiting your dashboard:</p>
                            <div style="text-align: center;">
                                <a href="{BASE_URL}/dashboard" class="button">Go to Dashboard</a>
                            </div>
                        </div>
                    </div>
                </body>
                </html>
            """,
            "reset_password": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background: linear-gradient(135deg, #2563eb, #60a5fa); color: white; padding: 40px 20px; text-align: center; }}
                        .content {{ background: white; padding: 40px 20px; }}
                        .button {{ display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 12px 30px; border-radius: 8px; font-weight: 600; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Reset Your Password</h1>
                        </div>
                        <div class="content">
                            <p>Click the button below to reset your password:</p>
                            <div style="text-align: center;">
                                <a href="{context.get('reset_link')}" class="button">Reset Password</a>
                            </div>
                            <p>Or copy this link: {context.get('reset_link')}</p>
                            <p>This link expires in 24 hours.</p>
                        </div>
                    </div>
                </body>
                </html>
            """,
            "payment_success": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background: linear-gradient(135deg, #10b981, #34d399); color: white; padding: 40px 20px; text-align: center; }}
                        .content {{ background: white; padding: 40px 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Payment Successful!</h1>
                        </div>
                        <div class="content">
                            <h2>Thank you for upgrading to {context.get('plan', 'Pro')}!</h2>
                            <p>Amount: ₹{context.get('amount')}</p>
                            <p>Transaction ID: {context.get('payment_id')}</p>
                            <p>Your plan is now active until {context.get('valid_until')}.</p>
                        </div>
                    </div>
                </body>
                </html>
            """
        }
        return templates.get(name, "<h1>Notification</h1><p>{}</p>".format(context))

# =====================================================
# WHATSAPP BOT ENGINE
# =====================================================

class WhatsAppBot:
    """Advanced WhatsApp bot with NLP capabilities"""
    
    @staticmethod
    def clean_phone(phone: str) -> str:
        """Clean and format phone number"""
        if not phone:
            return ""
        phone = re.sub(r'[^\d+]', '', phone.replace("whatsapp:", ""))
        if len(phone) == 10:
            phone = "91" + phone
        return phone
    
    @staticmethod
    def get_industry_menu(business) -> str:
        """Get dynamic menu based on industry"""
        menus = {
            "restaurant": """
👋 Welcome to *{name}* 🍽️

1️⃣ Book Table
2️⃣ View Menu
3️⃣ Location & Hours
4️⃣ Special Offers
5️⃣ Contact Us
6️⃣ Exit

Reply with number 👇
""",
            "clinic": """
👋 Welcome to *{name}* 🏥

1️⃣ Book Appointment
2️⃣ Doctor Availability
3️⃣ Fees & Insurance
4️⃣ Location
5️⃣ Emergency Contact
6️⃣ Exit

Reply with number 👇
""",
            "salon": """
👋 Welcome to *{name}* 💇

1️⃣ Book Appointment
2️⃣ Services & Prices
3️⃣ Stylists
4️⃣ Location
5️⃣ Offers
6️⃣ Exit

Reply with number 👇
""",
            "gym": """
👋 Welcome to *{name}* 💪

1️⃣ Book Session
2️⃣ Membership Plans
3️⃣ Class Schedule
4️⃣ Trainer Info
5️⃣ Location
6️⃣ Exit

Reply with number 👇
""",
            "realestate": """
👋 Welcome to *{name}* 🏠

1️⃣ Schedule Visit
2️⃣ Property Listings
3️⃣ EMI Calculator
4️⃣ Contact Agent
5️⃣ Location
6️⃣ Exit

Reply with number 👇
"""
        }
        
        industry = business.business_type.lower()
        menu = menus.get(industry, """
👋 Welcome to *{name}* 🚀

1️⃣ Book Appointment
2️⃣ Services
3️⃣ Location
4️⃣ Contact
5️⃣ Pricing
6️⃣ Exit

Reply with number 👇
""")
        
        return menu.format(name=business.name)
    
    @staticmethod
    def parse_booking(text: str) -> Optional[Dict]:
        """Parse natural language booking"""
        try:
            text = text.lower().strip()
            
            # Common patterns
            patterns = [
                r'(\d{1,2})[/-](\d{1,2})\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'tomorrow\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'today\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    groups = match.groups()
                    
                    # Handle different patterns
                    if len(groups) == 6:  # Full date pattern
                        day, month, hour, minute, ampm, name = groups
                        month_num = WhatsAppBot._month_to_number(month)
                        date = f"{day.zfill(2)}-{month_num}-{datetime.now().year}"
                    elif len(groups) == 4:  # Today/tomorrow pattern
                        hour, minute, ampm, name = groups
                        date = (datetime.now() + timedelta(days=1 if 'tomorrow' in text else 0)).strftime('%d-%m-%Y')
                    else:
                        continue
                    
                    # Format time
                    hour = int(hour)
                    if ampm and ampm.lower() == 'pm' and hour < 12:
                        hour += 12
                    elif ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0
                    
                    time = f"{hour:02d}:{minute or '00'}"
                    
                    return {
                        "date": date,
                        "time": time,
                        "name": name.strip().title()
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Booking parse error: {str(e)}")
            return None
    
    @staticmethod
    def _month_to_number(month: str) -> str:
        """Convert month name to number"""
        months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        return months.get(month[:3].lower(), '01')
    
    @staticmethod
    def process_message(phone: str, message: str, business, db) -> str:
        """Process incoming WhatsApp message"""
        message = message.strip()
        lower_msg = message.lower()
        
        state = business.flow_state or "start"
        
        # Reset command
        if lower_msg in ["reset", "restart", "help", "menu"]:
            business.flow_state = "menu"
            db.commit()
            return WhatsAppBot.get_industry_menu(business)
        
        # Handle based on state
        if state == "start" or state == "menu":
            return WhatsAppBot._handle_menu(message, business, db)
        elif state == "booking":
            return WhatsAppBot._handle_booking(message, phone, business, db)
        else:
            business.flow_state = "menu"
            db.commit()
            return WhatsAppBot.get_industry_menu(business)
    
    @staticmethod
    def _handle_menu(message: str, business, db) -> str:
        """Handle menu selection"""
        options = {
            '1': 'booking',
            '2': 'services',
            '3': 'location',
            '4': 'contact',
            '5': 'pricing',
            '6': 'exit'
        }
        
        if message in options:
            if options[message] == 'booking':
                business.flow_state = "booking"
                db.commit()
                return (
                    "📅 Please provide booking details:\n\n"
                    "Examples:\n"
                    "• 15 Mar 3PM John Doe\n"
                    "• 15/03 15:30 John Doe\n"
                    "• tomorrow 4PM John Doe\n\n"
                    "Type 'cancel' to go back"
                )
            elif options[message] == 'services':
                return WhatsAppBot._get_services(business)
            elif options[message] == 'location':
                return WhatsAppBot._get_location(business)
            elif options[message] == 'contact':
                return WhatsAppBot._get_contact(business)
            elif options[message] == 'pricing':
                return WhatsAppBot._get_pricing(business)
            elif options[message] == 'exit':
                business.flow_state = "start"
                db.commit()
                return "👋 Thank you for visiting! Type 'hi' to start again."
        
        return "❌ Invalid option. Please reply with a number (1-6)."
    
    @staticmethod
    def _handle_booking(message: str, phone: str, business, db) -> str:
        """Handle booking process"""
        if message.lower() in ['cancel', 'back', 'exit']:
            business.flow_state = "menu"
            db.commit()
            return "❌ Booking cancelled.\n\n" + WhatsAppBot.get_industry_menu(business)
        
        booking_data = WhatsAppBot.parse_booking(message)
        if not booking_data:
            return (
                "❌ Could not understand. Please use format:\n"
                "• 15 Mar 3PM John Doe\n"
                "• 15/03 15:30 John Doe\n"
                "• tomorrow 4PM John Doe\n\n"
                "Type 'cancel' to go back"
            )
        
        # Create booking
        booking = Booking(
            business_id=business.id,
            name=booking_data['name'],
            phone=phone,
            booking_date=booking_data['date'],
            booking_time=booking_data['time'],
            status='pending'
        )
        db.add(booking)
        business.flow_state = "menu"
        business.chat_used = (business.chat_used or 0) + 1
        db.commit()
        
        return f"""
✅ Booking Confirmed!

👤 {booking_data['name']}
📅 {booking_data['date']}
⏰ {booking_data['time']}

We'll send you a reminder before your appointment.

Type 'menu' for main menu 👋
"""
    
    @staticmethod
    def _get_services(business) -> str:
        """Get services based on industry"""
        services = {
            "restaurant": "🍽️ Our Services:\n• Dine-in\n• Takeaway\n• Delivery\n• Private Events",
            "salon": "💇 Our Services:\n• Haircut\n• Styling\n• Coloring\n• Facial\n• Manicure/Pedicure",
            "gym": "💪 Our Services:\n• Personal Training\n• Group Classes\n• Yoga\n• CrossFit\n• Nutrition Counseling",
            "clinic": "🏥 Our Services:\n• General Consultation\n• Specialist Visit\n• Health Checkup\n• Vaccination",
        }
        return services.get(business.business_type.lower(), "📋 Check our website for complete services.")
    
    @staticmethod
    def _get_location(business) -> str:
        """Get business location"""
        addr = business.address or "Main Location"
        return f"""
📍 {addr}

🕒 Business Hours:
Monday - Friday: 9AM - 8PM
Saturday: 10AM - 6PM
Sunday: Closed
"""
    
    @staticmethod
    def _get_contact(business) -> str:
        """Get contact information"""
        return f"""
📞 Contact Us:
Phone: {business.whatsapp_number}
Email: {business.admin_email}

For urgent inquiries, please call during business hours.
"""
    
    @staticmethod
    def _get_pricing(business) -> str:
        """Get pricing information"""
        return """
💰 Pricing:

Basic consultation: ₹500
Premium services: Starting at ₹1000

Check our website for detailed pricing.
"""

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
async def health_check(db=Depends(get_db)):
    """Health check endpoint with database verification"""
    try:
        from sqlalchemy import text
        
        # Test database connection - FIXED with text()
        db.execute(text("SELECT 1")).first()
        db_status = "healthy"
        
        # Check critical services
        services = {
            "razorpay": "configured" if razorpay_client else "not configured",
            "sendgrid": "configured" if SENDGRID_API_KEY else "not configured",
            "database": "connected"
        }
        
        return {
            "status": "ok",
            "version": APP_VERSION,
            "environment": ENVIRONMENT,
            "timestamp": datetime.utcnow().isoformat(),
            "services": services
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# =====================================================
# HOME PAGE
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home(req: Request):
    """Home page"""
    try:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": req,
                "logged": is_logged(req),
                "year": datetime.now().year
            }
        )
    except Exception as e:
        logger.error(f"Home page error: {str(e)}")
        return templates.TemplateResponse(
            "500.html",
            {"request": req, "error": "An error occurred loading the page"},
            status_code=500
        )

# =====================================================
# AUTHENTICATION ROUTES
# =====================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(req: Request):
    """Login page"""
    if is_logged(req):
        return RedirectResponse("/dashboard", 302)
    
    error = req.session.pop("login_error", None)
    return templates.TemplateResponse(
        "login.html",
        {"request": req, "error": error}
    )

@app.post("/login")
async def login(
    req: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db=Depends(get_db)
):
    """Login handler"""
    try:
        email = email.lower().strip()
        user = db.query(Business).filter(Business.admin_email == email).first()
        
        if not user or not verify_password(password, user.admin_password):
            logger.warning(f"Failed login attempt for email: {email}")
            req.session["login_error"] = "Invalid email or password"
            return RedirectResponse("/login", 302)
        
        if not user.is_active:
            logger.warning(f"Inactive account login attempt: {email}")
            req.session["login_error"] = "Account is disabled. Please contact support."
            return RedirectResponse("/login", 302)
        
        # Set session
        req.session["business_id"] = user.id
        if remember:
            req.session["max_age"] = 60 * 60 * 24 * 30  # 30 days
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ User logged in: {email}")
        
        # Redirect to intended page or dashboard
        next_url = req.session.pop("next", "/dashboard")
        return RedirectResponse(next_url, 302)
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        req.session["login_error"] = "An error occurred. Please try again."
        return RedirectResponse("/login", 302)

@app.get("/logout")
async def logout(req: Request):
    """Logout handler"""
    user_id = req.session.get("business_id")
    req.session.clear()
    logger.info(f"User logged out: {user_id}")
    return RedirectResponse("/", 302)

@app.get("/test-template")
async def test_template(req: Request):
    """Simple test route"""
    try:
        return templates.TemplateResponse("test.html", {"request": req})
    except Exception as e:
        return {"error": str(e)}
# =====================================================
# SIGNUP ROUTES
# =====================================================

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(req: Request, plan: str = None):
    """Signup page"""
    if is_logged(req):
        return RedirectResponse("/dashboard", 302)
    
    return templates.TemplateResponse(
        "signup.html",
        {
            "request": req,
            "plan": plan,
            "plans": PLANS
        }
    )

@app.post("/signup")
async def signup(
    req: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_type: str = Form(...),
    db=Depends(get_db)
):
    """Signup handler"""
    try:
        phone = WhatsAppBot.clean_phone(phone)
        email = email.lower().strip()
        name = sanitize_input(name)
        
        # Validate password strength
        is_valid, msg = validate_password_strength(password)
        if not is_valid:
            return templates.TemplateResponse(
                "signup.html",
                {
                    "request": req,
                    "error": msg,
                    "plans": PLANS
                }
            )
        
        # Check if user exists
        existing = db.query(Business).filter(
            (Business.admin_email == email) | (Business.whatsapp_number == phone)
        ).first()
        
        if existing:
            return templates.TemplateResponse(
                "signup.html",
                {
                    "request": req,
                    "error": "Email or phone already registered",
                    "plans": PLANS
                }
            )
        
        # Create user
        user = Business(
            name=name,
            whatsapp_number=phone,
            admin_email=email,
            admin_password=hash_password(password),
            business_type=business_type,
            plan="trial",
            is_active=True,
            chat_used=0,
            chat_limit=1000,
            onboarding_done=False,
            created_at=datetime.utcnow(),
            trial_ends_at=datetime.utcnow() + timedelta(days=7)
        )
        
        db.add(user)
        db.commit()
        
        # Set session
        req.session["business_id"] = user.id
        
        # Send welcome email (async)
        await EmailService.send_email(
            email,
            "Welcome to BizFlow AI!",
            "welcome",
            {"name": name}
        )
        
        logger.info(f"✅ New user signed up: {email}")
        
        return RedirectResponse("/onboarding", 302)
        
    except IntegrityError:
        logger.error(f"Signup integrity error for email: {email}")
        db.rollback()
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": req,
                "error": "An account with this email already exists",
                "plans": PLANS
            }
        )
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        db.rollback()
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": req,
                "error": "An error occurred. Please try again.",
                "plans": PLANS
            }
        )

# =====================================================
# DASHBOARD
# =====================================================

@app.get("/dashboard", response_class=HTMLResponse)
@login_required
async def dashboard(req: Request, db=Depends(get_db)):
    """User dashboard"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get real data
        bookings = db.query(Booking).filter(Booking.business_id == user.id).order_by(Booking.created_at.desc()).limit(5).all()
        total_bookings = len(bookings)
        
        analytics = {
            "conversations": user.chat_used or 0,
            "bookings": total_bookings,
            "conversion": 0
        }
        
        # Use the simple template
        return templates.TemplateResponse(
            "dashboard_simple.html",
            {
                "request": req,
                "business": user,
                "bookings": bookings,
                "analytics": analytics
            }
        )
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return HTMLResponse(f"<h1>Error</h1><pre>{str(e)}</pre>")
# =====================================================
# ONBOARDING
# =====================================================

@app.get("/onboarding", response_class=HTMLResponse)
@login_required
async def onboarding(req: Request, db=Depends(get_db)):
    """Onboarding wizard for new users"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        if user.onboarding_done:
            return RedirectResponse("/dashboard", 302)
        
        # Use the simple template
        return templates.TemplateResponse(
            "onboarding_simple.html",
            {
                "request": req,
                "business": user
            }
        )
    except Exception as e:
        logger.error(f"Onboarding error: {str(e)}")
        return HTMLResponse(f"<h1>Error</h1><pre>{str(e)}</pre>")

# =====================================================
# WHATSAPP WEBHOOK
# =====================================================

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request, db=Depends(get_db)):
    """WhatsApp webhook handler"""
    try:
        form = await req.form()
        raw_phone = form.get("From", "")
        message = form.get("Body", "")
        
        phone = WhatsAppBot.clean_phone(raw_phone)
        logger.info(f"📱 WhatsApp | {phone} | {message}")
        
        # Find business by phone number
        business = db.query(Business)\
            .filter(Business.whatsapp_number == phone)\
            .first()
        
        if not business:
            reply = (
                "👋 Welcome to BizFlow AI!\n\n"
                "This WhatsApp number is not registered with any business.\n\n"
                "If you're a business owner, sign up at:\n"
                f"{BASE_URL}/signup\n\n"
                "If you're a customer, please contact the business directly."
            )
        else:
            # Check if business is active and within limits
            if not business.is_active:
                reply = "❌ This business account is currently inactive. Please contact support."
            elif business.chat_used >= business.chat_limit:
                reply = (
                    "❌ Monthly chat limit reached.\n\n"
                    f"Your plan: {business.plan.upper()}\n"
                    f"Limit: {business.chat_limit} chats/month\n\n"
                    "Please upgrade your plan to continue."
                )
            else:
                # Process message
                reply = WhatsAppBot.process_message(phone, message, business, db)
        
        # Twilio response
        resp = MessagingResponse()
        resp.message(reply)
        
        return Response(
            content=str(resp),
            media_type="application/xml"
        )
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {str(e)}")
        resp = MessagingResponse()
        resp.message("❌ An error occurred. Please try again later.")
        return Response(
            content=str(resp),
            media_type="application/xml",
            status_code=500
        )

# =====================================================
# PAYMENT ROUTES
# =====================================================

@app.get("/billing", response_class=HTMLResponse)
@login_required
async def billing_page(req: Request, db=Depends(get_db)):
    """Billing and subscription page"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get payment history
        payments = db.query(Payment)\
            .filter(Payment.business_id == user.id)\
            .order_by(Payment.created_at.desc())\
            .all()
        
        return templates.TemplateResponse(
            "billing.html",
            {
                "request": req,
                "business": user,
                "payments": payments,
                "razorpay_key": RAZORPAY_KEY,
                "plans": PLANS,
                "current_plan": user.plan
            }
        )
    except Exception as e:
        logger.error(f"Billing page error: {str(e)}")
        return templates.TemplateResponse(
            "500.html",
            {"request": req, "error": "An error occurred loading the billing page"},
            status_code=500
        )

@app.post("/api/create-order")
async def create_order(req: Request, db=Depends(get_db)):
    """Create Razorpay order"""
    try:
        if not razorpay_client:
            logger.error("Razorpay client not initialized")
            return JSONResponse(
                status_code=503,
                content={"error": "Payment service temporarily unavailable"}
            )
        
        user = get_user(req, db)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required"}
            )
        
        data = await req.json()
        plan = data.get("plan")
        
        if plan not in PLANS:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid plan selected"}
            )
        
        amount = PLANS[plan]["price"] * 100  # Convert to paise
        
        # Create Razorpay order
        order = razorpay_client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": f"order_{user.id}_{int(datetime.utcnow().timestamp())}",
            "payment_capture": 1,
            "notes": {
                "business_id": str(user.id),
                "business_email": user.admin_email,
                "plan": plan
            }
        })
        
        logger.info(f"✅ Order created: {order['id']} for user {user.id}")
        
        return {
            "order_id": order["id"],
            "amount": amount,
            "currency": "INR",
            "key": RAZORPAY_KEY,
            "name": user.name,
            "email": user.admin_email,
            "phone": user.whatsapp_number,
            "plan": plan
        }
        
    except razorpay.errors.BadRequestError as e:
        logger.error(f"Razorpay error: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"error": "Payment service error. Please try again."}
        )
    except Exception as e:
        logger.error(f"Order creation error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to create order. Please try again."}
        )

@app.post("/api/payment-success")
async def payment_success(req: Request, db=Depends(get_db)):
    """Handle successful payment"""
    try:
        if not razorpay_client:
            logger.error("Razorpay client not initialized")
            return {"status": "error", "message": "Payment service unavailable"}
        
        user = get_user(req, db)
        if not user:
            return {"status": "error", "message": "User not authenticated"}
        
        data = await req.json()
        
        # Verify signature
        razorpay_client.utility.verify_payment_signature(data)
        
        # Get payment details
        payment_id = data.get('razorpay_payment_id')
        order_id = data.get('razorpay_order_id')
        
        # Fetch order details
        order = razorpay_client.order.fetch(order_id)
        amount_paid = order['amount']
        notes = order.get('notes', {})
        plan = notes.get('plan', 'pro')
        
        # Determine plan from amount if not in notes
        if plan not in PLANS:
            if amount_paid == PLANS["starter"]["price"] * 100:
                plan = "starter"
            else:
                plan = "pro"
        
        # Record payment
        payment = Payment(
            business_id=user.id,
            payment_id=payment_id,
            order_id=order_id,
            amount=amount_paid / 100,
            currency="INR",
            status="success",
            plan=plan,
            payment_data=data
        )
        db.add(payment)
        
        # Upgrade user plan
        old_plan = user.plan
        user.plan = plan
        user.chat_limit = PLANS[plan]["chats"]
        user.paid_until = datetime.utcnow() + timedelta(days=30)
        db.commit()
        
        logger.info(f"✅ Payment success: {payment_id} | User: {user.id} | Plan: {plan}")
        
        # Send confirmation email (async)
        await EmailService.send_email(
            user.admin_email,
            "Payment Successful!",
            "payment_success",
            {
                "plan": plan.upper(),
                "amount": amount_paid / 100,
                "payment_id": payment_id,
                "valid_until": user.paid_until.strftime('%d %B %Y')
            }
        )
        
        return {
            "status": "success",
            "plan": plan,
            "message": "Your plan has been upgraded successfully!"
        }
        
    except razorpay.errors.SignatureVerificationError:
        logger.error(f"Payment signature verification failed")
        return {"status": "error", "message": "Payment verification failed"}
    except Exception as e:
        logger.error(f"Payment success error: {str(e)}")
        return {"status": "error", "message": "An error occurred processing your payment"}

@app.post("/api/razorpay-webhook")
async def razorpay_webhook(req: Request):
    """Razorpay webhook handler for async events"""
    if not RAZORPAY_WEBHOOK_SECRET:
        return {"status": "webhook disabled"}
    
    try:
        # Verify webhook signature
        body = await req.body()
        signature = req.headers.get("x-razorpay-signature")
        
        expected_signature = hmac.new(
            key=RAZORPAY_WEBHOOK_SECRET.encode(),
            msg=body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid webhook signature")
            return JSONResponse(status_code=400, content={"error": "Invalid signature"})
        
        # Parse webhook
        data = json.loads(body)
        event = data.get("event")
        
        logger.info(f"📡 Razorpay webhook: {event}")
        
        # Handle webhook events in a background task
        # For now, just acknowledge
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# =====================================================
# ADMIN ROUTES
# =====================================================

@app.get("/admin", response_class=HTMLResponse)
@admin_required
async def admin_dashboard(req: Request, db=Depends(get_db)):
    """Admin dashboard"""
    try:
        # Get all users
        users = db.query(Business)\
            .order_by(Business.created_at.desc())\
            .all()
        
        # Get stats
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        total_revenue = sum([p.amount for p in db.query(Payment).filter(Payment.status == "success").all()])
        total_bookings = db.query(Booking).count()
        
        # Recent payments
        recent_payments = db.query(Payment)\
            .order_by(Payment.created_at.desc())\
            .limit(10)\
            .all()
        
        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": req,
                "users": users,
                "stats": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "inactive_users": total_users - active_users,
                    "total_revenue": total_revenue,
                    "total_bookings": total_bookings,
                    "pro_users": len([u for u in users if u.plan == "pro"]),
                    "trial_users": len([u for u in users if u.plan == "trial"])
                },
                "recent_payments": recent_payments
            }
        )
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/admin/toggle-user/{user_id}")
@admin_required
async def toggle_user(user_id: int, req: Request, db=Depends(get_db)):
    """Enable/disable user account"""
    try:
        user = db.query(Business).get(user_id)
        if not user:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        
        user.is_active = not user.is_active
        db.commit()
        
        logger.info(f"Admin toggled user {user_id} to {user.is_active}")
        
        return {"status": "success", "is_active": user.is_active}
        
    except Exception as e:
        logger.error(f"Toggle user error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to update user"})

@app.post("/admin/make-admin/{user_id}")
@admin_required
async def make_admin(user_id: int, req: Request, db=Depends(get_db)):
    """Make user admin"""
    try:
        user = db.query(Business).get(user_id)
        if not user:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        
        user.is_admin = True
        db.commit()
        
        logger.info(f"Admin made user {user_id} an admin")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Make admin error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to update user"})

# =====================================================
# USER ROUTES
# =====================================================

@app.get("/settings", response_class=HTMLResponse)
@login_required
async def settings_page(req: Request, db=Depends(get_db)):
    """User settings page"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": req,
                "business": user
            }
        )
    except Exception as e:
        logger.error(f"Settings page error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/settings")
@login_required
async def update_settings(
    req: Request,
    name: str = Form(...),
    whatsapp: str = Form(...),
    business_goal: str = Form(None),
    business_address: str = Form(None),
    db=Depends(get_db)
):
    """Update user settings"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        user.name = sanitize_input(name)
        user.whatsapp_number = WhatsAppBot.clean_phone(whatsapp)
        if business_goal:
            user.goal = sanitize_input(business_goal)
        if business_address:
            user.address = sanitize_input(business_address)
        
        db.commit()
        
        logger.info(f"User {user.id} updated settings")
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": req,
                "business": user,
                "success": "Settings updated successfully!"
            }
        )
        
    except Exception as e:
        logger.error(f"Settings update error: {str(e)}")
        return RedirectResponse("/settings", 302)

# =====================================================
# BOOKINGS ROUTES
# =====================================================

@app.get("/bookings", response_class=HTMLResponse)
@login_required
async def bookings_page(req: Request, db=Depends(get_db)):
    """View all bookings"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get all bookings with filters
        status_filter = req.query_params.get("status")
        query = db.query(Booking).filter(Booking.business_id == user.id)
        
        if status_filter and status_filter != "all":
            query = query.filter(Booking.status == status_filter)
        
        bookings = query.order_by(Booking.booking_date.desc()).all()
        
        return templates.TemplateResponse(
            "bookings.html",
            {
                "request": req,
                "business": user,
                "bookings": bookings,
                "current_filter": status_filter or "all"
            }
        )
    except Exception as e:
        logger.error(f"Bookings page error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/api/bookings/{booking_id}/cancel")
@login_required
async def cancel_booking(booking_id: int, req: Request, db=Depends(get_db)):
    """Cancel a booking"""
    try:
        user = get_user(req, db)
        if not user:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
        
        booking = db.query(Booking)\
            .filter(Booking.id == booking_id, Booking.business_id == user.id)\
            .first()
        
        if not booking:
            return JSONResponse(status_code=404, content={"error": "Booking not found"})
        
        booking.status = "cancelled"
        db.commit()
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Cancel booking error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to cancel booking"})

# =====================================================
# EXPORT ROUTES
# =====================================================

@app.get("/export/bookings")
@login_required
async def export_bookings(req: Request, db=Depends(get_db)):
    """Export bookings as CSV"""
    try:
        user = get_user(req, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Name', 'Phone', 'Date', 'Time', 'Status', 'Created At'])
        
        # Write data
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .all()
        
        for b in bookings:
            writer.writerow([
                b.id,
                b.name,
                b.phone,
                b.booking_date,
                b.booking_time,
                b.status,
                b.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        # Return as downloadable file
        output.seek(0)
        filename = f"bookings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Export bookings error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

# =====================================================
# STATIC PAGES
# =====================================================

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(req: Request):
    """Privacy policy page"""
    return templates.TemplateResponse(
        "privacy.html",
        {"request": req, "now": datetime.utcnow()}
    )

@app.get("/terms", response_class=HTMLResponse)
async def terms(req: Request):
    """Terms of service page"""
    return templates.TemplateResponse(
        "terms.html",
        {"request": req, "now": datetime.utcnow()}
    )

@app.get("/refund", response_class=HTMLResponse)
async def refund(req: Request):
    """Refund policy page"""
    return templates.TemplateResponse(
        "refund.html",
        {"request": req, "now": datetime.utcnow()}
    )

@app.get("/about", response_class=HTMLResponse)
async def about(req: Request):
    """About page"""
    return templates.TemplateResponse(
        "about.html",
        {"request": req, "now": datetime.utcnow()}
    )

@app.get("/contact", response_class=HTMLResponse)
async def contact(req: Request):
    """Contact page"""
    return templates.TemplateResponse(
        "contact.html",
        {
            "request": req,
            "support_email": SUPPORT_EMAIL,
            "now": datetime.utcnow()
        }
    )

# =====================================================
# DEBUG ROUTES (Development Only)
# =====================================================

if ENVIRONMENT == "development":
    
    @app.get("/debug/razorpay")
    async def debug_razorpay():
        """Debug Razorpay configuration"""
        return {
            "key_present": bool(RAZORPAY_KEY),
            "secret_present": bool(RAZORPAY_SECRET),
            "client_initialized": razorpay_client is not None,
            "key_prefix": RAZORPAY_KEY[:10] + "..." if RAZORPAY_KEY else None,
            "environment": ENVIRONMENT
        }
    
    @app.get("/debug/email")
    async def debug_email():
        """Test email configuration"""
        result = await EmailService.send_email(
            "test@example.com",
            "Test Email",
            "welcome",
            {"name": "Test User"}
        )
        return {"email_sent": result}
    
    @app.get("/debug/db")
    async def debug_db(db=Depends(get_db)):
        """Test database connection"""
        try:
            from sqlalchemy import text
            result = db.execute("SELECT 1").first()
            return {
                "database": "connected",
                "result": result[0] if result else None,
                "tables": {
                    "businesses": db.query(Business).count(),
                    "bookings": db.query(Booking).count(),
                    "payments": db.query(Payment).count()
                }
            }
        except Exception as e:
            return {"database": "error", "error": str(e)}
    
    @app.get("/debug/session")
    async def debug_session(req: Request):
        """Debug session data"""
        return {
            "session_id": req.session.get("business_id"),
            "session_data": dict(req.session)
        }

@app.get("/debug/session")
async def debug_session(req: Request, db=Depends(get_db)):
    """Debug session and user data"""
    results = {
        "is_logged": is_logged(req),
        "session_id": req.session.get("business_id"),
        "session_data": dict(req.session),
    }
    
    if is_logged(req):
        user = get_user(req, db)
        if user:
            results["user"] = {
                "id": user.id,
                "name": user.name,
                "email": user.admin_email,
                "plan": user.plan,
                "chat_used": user.chat_used,
                "chat_limit": user.chat_limit,
                "trial_ends_at": str(user.trial_ends_at) if user.trial_ends_at else None,
                "onboarding_done": user.onboarding_done
            }
        else:
            results["user"] = "User not found in database"
    
    return results

@app.get("/debug/dashboard-raw")
async def debug_dashboard_raw(req: Request, db=Depends(get_db)):
    """Raw dashboard debug - no templates"""
    try:
        # Check login
        if not is_logged(req):
            return {"error": "Not logged in", "session": dict(req.session)}
        
        user = get_user(req, db)
        if not user:
            return {"error": "User not found in database", "session_id": req.session.get("business_id")}
        
        # Test each database query
        results = {
            "user": {
                "id": user.id,
                "name": user.name,
                "plan": user.plan,
                "chat_used": user.chat_used,
                "chat_limit": user.chat_limit,
            }
        }
        
        # Test bookings query
        try:
            bookings = db.query(Booking).filter(Booking.business_id == user.id).limit(1).all()
            results["bookings_query"] = f"✅ Success, found {len(bookings)}"
        except Exception as e:
            results["bookings_query"] = f"❌ Failed: {str(e)}"
        
        # Test analytics calculations
        try:
            total_bookings = db.query(Booking).filter(Booking.business_id == user.id).count()
            results["total_bookings"] = total_bookings
        except Exception as e:
            results["total_bookings_error"] = str(e)
        
        try:
            cancelled = db.query(Booking).filter(
                Booking.business_id == user.id, 
                Booking.status == "cancelled"
            ).count()
            results["cancelled"] = cancelled
        except Exception as e:
            results["cancelled_error"] = str(e)
        
        # Test trial days calculation
        try:
            if user.plan == "trial" and user.trial_ends_at:
                trial_days = (user.trial_ends_at - datetime.utcnow()).days
                results["trial_days"] = trial_days
            else:
                results["trial_days"] = "N/A"
        except Exception as e:
            results["trial_days_error"] = str(e)
        
        return results
        
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/templates")
async def debug_templates():
    """Check which templates exist"""
    import os
    template_dir = "templates"
    files = os.listdir(template_dir) if os.path.exists(template_dir) else []
    return {
        "template_dir_exists": os.path.exists(template_dir),
        "templates": files,
        "working_dir": os.getcwd()
    }
# =====================================================
# ERROR HANDLERS
# =====================================================

@app.exception_handler(404)
async def not_found_handler(req: Request, exc):
    """Custom 404 handler"""
    return templates.TemplateResponse(
        "404.html",
        {"request": req},
        status_code=404
    )

@app.exception_handler(500)
async def internal_error_handler(req: Request, exc):
    """Custom 500 handler"""
    logger.error(f"500 error: {str(exc)}")
    logger.error(traceback.format_exc())
    return templates.TemplateResponse(
        "500.html",
        {"request": req},
        status_code=500
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(req: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    if exc.status_code == 401:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(
        "error.html",
        {"request": req, "error": exc.detail, "status_code": exc.status_code},
        status_code=exc.status_code
    )

# =====================================================
# STARTUP/SHUTDOWN EVENTS
# =====================================================

@app.on_event("startup")
async def startup_event():
    """Tasks to run on startup"""
    logger.info("=" * 60)
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} starting...")
    logger.info(f"🌍 Environment: {ENVIRONMENT}")
    logger.info(f"🔗 Base URL: {BASE_URL}")
    logger.info(f"💳 Razorpay: {'✅ Configured' if razorpay_client else '❌ Not configured'}")
    logger.info(f"📧 SendGrid: {'✅ Configured' if SENDGRID_API_KEY else '❌ Not configured'}")
    logger.info(f"📊 Database: Connected")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """Tasks to run on shutdown"""
    logger.info(f"👋 {APP_NAME} shutting down...")

# =====================================================
# MAIN ENTRY POINT
# =====================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
        workers=1  # Start with 1 worker, increase in production if needed
    )