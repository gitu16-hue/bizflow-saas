# =====================================================
# BIZFLOW AI - ENTERPRISE SAAS PLATFORM
# VERSION 12.0 - PRODUCTION READY
# =====================================================

import asyncio
import sys
import os
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from contextlib import asynccontextmanager
import json
import secrets
import hmac
import hashlib
import re
from functools import wraps
import time

# Third-party imports
from dotenv import load_dotenv
load_dotenv()

# FastAPI & Related
from fastapi import FastAPI, Request, Form, Depends, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError

# Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Security
from passlib.hash import bcrypt

# Database
from database import SessionLocal, engine
from models import Base, Business, Booking, Payment, AuditLog, Conversation

# Email
import sendgrid
from sendgrid.helpers.mail import Mail

# Payments
import razorpay

# Utilities
import csv
from io import StringIO
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import text, desc
from sqlalchemy.orm import Session

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# =====================================================
# ENVIRONMENT & CONFIGURATION
# =====================================================

class Settings:
    """Application settings with validation"""
    APP_NAME = "BizFlow AI"
    APP_VERSION = "12.0"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    DEBUG = ENVIRONMENT == "development"
    BASE_URL = os.getenv("BASE_URL", "https://bizflow-saas.onrender.com")
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bizflow.db")
    
    # Email
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@bizflowai.online")
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@bizflowai.online")
    
    # Payment
    RAZORPAY_KEY = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    
    # Security
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_TIMEOUT_MINUTES = 15
    SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days
    SESSION_REMEMBER_AGE = 60 * 60 * 24 * 30  # 30 days
    
    # Rate Limiting
    RATE_LIMIT_GLOBAL = "100/minute"
    RATE_LIMIT_LOGIN = "5/minute"
    RATE_LIMIT_API = "60/minute"
    
    # Redis (optional)
    REDIS_URL = os.getenv("REDIS_URL", None)
    
    @classmethod
    def validate(cls):
        """Validate critical settings"""
        required = ["SECRET_KEY", "DATABASE_URL"]
        missing = [req for req in required if not getattr(cls, req)]
        if missing:
            raise ValueError(f"Missing required settings: {missing}")

# Initialize settings
settings = Settings()
settings.validate()

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
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

# Create logs directory
os.makedirs("logs", exist_ok=True)

# Setup logging
logger = logging.getLogger("bizflow")
logger.setLevel(logging.INFO if not settings.DEBUG else logging.DEBUG)

# File handler
file_handler = logging.FileHandler("logs/bizflow.log")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
console_handler.setFormatter(CustomFormatter())
logger.addHandler(console_handler)

# Error file handler
error_handler = logging.FileHandler("logs/error.log")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(file_formatter)
logger.addHandler(error_handler)

# =====================================================
# RATE LIMITING
# =====================================================

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_GLOBAL],
    storage_uri=settings.REDIS_URL or "memory://",
    strategy="fixed-window"
)

# =====================================================
# PAYMENT CLIENT INITIALIZATION
# =====================================================

razorpay_client = None
if settings.RAZORPAY_KEY and settings.RAZORPAY_SECRET:
    try:
        razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY.strip(), settings.RAZORPAY_SECRET.strip())
        )
        logger.info("✅ Razorpay client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Razorpay client initialization failed: {str(e)}")
        razorpay_client = None

# =====================================================
# LIFESPAN MANAGEMENT
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown events
    """
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    logger.info(f"🌍 Environment: {settings.ENVIRONMENT}")
    logger.info(f"🔗 Base URL: {settings.BASE_URL}")
    logger.info(f"💳 Razorpay: {'✅ Configured' if razorpay_client else '❌ Not configured'}")
    logger.info(f"📧 SendGrid: {'✅ Configured' if settings.SENDGRID_API_KEY else '❌ Not configured'}")
    logger.info("=" * 60)
    
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables verified/created")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        raise
    
    yield
    
    logger.info(f"👋 {settings.APP_NAME} shutting down...")

# =====================================================
# FASTAPI APP INITIALIZATION
# =====================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise WhatsApp Business Automation Platform",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)

# =====================================================
# MIDDLEWARE SETUP
# =====================================================

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

# Performance monitoring middleware
class PerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        if process_time > 1.0:
            logger.warning(f"Slow request: {request.method} {request.url.path} took {process_time:.2f}s")
        
        return response

# Add middleware in correct order
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "bizflowai.online",
        "*.railway.app",
        "*.onrender.com",
        "localhost",
        "127.0.0.1",
        "bizflow-saas.onrender.com"
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.BASE_URL,
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
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=settings.ENVIRONMENT == "production"
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(PerformanceMiddleware)

# =====================================================
# TEMPLATES & STATIC FILES
# =====================================================

templates = Jinja2Templates(directory="templates")
# Enable caching in production for better performance
if settings.ENVIRONMENT == "production":
    templates.env.cache_size = 50  # Cache up to 50 templates
else:
    templates.env.cache = None  # Disable caching in development

app.mount("/static", StaticFiles(directory="static"), name="static")

# =====================================================
# DATABASE DEPENDENCY
# =====================================================

def get_db() -> Session:
    """Get database session with automatic cleanup"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =====================================================
# DECORATORS & HELPERS
# =====================================================

