# =====================================================
# BIZFLOW AI - ENTERPRISE SAAS PLATFORM
# VERSION 10.0 - PRODUCTION READY
# =====================================================

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
from fastapi import FastAPI, Request, Form, Depends, Response, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError

# Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.datastructures import MutableHeaders

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
from sqlalchemy import text
from sqlalchemy.orm import Session

# Rate limiting
import aioredis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# =====================================================
# ENVIRONMENT & CONFIGURATION
# =====================================================

class Settings:
    """Application settings with validation"""
    APP_NAME = "BizFlow AI"
    APP_VERSION = "10.2"
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
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

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
    logger.info(f"📊 Rate Limiting: {'✅ Enabled' if settings.REDIS_URL else '⚠️ Using memory storage'}")
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
    async def wrapper(request: Request, db: Session = Depends(get_db), *args, **kwargs):
        if not request.session.get("business_id"):
            request.session["next"] = request.url.path
            return RedirectResponse("/login", 302)
        
        user = db.query(Business).get(request.session["business_id"])
        if not user or not user.is_admin:
            return RedirectResponse("/dashboard", 302)
        
        return await func(request, db, *args, **kwargs)
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
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with detailed status"""
    try:
        # Test database
        db.execute(text("SELECT 1")).first()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Test Redis if configured
    redis_status = "not configured"
    if settings.REDIS_URL:
        try:
            redis = await aioredis.from_url(settings.REDIS_URL)
            await redis.ping()
            redis_status = "healthy"
            await redis.close()
        except Exception as e:
            redis_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "redis": redis_status,
            "razorpay": "configured" if razorpay_client else "not configured",
            "sendgrid": "configured" if settings.SENDGRID_API_KEY else "not configured"
        },
        "uptime": time.time() - start_time if 'start_time' in globals() else None
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
        logger.error(f"Dashboard error for user {getattr(user, 'id', 'unknown')}: {str(e)}")
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
        """Parse natural language booking"""
        try:
            text = text.lower().strip()
            
            # Common patterns
            patterns = [
                r'(\d{1,2})[/-](\d{1,2})\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'tomorrow\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'today\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)',
                r'next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+([a-z\s]+)'
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
                    elif len(groups) == 5:  # Next weekday pattern
                        weekday, hour, minute, ampm, name = groups
                        # Calculate next occurrence of weekday
                        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        target_day = days.index(weekday)
                        current_day = datetime.now().weekday()
                        days_ahead = target_day - current_day
                        if days_ahead <= 0:
                            days_ahead += 7
                        date = (datetime.now() + timedelta(days=days_ahead)).strftime('%d-%m-%Y')
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
                    "• tomorrow 4PM John Doe\n"
                    "• next Monday 10AM Jane Smith\n\n"
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
                "• tomorrow 4PM John Doe\n"
                "• next Monday 10AM Jane Smith\n\n"
                "Type 'cancel' to go back"
            )
        
        # Check for double booking (simplified)
        existing = db.query(Booking).filter(
            Booking.business_id == business.id,
            Booking.booking_date == booking_data['date'],
            Booking.booking_time == booking_data['time'],
            Booking.status.in_(['pending', 'confirmed'])
        ).first()
        
        if existing:
            return f"""
❌ Sorry, {booking_data['time']} on {booking_data['date']} is already booked.