def login_required(func):
    """Decorator to require login"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("business_id"):
            request.session["next"] = request.url.path
            return RedirectResponse("/login", 302)
        return await func(request, *args, **kwargs)
    return wrapper

def admin_required(func):
    """Decorator to require admin privileges"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        business_id = request.session.get("business_id")
        if not business_id:
            request.session["next"] = request.url.path
            return RedirectResponse("/login", 302)
        
        db = next(get_db())
        try:
            user = db.query(Business).get(business_id)
            if not user or not user.is_admin:
                return RedirectResponse("/dashboard", 302)
        finally:
            db.close()
        
        return await func(request, *args, **kwargs)
    return wrapper

def rate_limit(limit: str):
    """Rate limiting decorator"""
    return limiter.limit(limit)

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
    return re.sub(r'[<>\'"]', '', text)

def log_audit(user_id: int, action: str, details: dict = None, db: Session = None):
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
# AUTHENTICATION HELPERS
# =====================================================

def is_logged(req: Request) -> bool:
    """Check if user is logged in"""
    return bool(req.session.get("business_id"))

def get_user(req: Request, db: Session):
    """Get current user from session"""
    bid = req.session.get("business_id")
    if not bid:
        return None
    return db.query(Business).get(bid)

# =====================================================
# ERROR HANDLERS
# =====================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return templates.TemplateResponse(
        "404.html",
        {"request": request},
        status_code=404
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Custom 500 handler"""
    logger.error(f"500 error: {str(exc)}")
    logger.error(traceback.format_exc())
    return templates.TemplateResponse(
        "500.html",
        {"request": request},
        status_code=500
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    if exc.status_code == 401:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "error": exc.detail,
            "status_code": exc.status_code
        },
        status_code=exc.status_code
    )

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
@rate_limit("10/minute")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """Health check endpoint with detailed status"""
    try:
        db.execute(text("SELECT 1")).first()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "razorpay": "configured" if razorpay_client else "not configured",
            "sendgrid": "configured" if settings.SENDGRID_API_KEY else "not configured"
        }
    }

# =====================================================
# HOME PAGE
# =====================================================

@app.get("/", response_class=HTMLResponse)
@rate_limit("30/minute")
async def home(request: Request):
    """Home page"""
    try:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "logged": is_logged(request),
                "year": datetime.now().year
            }
        )
    except Exception as e:
        logger.error(f"Home page error: {str(e)}")
        return templates.TemplateResponse(
            "500.html",
            {"request": request, "error": "An error occurred loading the page"},
            status_code=500
        )

# =====================================================
# AUTHENTICATION ROUTES
# =====================================================

@app.get("/login", response_class=HTMLResponse)
@rate_limit("10/minute")
async def login_page(request: Request):
    """Login page"""
    if is_logged(request):
        return RedirectResponse("/dashboard", 302)
    
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )

@app.post("/login")
@rate_limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Login handler"""
    try:
        email = email.lower().strip()
        user = db.query(Business).filter(Business.admin_email == email).first()
        
        if not user or not verify_password(password, user.admin_password):
            logger.warning(f"Failed login attempt for email: {email}")
            await asyncio.sleep(1)  # Prevent timing attacks
            request.session["login_error"] = "Invalid email or password"
            return RedirectResponse("/login", 302)
        
        if not user.is_active:
            logger.warning(f"Inactive account login attempt: {email}")
            request.session["login_error"] = "Account is disabled. Please contact support."
            return RedirectResponse("/login", 302)
        
        # Set session
        request.session["business_id"] = user.id
        if remember:
            request.session["max_age"] = settings.SESSION_REMEMBER_AGE
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        # Log audit
        log_audit(user.id, "login", {"ip": request.client.host}, db)
        
        logger.info(f"✅ User logged in: {email}")
        
        # Redirect to intended page
        next_url = request.session.pop("next", "/dashboard")
        return RedirectResponse(next_url, 302)
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        request.session["login_error"] = "An error occurred. Please try again."
        return RedirectResponse("/login", 302)

@app.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Logout handler"""
    user_id = request.session.get("business_id")
    if user_id:
        log_audit(user_id, "logout", {"ip": request.client.host}, db)
    
    request.session.clear()
    logger.info(f"User logged out: {user_id}")
    return RedirectResponse("/", 302)

# =====================================================
# SIGNUP ROUTES
# =====================================================

@app.get("/signup", response_class=HTMLResponse)
@rate_limit("10/minute")
async def signup_page(request: Request, plan: str = None):
    """Signup page"""
    if is_logged(request):
        return RedirectResponse("/dashboard", 302)
    
    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "plan": plan,
            "plans": PLANS
        }
    )

@app.post("/signup")
@rate_limit("5/minute")
async def signup(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_type: str = Form(...),
    db: Session = Depends(get_db)
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
                    "request": request,
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
                    "request": request,
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
        request.session["business_id"] = user.id
        
        # Log audit
        log_audit(user.id, "signup", {"ip": request.client.host}, db)
        
        # Send welcome email (async)
        asyncio.create_task(
            EmailService.send_email(
                email,
                "Welcome to BizFlow AI!",
                "welcome",
                {"name": name}
            )
        )
        
        logger.info(f"✅ New user signed up: {email}")
        
        return RedirectResponse("/onboarding", 302)
        
    except IntegrityError:
        logger.error(f"Signup integrity error for email: {email}")
        db.rollback()
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
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
                "request": request,
                "error": "An error occurred. Please try again.",
                "plans": PLANS
            }
        )

# =====================================================
# DASHBOARD
# =====================================================

@app.get("/dashboard", response_class=HTMLResponse)
@login_required
@rate_limit("30/minute")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """User dashboard"""
    try:
        user = get_user(request, db)
        if not user:
            request.session.clear()
            return RedirectResponse("/login", 302)
        
        # Check trial expiry
        if user.plan == "trial" and user.trial_ends_at and user.trial_ends_at < datetime.utcnow():
            user.plan = "expired"
            db.commit()
        
        # Get recent bookings
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .limit(10)\
            .all()
        
        # Calculate analytics
        total_bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .count()
        
        cancelled = db.query(Booking)\
            .filter(Booking.business_id == user.id, Booking.status == "cancelled")\
            .count()
        
        analytics = {
            "conversations": user.chat_used or 0,
            "bookings": total_bookings,
            "interested": 0,
            "cancelled": cancelled,
            "conversion": round((total_bookings / max(user.chat_used, 1)) * 100, 1) if user.chat_used else 0,
            "chat_usage_percent": round((user.chat_used / user.chat_limit) * 100, 1) if user.chat_limit else 0
        }
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "business": user,
                "bookings": bookings,
                "analytics": analytics,
                "now": datetime.utcnow(),
                "trial_days_left": max((user.trial_ends_at - datetime.utcnow()).days, 0) if user.plan == "trial" and user.trial_ends_at else 0,
                "plans": PLANS
            }
        )
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        logger.error(traceback.format_exc())
        return templates.TemplateResponse(
            "500.html",
            {"request": request, "error": "An error occurred loading your dashboard"},
            status_code=500
        )

# =====================================================
# ONBOARDING
# =====================================================

@app.get("/onboarding", response_class=HTMLResponse)
@login_required
async def onboarding(request: Request, db: Session = Depends(get_db)):
    """Onboarding wizard for new users"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        if user.onboarding_done:
            return RedirectResponse("/dashboard", 302)
        
        return templates.TemplateResponse(
            "onboarding.html",
            {
                "request": request,
                "business": user
            }
        )
    except Exception as e:
        logger.error(f"Onboarding error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/onboarding")
@login_required
async def onboarding_complete(
    request: Request,
    business_goal: str = Form(...),
    business_address: str = Form(...),
    business_hours: str = Form(...),
    db: Session = Depends(get_db)
):
    """Complete onboarding"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        user.goal = sanitize_input(business_goal)
        user.address = sanitize_input(business_address)
        user.business_hours = sanitize_input(business_hours)
        user.onboarding_done = True
        db.commit()
        
        logger.info(f"User {user.id} completed onboarding")
        return RedirectResponse("/dashboard", 302)
        
    except Exception as e:
        logger.error(f"Onboarding completion error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

# =====================================================
# PLANS CONFIGURATION
# =====================================================
PLANS = {
    "starter": {
        "name": "Starter",
        "price": 999,
        "chats": 300,
        "features": [
            "WhatsApp Bot Integration",
            "300 Chats/Month",
            "Basic Booking System",
            "Analytics Dashboard",
            "Email Support"
        ],
        "color": "blue",
        "icon": "rocket"
    },
    "pro": {
        "name": "Pro",
        "price": 2499,
        "chats": 999999,
        "features": [
            "Unlimited Chats",
            "Advanced AI Assistant",
            "Auto Reminders & Alerts",
            "Calendar Sync",
            "Priority Support",
            "Lead Optimization AI",
            "CRM Integration"
        ],
        "color": "orange",
        "icon": "crown",
        "popular": True
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 9999,
        "chats": "Unlimited",
        "features": [
            "Everything in Pro",
            "Dedicated Account Manager",
            "Custom Integrations",
            "SLA Guarantee",
            "On-premise Option",
            "24/7 Phone Support",
            "Advanced Analytics"
        ],
        "color": "purple",
        "icon": "building"
    }
}

# =====================================================
# WHATSAPP BOT ENGINE - ENHANCED NLP VERSION
# =====================================================

class WhatsAppBot:
    """Advanced WhatsApp bot with enhanced NLP capabilities"""
    
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
        """Get dynamic menu based on industry with emoji support"""
        menus = {
            "restaurant": """
👋 Welcome to *{name}* 🍽️

1️⃣ Book a Table
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
3️⃣ Our Stylists
4️⃣ Location
5️⃣ Special Offers
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
""",
            "education": """
👋 Welcome to *{name}* 📚

1️⃣ Book Demo Class
2️⃣ Courses Offered
3️⃣ Fee Structure
4️⃣ Location
5️⃣ Contact Counselor
6️⃣ Exit

Reply with number 👇
""",
            "automotive": """
👋 Welcome to *{name}* 🚗

1️⃣ Book Service
2️⃣ Service Packages
3️⃣ Pickup/Drop
4️⃣ Location
5️⃣ Contact Mechanic
6️⃣ Exit

Reply with number 👇
"""
        }
        
        industry = business.business_type.lower()
        menu = menus.get(industry, """
👋 Welcome to *{name}* 🚀