Please choose another time.
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
        services = {
            "restaurant": "🍽️ Our Services:\n• Dine-in\n• Takeaway\n• Delivery\n• Private Events\n• Catering",
            "salon": "💇 Our Services:\n• Haircut & Styling\n• Coloring\n• Facial\n• Manicure/Pedicure\n• Massage",
            "gym": "💪 Our Services:\n• Personal Training\n• Group Classes\n• Yoga\n• CrossFit\n• Nutrition Counseling",
            "clinic": "🏥 Our Services:\n• General Consultation\n• Specialist Visit\n• Health Checkup\n• Vaccination\n• Lab Tests",
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

Check our website for detailed pricing and packages.
"""

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
        
        # Get payment history
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
        logger.error(traceback.format_exc())
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
            logger.error("Razorpay client not initialized")
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
            "key": settings.RAZORPAY_KEY,
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
        logger.error(traceback.format_exc())
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
            logger.error("Razorpay client not initialized")
            return {"status": "error", "message": "Payment service unavailable"}
        
        user = get_user(request, db)
        if not user:
            return {"status": "error", "message": "User not authenticated"}
        
        data = await request.json()
        
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
        
        # Log audit
        log_audit(user.id, "payment", {
            "plan": plan,
            "amount": amount_paid / 100,
            "payment_id": payment_id
        }, db)
        
        logger.info(f"✅ Payment success: {payment_id} | User: {user.id} | Plan: {plan}")
        
        # Send confirmation email (async)
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
        logger.error(traceback.format_exc())
        return {"status": "error", "message": "An error occurred processing your payment"}

@app.post("/api/razorpay-webhook")
async def razorpay_webhook(request: Request):
    """Razorpay webhook handler for async events"""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return {"status": "webhook disabled"}
    
    try:
        # Verify webhook signature
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
        
        # Parse webhook
        data = json.loads(body)
        event = data.get("event")
        
        logger.info(f"📡 Razorpay webhook: {event}")
        
        # Handle different events asynchronously
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
        # Handle failed payment (e.g., notify user)
    
    elif event == "subscription.charged":
        # Handle recurring payment success
        pass
    
    elif event == "subscription.paused":
        # Handle subscription paused
        pass

# =====================================================
# ADMIN ROUTES
# =====================================================

@app.get("/admin", response_class=HTMLResponse)
@admin_required
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
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
                "request": request,
                "users": users,
                "stats": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "inactive_users": total_users - active_users,
                    "total_revenue": total_revenue,
                    "total_bookings": total_bookings,
                    "pro_users": len([u for u in users if u.plan == "pro"]),
                    "trial_users": len([u for u in users if u.plan == "trial"]),
                    "enterprise_users": len([u for u in users if u.plan == "enterprise"])
                },
                "recent_payments": recent_payments
            }
        )
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        logger.error(traceback.format_exc())
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
        
        # Log audit
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

@app.post("/admin/make-admin/{user_id}")
@admin_required
async def make_admin(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Make user admin"""
    try:
        user = db.query(Business).get(user_id)
        if not user:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        
        user.is_admin = True
        db.commit()
        
        # Log audit
        admin = get_user(request, db)
        log_audit(admin.id, "admin_make_admin", {
            "target_user": user_id
        }, db)
        
        logger.info(f"Admin {admin.id} made user {user_id} an admin")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Make admin error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to update user"})

@app.delete("/admin/delete-user/{user_id}")
@admin_required
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete user account (soft delete)"""
    try:
        user = db.query(Business).get(user_id)
        if not user:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        
        # Store info before deletion
        user_email = user.admin_email
        user_name = user.name
        
        # Soft delete - just mark inactive and remove sensitive data
        user.is_active = False
        user.admin_email = f"deleted_{user.id}@deleted.com"
        user.whatsapp_number = f"deleted_{user.id}"
        db.commit()
        
        # Log audit
        admin = get_user(request, db)
        log_audit(admin.id, "admin_delete_user", {
            "target_user": user_id,
            "target_email": user_email,
            "target_name": user_name
        }, db)
        
        logger.info(f"Admin {admin.id} deleted user {user_id}")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Delete user error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to delete user"})

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
    """View all bookings"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get all bookings with filters
        status_filter = request.query_params.get("status")
        query = db.query(Booking).filter(Booking.business_id == user.id)
        
        if status_filter and status_filter != "all":
            query = query.filter(Booking.status == status_filter)
        
        bookings = query.order_by(Booking.booking_date.desc()).all()
        
        return templates.TemplateResponse(
            "bookings.html",
            {
                "request": request,
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
async def cancel_booking(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Cancel a booking"""
    try:
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
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Cancel booking error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to cancel booking"})

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
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Name', 'Phone', 'Email', 'Date', 'Time', 'Status', 'Created At'])
        
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
                b.email or '',
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

# =====================================================
# DEBUG ROUTES (Development Only)
# =====================================================

if settings.DEBUG:
    
    @app.get("/debug/razorpay")
    async def debug_razorpay():
        """Debug Razorpay configuration"""
        return {
            "key_present": bool(settings.RAZORPAY_KEY),
            "secret_present": bool(settings.RAZORPAY_SECRET),
            "client_initialized": razorpay_client is not None,
            "key_prefix": settings.RAZORPAY_KEY[:10] + "..." if settings.RAZORPAY_KEY else None,
            "environment": settings.ENVIRONMENT
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
    async def debug_db(db: Session = Depends(get_db)):
        """Test database connection"""
        try:
            result = db.execute("SELECT 1").first()
            return {
                "database": "connected",
                "result": result[0] if result else None,
                "tables": {
                    "businesses": db.query(Business).count(),
                    "bookings": db.query(Booking).count(),
                    "payments": db.query(Payment).count(),
                    "audit_logs": db.query(AuditLog).count(),
                    "conversations": db.query(Conversation).count()
                }
            }
        except Exception as e:
            return {"database": "error", "error": str(e)}
    
    @app.get("/debug/session")
    async def debug_session(request: Request):
        """Debug session data"""
        return {
            "session_id": request.session.get("business_id"),
            "session_data": dict(request.session)
        }

@app.get("/debug/session")
async def debug_session(request: Request, db: Session = Depends(get_db)):
    """Debug session and user data"""
    results = {
        "is_logged": is_logged(request),
        "session_id": request.session.get("business_id"),
        "session_data": dict(request.session),
    }
    
    if is_logged(request):
        user = get_user(request, db)
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
async def debug_dashboard_raw(request: Request, db: Session = Depends(get_db)):
    """Raw dashboard debug - no templates"""
    try:
        # Check login
        if not is_logged(request):
            return {"error": "Not logged in", "session": dict(request.session)}
        
        user = get_user(request, db)
        if not user:
            return {"error": "User not found in database", "session_id": request.session.get("business_id")}
        
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
# MAIN ENTRY POINT
# =====================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        workers=4 if not settings.DEBUG else 1  # Multiple workers in production
    )