1️⃣ Book Appointment
2️⃣ Our Services
3️⃣ Location
4️⃣ Contact Us
5️⃣ Pricing
6️⃣ Exit

Reply with number 👇
""")
        
        return menu.format(name=business.name)
    
    @staticmethod
    def parse_booking(text: str) -> Optional[Dict]:
        """
        Parse natural language booking with enhanced NLP
        Handles various formats like:
        - "16march 7 pm jayant singh"
        - "16 mar 7pm John"
        - "March 16 7:30 PM Jane Doe"
        - "tomorrow 3pm Rahul"
        - "next Monday 10am Priya"
        """
        try:
            text = text.lower().strip()
            
            # Handle formats like "16march 7 pm jayant singh" (no space between day and month)
            
            # Step 1: Extract date components
            # Match patterns like: 16march, 16mar, 16 march, 16th march, 16th mar
            date_patterns = [
                r'(\d{1,2})(?:st|nd|rd|th)?\s*(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)',
                r'(\d{1,2})(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)'
            ]
            
            date_match = None
            for dp in date_patterns:
                date_match = re.search(dp, text)
                if date_match:
                    break
            
            if not date_match:
                # Try reverse format: march 16, March 16th
                reverse_date = re.search(r'(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)\s+(\d{1,2})(?:st|nd|rd|th)?', text)
                if reverse_date:
                    month_text, day = reverse_date.groups()
                    date_match = (None, day, month_text)
                else:
                    return None
            else:
                day, month_text = date_match.groups()
            
            # Convert month text to number
            month_map = {
                'jan': '01', 'january': '01',
                'feb': '02', 'february': '02',
                'mar': '03', 'march': '03',
                'apr': '04', 'april': '04',
                'may': '05',
                'jun': '06', 'june': '06',
                'jul': '07', 'july': '07',
                'aug': '08', 'august': '08',
                'sep': '09', 'september': '09',
                'oct': '10', 'october': '10',
                'nov': '11', 'november': '11',
                'dec': '12', 'december': '12'
            }
            
            month = month_map.get(month_text[:3].lower())
            if not month:
                return None
            
            # Step 2: Extract time
            time_patterns = [
                r'(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm)',
                r'(\d{1,2})\s*(am|pm)',
                r'(\d{1,2}):(\d{2})\s*(am|pm)',
            ]
            
            time_match = None
            hour = None
            minute = '00'
            ampm = None
            
            for tp in time_patterns:
                time_match = re.search(tp, text)
                if time_match:
                    groups = time_match.groups()
                    if len(groups) == 2:
                        hour, ampm = groups[0], groups[1]
                    elif len(groups) == 3 and groups[1] is None:
                        hour, _, ampm = groups
                    elif len(groups) == 3 and groups[1] is not None:
                        hour, minute, ampm = groups
                    break
            
            if not time_match:
                return None
            
            # Step 3: Extract name
            time_end = time_match.end()
            name = text[time_end:].strip()
            
            if not name and date_match:
                if isinstance(date_match, tuple):
                    name = text[date_match[2]:].strip() if len(date_match) > 2 else ""
                else:
                    name = text[date_match.end():].strip()
                
                name = re.sub(r'\d{1,2}\s*(?::\d{2})?\s*(am|pm)?', '', name).strip()
            
            if name:
                name = re.sub(r'\b(am|pm)\b', '', name, flags=re.IGNORECASE).strip()
                name = re.sub(r'\s+', ' ', name).strip()
                name = name.title()
            else:
                name = "Guest"
            
            # Step 4: Format time
            hour = int(hour)
            if ampm and ampm.lower() == 'pm' and hour < 12:
                hour += 12
            elif ampm and ampm.lower() == 'am' and hour == 12:
                hour = 0
            
            minute = minute.zfill(2) if minute else '00'
            time = f"{hour:02d}:{minute}"
            
            # Step 5: Create date string
            year = datetime.now().year
            date_str = f"{day.zfill(2)}-{month}-{year}"
            
            # Validate date
            try:
                booking_date = datetime.strptime(date_str, '%d-%m-%Y')
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                if booking_date < today:
                    if (today - booking_date).days < 30:
                        next_year = year + 1
                        date_str = f"{day.zfill(2)}-{month}-{next_year}"
            except:
                pass
            
            return {
                "date": date_str,
                "time": time,
                "name": name
            }
            
        except Exception as e:
            logger.error(f"Booking parse error: {str(e)}")
            return None
    
    @staticmethod
    def _month_to_number(month: str) -> str:
        """Convert month name to number"""
        months = {
            'jan': '01', 'january': '01',
            'feb': '02', 'february': '02',
            'mar': '03', 'march': '03',
            'apr': '04', 'april': '04',
            'may': '05',
            'jun': '06', 'june': '06',
            'jul': '07', 'july': '07',
            'aug': '08', 'august': '08',
            'sep': '09', 'september': '09',
            'oct': '10', 'october': '10',
            'nov': '11', 'november': '11',
            'dec': '12', 'december': '12'
        }
        return months.get(month[:3].lower(), '01')
    
    @staticmethod
    def process_message(phone: str, message: str, business, db) -> str:
        """Process incoming WhatsApp message with enhanced NLP"""
        message = message.strip()
        lower_msg = message.lower()
        
        state = business.flow_state or "start"
        
        # Reset command - expanded with common greetings
        if lower_msg in ["reset", "restart", "help", "menu", "hi", "hello", "hey", "start", "hii", "hy"]:
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
        """Handle menu selection with support for natural language"""
        message = message.strip().lower()
        
        # Map natural language to options
        if message in ['1', 'book', 'booking', 'appointment', 'reserve', 'schedule']:
            business.flow_state = "booking"
            db.commit()
            return (
                "📅 Please provide booking details:\n\n"
                "Examples:\n"
                "• 15 Mar 3PM John Doe\n"
                "• 16 March 7 PM Jayant Singh\n"
                "• tomorrow 4PM Rahul\n"
                "• next Monday 10AM Jane Smith\n\n"
                "Type 'cancel' to go back"
            )
        elif message in ['2', 'services', 'menu', 'price list', 'what do you offer']:
            return WhatsAppBot._get_services(business)
        elif message in ['3', 'location', 'address', 'where', 'directions']:
            return WhatsAppBot._get_location(business)
        elif message in ['4', 'contact', 'phone', 'email', 'reach us', 'support']:
            return WhatsAppBot._get_contact(business)
        elif message in ['5', 'pricing', 'price', 'cost', 'rates', 'fees']:
            return WhatsAppBot._get_pricing(business)
        elif message in ['6', 'exit', 'bye', 'goodbye', 'quit', 'end']:
            business.flow_state = "start"
            db.commit()
            return "👋 Thank you for visiting! Type 'hi' to start again."
        else:
            return "❌ Invalid option. Please reply with a number (1-6) or type 'menu' to see options."
    
    @staticmethod
    def _handle_booking(message: str, phone: str, business, db) -> str:
        """Handle booking process with enhanced NLP"""
        if message.lower() in ['cancel', 'back', 'exit', 'go back', 'never mind']:
            business.flow_state = "menu"
            db.commit()
            return "❌ Booking cancelled.\n\n" + WhatsAppBot.get_industry_menu(business)
        
        booking_data = WhatsAppBot.parse_booking(message)
        if not booking_data:
            return (
                "❌ Could not understand. Please use format like:\n"
                "• 15 Mar 3PM John Doe\n"
                "• 16 March 7 PM Jayant Singh\n"
                "• tomorrow 4PM Rahul\n"
                "• next Monday 10AM Jane Smith\n\n"
                "Type 'cancel' to go back"
            )
        
        # Check for double booking
        existing = db.query(Booking).filter(
            Booking.business_id == business.id,
            Booking.booking_date == booking_data['date'],
            Booking.booking_time == booking_data['time'],
            Booking.status.in_(['pending', 'confirmed'])
        ).first()
        
        if existing:
            return f"""
❌ Sorry, {booking_data['time']} on {booking_data['date']} is already booked.

Please choose another time or type 'cancel' to go back.
"""
        
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
        industry = business.business_type.lower()
        
        services_map = {
            "restaurant": "🍽️ *Our Services*\n\n• Dine-in Experience\n• Takeaway Orders\n• Home Delivery\n• Private Events\n• Catering Services\n• Special Occasion Booking",
            "salon": "💇 *Our Services*\n\n• Haircut & Styling\n• Hair Coloring\n• Facial Treatments\n• Manicure/Pedicure\n• Massage Therapy\n• Bridal Package",
            "gym": "💪 *Our Services*\n\n• Personal Training\n• Group Classes\n• Yoga & Meditation\n• CrossFit\n• Nutrition Counseling\n• Weight Management",
            "clinic": "🏥 *Our Services*\n\n• General Consultation\n• Specialist Visit\n• Health Checkup\n• Vaccination\n• Lab Tests\n• Emergency Care",
            "realestate": "🏠 *Our Services*\n\n• Property Listings\n• Site Visits\n• Home Loans Assistance\n• Legal Documentation\n• Interior Design\n• Property Management",
            "education": "📚 *Our Services*\n\n• Demo Classes\n• Course Counseling\n• Study Materials\n• Online Classes\n• Career Guidance\n• Scholarship Info",
            "automotive": "🚗 *Our Services*\n\n• Regular Service\n• Repair Work\n• Spare Parts\n• Detailing\n• Insurance Claim\n• Roadside Assistance"
        }
        
        return services_map.get(industry, "📋 *Our Services*\n\n• General Consultation\n• Information Services\n• Customer Support\n• Visit our website for complete details.")
    
    @staticmethod
    def _get_location(business) -> str:
        """Get business location with hours"""
        addr = business.address or "📍 Main Location"
        hours = business.business_hours or "Monday - Friday: 9AM - 8PM\nSaturday: 10AM - 6PM\nSunday: Closed"
        
        return f"""
📍 *Address*
{addr}

🕒 *Business Hours*
{hours}

Google Maps: https://maps.google.com/?q={addr.replace(' ', '+')}
"""
    
    @staticmethod
    def _get_contact(business) -> str:
        """Get contact information"""
        return f"""
📞 *Contact Us*

📱 Phone: {business.whatsapp_number}
📧 Email: {business.admin_email}

⏰ Response Time: Within 2 hours

For urgent inquiries, please call during business hours.
"""
    
    @staticmethod
    def _get_pricing(business) -> str:
        """Get pricing information"""
        industry = business.business_type.lower()
        
        pricing_map = {
            "restaurant": "💰 *Pricing*\n\n• Starters: ₹150 - ₹350\n• Main Course: ₹250 - ₹600\n• Desserts: ₹100 - ₹250\n• Beverages: ₹50 - ₹200\n\n*Special discounts on group bookings!*",
            "salon": "💰 *Pricing*\n\n• Haircut: ₹199 - ₹499\n• Hair Color: ₹999 - ₹2999\n• Facial: ₹599 - ₹1499\n• Manicure: ₹399\n• Pedicure: ₹499\n• Massage: ₹999 - ₹1999",
            "gym": "💰 *Pricing*\n\n• Monthly Membership: ₹1999\n• Quarterly: ₹5499\n• Yearly: ₹17999\n• Personal Training: ₹500/session\n\n*First session FREE!*",
            "clinic": "💰 *Pricing*\n\n• Consultation: ₹500\n• Specialist Visit: ₹800 - ₹1500\n• Health Checkup: ₹999\n• Vaccination: ₹300 - ₹1000\n\n*Insurance accepted*",
            "realestate": "💰 *Pricing*\n\n• Booking Amount: ₹50,000\n• Visit Charges: ₹1000 (refundable)\n• Documentation: ₹5000\n\n*Call for property pricing*",
            "education": "💰 *Pricing*\n\n• Demo Class: FREE\n• Monthly Tuition: ₹2000 - ₹5000\n• Course Fee: ₹15000 - ₹50000\n• Study Material: Included\n\n*Scholarships available*",
            "automotive": "💰 *Pricing*\n\n• Basic Service: ₹1999\n• Standard Service: ₹3499\n• Comprehensive: ₹5999\n• Repair: Quoted after inspection\n\n*Free pickup & drop*"
        }
        
        return pricing_map.get(industry, "💰 *Pricing*\n\nBasic consultation: ₹500\nPremium services: Starting at ₹1000\n\nCheck our website for detailed pricing and packages.")

# =====================================================
# CONVERSATIONS PAGE
# =====================================================

@app.get("/conversations", response_class=HTMLResponse)
@login_required
async def conversations_page(request: Request, db: Session = Depends(get_db)):
    """View all WhatsApp conversations"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get all conversations for this business
        conversations = db.query(Conversation)\
            .filter(Conversation.business_id == user.id)\
            .order_by(Conversation.updated_at.desc())\
            .all()
        
        return templates.TemplateResponse(
            "conversations.html",
            {
                "request": request,
                "business": user,
                "conversations": conversations
            }
        )
    except Exception as e:
        logger.error(f"Conversations page error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.get("/conversations/{conversation_id}", response_class=HTMLResponse)
@login_required
async def conversation_detail(
    conversation_id: int, 
    request: Request, 
    db: Session = Depends(get_db)
):
    """View a specific conversation"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get the conversation
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.business_id == user.id
        ).first()
        
        if not conversation:
            return RedirectResponse("/conversations", 302)
        
        return templates.TemplateResponse(
            "conversation_detail.html",
            {
                "request": request,
                "business": user,
                "conversation": conversation
            }
        )
    except Exception as e:
        logger.error(f"Conversation detail error: {str(e)}")
        return RedirectResponse("/conversations", 302)

# =====================================================
# WHATSAPP WEBHOOK
# =====================================================

@app.post("/webhook/whatsapp")
@rate_limit("60/minute")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """WhatsApp webhook handler"""
    try:
        form = await request.form()
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
                f"{settings.BASE_URL}/signup\n\n"
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
        logger.error(traceback.format_exc())
        resp = MessagingResponse()
        resp.message("❌ An error occurred. Please try again later.")
        return Response(
            content=str(resp),
            media_type="application/xml",
            status_code=500
        )

# =====================================================
# EMAIL SERVICE
# =====================================================

class EmailService:
    """Enterprise email service with templates"""
    
    @staticmethod
    async def send_email(to_email: str, subject: str, template_name: str, context: dict = None) -> bool:
        """Send email using template"""
        if not settings.SENDGRID_API_KEY:
            logger.error("SendGrid API key not configured")
            return False
        
        try:
            template = EmailService._get_template(template_name, context or {})
            
            message = Mail(
                from_email=settings.FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=template
            )
            
            sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
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
                                <a href="{settings.BASE_URL}/dashboard" class="button">Go to Dashboard</a>
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
# BOOKINGS API
# =====================================================

@app.post("/api/bookings/{booking_id}/status")
@login_required
async def update_booking_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Update booking status"""
    try:
        # Get booking_id from path
        booking_id = request.path_params.get("booking_id")
        if not booking_id:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Booking ID required"}
            )
        
        # Convert to int
        try:
            booking_id = int(booking_id)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid booking ID"}
            )
        
        user = get_user(request, db)
        if not user:
            return JSONResponse(
                status_code=401, 
                content={"status": "error", "message": "Not authenticated"}
            )
        
        booking = db.query(Booking).filter(
            Booking.id == booking_id,
            Booking.business_id == user.id
        ).first()
        
        if not booking:
            return JSONResponse(
                status_code=404, 
                content={"status": "error", "message": "Booking not found"}
            )
        
        data = await request.json()
        new_status = data.get('status')
        
        valid_statuses = ['pending', 'confirmed', 'cancelled', 'completed']
        if new_status not in valid_statuses:
            return JSONResponse(
                status_code=400, 
                content={"status": "error", "message": f"Invalid status"}
            )
        
        old_status = booking.status
        booking.status = new_status
        db.commit()
        
        logger.info(f"Booking {booking_id} status updated: {old_status} -> {new_status}")
        
        return {
            "status": "success", 
            "message": f"Booking marked as {new_status}",
            "booking": {
                "id": booking.id,
                "old_status": old_status,
                "new_status": new_status
            }
        }
        
    except Exception as e:
        logger.error(f"Booking status update error: {str(e)}")
        return JSONResponse(
            status_code=500, 
            content={"status": "error", "message": str(e)}
        )

@app.post("/api/bookings/{booking_id}/cancel")
@login_required
async def cancel_booking(
    request: Request, 
    db: Session = Depends(get_db)
):
    """Cancel a booking"""
    try:
        # Get booking_id from path
        booking_id = request.path_params.get("booking_id")
        if not booking_id:
            return JSONResponse(
                status_code=400,
                content={"error": "Booking ID required"}
            )
        
        try:
            booking_id = int(booking_id)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid booking ID"}
            )
        
        user = get_user(request, db)
        if not user:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
        
        booking = db.query(Booking)\
            .filter(Booking.id == booking_id, Booking.business_id == user.id)\
            .first()
        
        if not booking:
            return JSONResponse(status_code=404, content={"error": "Booking not found"})
        
        booking.status = "cancelled"
        db.commit()
        
        logger.info(f"Booking {booking_id} cancelled by user {user.id}")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Cancel booking error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to cancel booking"})

# =====================================================
# PAYMENT ROUTES
# =====================================================

@app.get("/billing", response_class=HTMLResponse)
@login_required
async def billing_page(request: Request, db: Session = Depends(get_db)):
    """Billing and subscription page"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        payments = db.query(Payment)\
            .filter(Payment.business_id == user.id)\
            .order_by(Payment.created_at.desc())\
            .all()
        
        return templates.TemplateResponse(
            "billing.html",
            {
                "request": request,
                "business": user,
                "payments": payments,
                "razorpay_key": settings.RAZORPAY_KEY,
                "plans": PLANS,
                "current_plan": user.plan
            }
        )
    except Exception as e:
        logger.error(f"Billing page error: {str(e)}")
        return templates.TemplateResponse(
            "500.html",
            {"request": request, "error": "An error occurred loading the billing page"},
            status_code=500
        )

@app.post("/api/create-order")
@login_required
@rate_limit("10/minute")
async def create_order(request: Request, db: Session = Depends(get_db)):
    """Create Razorpay order"""
    try:
        if not razorpay_client:
            return JSONResponse(
                status_code=503,
                content={"error": "Payment service temporarily unavailable"}
            )
        
        user = get_user(request, db)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required"}
            )
        
        data = await request.json()
        plan = data.get("plan")
        
        if plan not in PLANS:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid plan selected"}
            )
        
        amount = PLANS[plan]["price"] * 100
        
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
            "key": settings.RAZORPAY_KEY,
            "name": user.name,
            "email": user.admin_email,
            "phone": user.whatsapp_number,
            "plan": plan
        }
        
    except Exception as e:
        logger.error(f"Order creation error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to create order. Please try again."}
        )

@app.post("/api/payment-success")
@login_required
async def payment_success(request: Request, db: Session = Depends(get_db)):
    """Handle successful payment"""
    try:
        if not razorpay_client:
            return {"status": "error", "message": "Payment service unavailable"}
        
        user = get_user(request, db)
        if not user:
            return {"status": "error", "message": "User not authenticated"}
        
        data = await request.json()
        
        razorpay_client.utility.verify_payment_signature(data)
        
        payment_id = data.get('razorpay_payment_id')
        order_id = data.get('razorpay_order_id')
        
        order = razorpay_client.order.fetch(order_id)
        amount_paid = order['amount']
        notes = order.get('notes', {})
        plan = notes.get('plan', 'pro')
        
        if plan not in PLANS:
            if amount_paid == PLANS["starter"]["price"] * 100:
                plan = "starter"
            else:
                plan = "pro"
        
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
        
        user.plan = plan
        user.chat_limit = PLANS[plan]["chats"]
        user.paid_until = datetime.utcnow() + timedelta(days=30)
        db.commit()
        
        log_audit(user.id, "payment", {
            "plan": plan,
            "amount": amount_paid / 100,
            "payment_id": payment_id
        }, db)
        
        logger.info(f"✅ Payment success: {payment_id} | User: {user.id} | Plan: {plan}")
        
        asyncio.create_task(
            EmailService.send_email(
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
async def razorpay_webhook(request: Request):
    """Razorpay webhook handler for async events"""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return {"status": "webhook disabled"}
    
    try:
        body = await request.body()
        signature = request.headers.get("x-razorpay-signature")
        
        expected_signature = hmac.new(
            key=settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            msg=body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid webhook signature")
            return JSONResponse(status_code=400, content={"error": "Invalid signature"})
        
        data = json.loads(body)
        event = data.get("event")
        
        logger.info(f"📡 Razorpay webhook: {event}")
        
        asyncio.create_task(handle_razorpay_webhook_event(data))
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

async def handle_razorpay_webhook_event(data: dict):
    """Handle razorpay webhook events asynchronously"""
    event = data.get("event")
    payload = data.get("payload", {})
    
    if event == "payment.failed":
        payment_id = payload.get("payment", {}).get("entity", {}).get("id")
        logger.warning(f"Payment failed: {payment_id}")

# =====================================================
# ADMIN ROUTES
# =====================================================

@app.get("/admin", response_class=HTMLResponse)
@admin_required
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Admin dashboard"""
    try:
        users = db.query(Business).order_by(Business.created_at.desc()).all()
        
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        total_revenue = sum([p.amount for p in db.query(Payment).filter(Payment.status == "success").all()])
        total_bookings = db.query(Booking).count()
        
        recent_payments = db.query(Payment).order_by(Payment.created_at.desc()).limit(10).all()
        
        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "total_revenue": total_revenue,
            "total_bookings": total_bookings,
            "pro_users": len([u for u in users if u.plan == "pro"]),
            "trial_users": len([u for u in users if u.plan == "trial"]),
            "enterprise_users": len([u for u in users if u.plan == "enterprise"])
        }
        
        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": request,
                "users": users,
                "stats": stats,
                "recent_payments": recent_payments
            }
        )
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/admin/toggle-user/{user_id}")
@admin_required
async def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Enable/disable user account"""
    try:
        user = db.query(Business).get(user_id)
        if not user:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        
        user.is_active = not user.is_active
        db.commit()
        
        admin = get_user(request, db)
        log_audit(admin.id, "admin_toggle_user", {
            "target_user": user_id,
            "new_status": user.is_active
        }, db)
        
        logger.info(f"Admin {admin.id} toggled user {user_id} to {user.is_active}")
        
        return {"status": "success", "is_active": user.is_active}
        
    except Exception as e:
        logger.error(f"Toggle user error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to update user"})

# =====================================================
# USER ROUTES
# =====================================================

@app.get("/settings", response_class=HTMLResponse)
@login_required
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """User settings page"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "business": user
            }
        )
    except Exception as e:
        logger.error(f"Settings page error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.post("/settings")
@login_required
async def update_settings(
    request: Request,
    name: str = Form(...),
    whatsapp: str = Form(...),
    business_goal: str = Form(None),
    business_address: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update user settings"""
    try:
        user = get_user(request, db)
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
                "request": request,
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
async def bookings_page(request: Request, db: Session = Depends(get_db)):
    """View and manage all bookings"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .all()
        
        response = templates.TemplateResponse(
            "bookings.html",
            {
                "request": request,
                "business": user,
                "bookings": bookings
            }
        )
        
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        
        return response
        
    except Exception as e:
        logger.error(f"Bookings page error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

@app.get("/manage-bookings", response_class=HTMLResponse)
@login_required
async def manage_bookings(request: Request, db: Session = Depends(get_db)):
    """Bookings management page with confirm/cancel buttons"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .all()
        
        total = len(bookings)
        pending = len([b for b in bookings if b.status == "pending"])
        confirmed = len([b for b in bookings if b.status == "confirmed"])
        completed = len([b for b in bookings if b.status == "completed"])
        
        return templates.TemplateResponse(
            "manage_bookings.html",
            {
                "request": request,
                "business": user,
                "bookings": bookings,
                "stats": {
                    "total": total,
                    "pending": pending,
                    "confirmed": confirmed,
                    "completed": completed
                }
            }
        )
    except Exception as e:
        logger.error(f"Manage bookings error: {str(e)}")
        return RedirectResponse("/dashboard", 302)

# =====================================================
# EXPORT ROUTES
# =====================================================

@app.get("/export/bookings")
@login_required
async def export_bookings(request: Request, db: Session = Depends(get_db)):
    """Export bookings as CSV"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['ID', 'Name', 'Phone', 'Email', 'Date', 'Time', 'Status', 'Created At'])
        
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .all()
        
        for b in bookings:
            writer.writerow([
                b.id,
                b.name,
                b.phone,
                b.email or '',
                b.booking_date,
                b.booking_time,
                b.status,
                b.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
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
async def privacy(request: Request):
    """Privacy policy page"""
    return templates.TemplateResponse(
        "privacy.html",
        {"request": request, "now": datetime.utcnow()}
    )

@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    """Terms of service page"""
    return templates.TemplateResponse(
        "terms.html",
        {"request": request, "now": datetime.utcnow()}
    )

@app.get("/refund", response_class=HTMLResponse)
async def refund(request: Request):
    """Refund policy page"""
    return templates.TemplateResponse(
        "refund.html",
        {"request": request, "now": datetime.utcnow()}
    )

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page"""
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "now": datetime.utcnow()}
    )

@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    """Contact page"""
    return templates.TemplateResponse(
        "contact.html",
        {
            "request": request,
            "support_email": settings.SUPPORT_EMAIL,
            "now": datetime.utcnow()
        }
    )

@app.get("/ping")
async def ping():
    """Simple ping endpoint for uptime monitoring"""
    return {"ping": "pong", "time": datetime.utcnow().isoformat()}

# =====================================================
# MAIN ENTRY POINT
# =====================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        workers=4 if not settings.DEBUG else 1
    )