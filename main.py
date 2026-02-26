# =====================================================
# BIZFLOW AI - ENTERPRISE SAAS PLATFORM
# VERSION 13.0 - ADVANCED AI POWERED
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
import pytz
from decimal import Decimal

# Third-party imports
from dotenv import load_dotenv
load_dotenv()

# FastAPI & Related
from fastapi import FastAPI, Request, Form, Depends, Response, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
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
from sqlalchemy import text, desc, func
from sqlalchemy.orm import Session

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# OAuth imports
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# =====================================================
# ENVIRONMENT & CONFIGURATION
# =====================================================

class Settings:
    """Application settings with validation"""
    APP_NAME = "BizFlow AI"
    APP_VERSION = "13.0"
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
    
    # Twilio
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
    
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
# OAUTH CONFIGURATION
# =====================================================

class OAuthConfig:
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    
    @classmethod
    def is_configured(cls):
        return bool(cls.GOOGLE_CLIENT_ID and cls.GOOGLE_CLIENT_SECRET)

# Initialize OAuth
starlette_config = Config(environ=os.environ)
oauth = OAuth(starlette_config)

# Configure Google OAuth
if OAuthConfig.GOOGLE_CLIENT_ID and OAuthConfig.GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=OAuthConfig.GOOGLE_CLIENT_ID,
        client_secret=OAuthConfig.GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'redirect_uri': f"{settings.BASE_URL}/auth/google"
        }
    )

# Configure GitHub OAuth
if OAuthConfig.GITHUB_CLIENT_ID and OAuthConfig.GITHUB_CLIENT_SECRET:
    oauth.register(
        name='github',
        client_id=OAuthConfig.GITHUB_CLIENT_ID,
        client_secret=OAuthConfig.GITHUB_CLIENT_SECRET,
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        client_kwargs={
            'scope': 'user:email',
            'redirect_uri': f"{settings.BASE_URL}/auth/github"
        }
    )

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
    
    # Log OAuth status
    if OAuthConfig.GOOGLE_CLIENT_ID and OAuthConfig.GOOGLE_CLIENT_SECRET:
        logger.info("✅ Google OAuth configured")
    else:
        logger.warning("⚠️ Google OAuth not configured")
    
    if OAuthConfig.GITHUB_CLIENT_ID and OAuthConfig.GITHUB_CLIENT_SECRET:
        logger.info("✅ GitHub OAuth configured")
    else:
        logger.warning("⚠️ GitHub OAuth not configured")
    
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
# HELPER FUNCTIONS
# =====================================================

def get_indian_time():
    """Get current time in Indian timezone"""
    ist = pytz.timezone('Asia/Kolkata')
    utc_now = datetime.utcnow()
    utc_now = utc_now.replace(tzinfo=pytz.utc)
    ist_now = utc_now.astimezone(ist)
    return ist_now

def get_template_context(request: Request, additional_context: dict = None):
    """Get base template context with common variables"""
    context = {
        "request": request,
        "now": datetime.utcnow(),
        "year": datetime.utcnow().year,
        "is_logged": is_logged(request)
    }
    if additional_context:
        context.update(additional_context)
    return context

def format_currency(amount: float) -> str:
    """Format amount as Indian currency"""
    return f"₹{amount:,.2f}"

def generate_invoice_number() -> str:
    """Generate unique invoice number"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random = secrets.token_hex(2).upper()
    return f"INV-{timestamp}-{random}"

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
            "sendgrid": "configured" if settings.SENDGRID_API_KEY else "not configured",
            "google_oauth": "configured" if OAuthConfig.GOOGLE_CLIENT_ID else "not configured",
            "github_oauth": "configured" if OAuthConfig.GITHUB_CLIENT_ID else "not configured"
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
    success = request.session.pop("login_success", None)
    
    # Get email from query parameters for pre-fill
    email_prefill = request.query_params.get("email", "")
    
    # Check if remember should be checked
    remember_checked = request.query_params.get("remember", "") == "1"
    
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request, 
            "error": error,
            "success": success,
            "email_prefill": email_prefill,
            "remember_checked": remember_checked
        }
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
# OAUTH ROUTES
# =====================================================

@app.get('/login/google')
async def login_google(request: Request):
    """Redirect to Google OAuth"""
    try:
        if not OAuthConfig.GOOGLE_CLIENT_ID:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Google login is not configured. Please use email login."
                }
            )
        
        redirect_uri = f"{settings.BASE_URL}/auth/google"
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"Google OAuth redirect error: {str(e)}")
        return RedirectResponse("/login?error=oauth_failed", 302)

@app.get('/auth/google')
async def auth_google(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            logger.error("No user info from Google")
            return RedirectResponse("/login?error=oauth_failed", 302)
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        if not email:
            logger.error("No email from Google")
            return RedirectResponse("/login?error=oauth_failed", 302)
        
        # Check if user exists
        user = db.query(Business).filter(Business.admin_email == email).first()
        
        if not user:
            # Create new user
            random_password = secrets.token_urlsafe(16)
            phone = f"oauth_{secrets.token_hex(4)}"
            
            user = Business(
                name=name,
                whatsapp_number=phone,
                admin_email=email,
                admin_password=hash_password(random_password),
                business_type="general",
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
            db.refresh(user)
            
            logger.info(f"✅ New user created via Google OAuth: {email}")
        
        # Set session
        request.session["business_id"] = user.id
        
        # Log audit
        log_audit(user.id, "oauth_login", {"provider": "google"}, db)
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        return RedirectResponse("/dashboard", 302)
        
    except Exception as e:
        logger.error(f"Google OAuth callback error: {str(e)}")
        return RedirectResponse("/login?error=oauth_failed", 302)

@app.get('/login/github')
async def login_github(request: Request):
    """Redirect to GitHub OAuth"""
    try:
        if not OAuthConfig.GITHUB_CLIENT_ID:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "GitHub login is not configured. Please use email login."
                }
            )
        
        redirect_uri = f"{settings.BASE_URL}/auth/github"
        return await oauth.github.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"GitHub OAuth redirect error: {str(e)}")
        return RedirectResponse("/login?error=oauth_failed", 302)

@app.get('/auth/github')
async def auth_github(request: Request, db: Session = Depends(get_db)):
    """Handle GitHub OAuth callback"""
    try:
        token = await oauth.github.authorize_access_token(request)
        
        # Get user info from GitHub
        resp = await oauth.github.get('user', token=token)
        user_info = resp.json()
        
        # Get user emails
        emails_resp = await oauth.github.get('user/emails', token=token)
        emails = emails_resp.json()
        
        primary_email = None
        for email_info in emails:
            if email_info.get('primary'):
                primary_email = email_info.get('email')
                break
        
        if not primary_email:
            primary_email = emails[0].get('email') if emails else None
        
        if not primary_email:
            logger.error("No email from GitHub")
            return RedirectResponse("/login?error=oauth_failed", 302)
        
        name = user_info.get('name') or user_info.get('login') or primary_email.split('@')[0]
        
        # Check if user exists
        user = db.query(Business).filter(Business.admin_email == primary_email).first()
        
        if not user:
            # Create new user
            random_password = secrets.token_urlsafe(16)
            phone = f"oauth_{secrets.token_hex(4)}"
            
            user = Business(
                name=name,
                whatsapp_number=phone,
                admin_email=primary_email,
                admin_password=hash_password(random_password),
                business_type="general",
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
            db.refresh(user)
            
            logger.info(f"✅ New user created via GitHub OAuth: {primary_email}")
        
        # Set session
        request.session["business_id"] = user.id
        
        # Log audit
        log_audit(user.id, "oauth_login", {"provider": "github"}, db)
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        return RedirectResponse("/dashboard", 302)
        
    except Exception as e:
        logger.error(f"GitHub OAuth callback error: {str(e)}")
        return RedirectResponse("/login?error=oauth_failed", 302)

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

        # Get current time in Indian timezone
        now_ist = get_indian_time()
   
        # Format date for display
        formatted_date = now_ist.strftime('%A, %B %d, %Y')
        formatted_time = now_ist.strftime('%I:%M %p')
        
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
        
        pending = db.query(Booking)\
            .filter(Booking.business_id == user.id, Booking.status == "pending")\
            .count()
        
        confirmed = db.query(Booking)\
            .filter(Booking.business_id == user.id, Booking.status == "confirmed")\
            .count()
        
        completed = db.query(Booking)\
            .filter(Booking.business_id == user.id, Booking.status == "completed")\
            .count()
        
        cancelled = db.query(Booking)\
            .filter(Booking.business_id == user.id, Booking.status == "cancelled")\
            .count()
        
        analytics = {
            "conversations": user.chat_used or 0,
            "bookings": total_bookings,
            "pending": pending,
            "confirmed": confirmed,
            "completed": completed,
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
                "now": now_ist,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
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
# WHATSAPP BOT ENGINE - ADVANCED AI POWERED VERSION
# =====================================================

class WhatsAppBot:
    """Enterprise-grade WhatsApp bot with advanced AI capabilities"""
    
    # ==================== CONSTANTS & CONFIGURATION ====================
    
    # Common typos and variations mapping
    TYPOS = {
        r'\b(tomm?orr?ow|tomorow|tommorrow|2mrw|tmr)\b': 'tomorrow',
        r'\b(today|2day|2dai)\b': 'today',
        r'\b(upcomming|comming|up coming|upcomming)\b': 'upcoming',
        r'\b(nex|nxt|nxt)\b': 'next',
        r'\b(plese|pls|plz|pleas)\b': 'please',
        r'\b(thanx|thx|thanku|thnk)\b': 'thanks',
        r'\b(ok|okay|k|kk|oki)\b': 'ok'
    }
    
    # Month name to number mapping
    MONTH_MAP = {
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
    
    # Day name to number mapping (0 = Monday, 6 = Sunday)
    DAY_MAP = {
        'monday': 0, 'mon': 0,
        'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2,
        'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
        'friday': 4, 'fri': 4,
        'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6
    }
    
    # Time patterns for regex matching
    TIME_PATTERNS = [
        r'(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)',
        r'(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)',
        r'(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)',
        r'(\d{1,2})\s*o\'?clock\s*(am|pm)?',
        r'(\d{1,2})(?::(\d{2}))?\s*hrs?',
        r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
    ]
    
    # Date patterns for regex matching
    DATE_PATTERNS = [
        r'(\d{1,2})(?:st|nd|rd|th)?\s*(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)',
        r'(\d{1,2})(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)',
        r'(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
        r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?',
        r'(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?'
    ]
    
    # ==================== CORE METHODS ====================
    
    @staticmethod
    def clean_phone(phone: str) -> str:
        """Clean and format phone number with intelligent formatting"""
        if not phone:
            return ""
        
        # Remove whatsapp prefix and non-digit characters
        phone = re.sub(r'[^\d+]', '', phone.replace("whatsapp:", "").replace("whatsapp", ""))
        
        # Handle Indian numbers
        if len(phone) == 10:
            phone = "91" + phone
        elif len(phone) == 11 and phone.startswith('0'):
            phone = "91" + phone[1:]
        elif len(phone) == 12 and phone.startswith('91'):
            pass  # Already correct format
        elif len(phone) == 13 and phone.startswith('+91'):
            phone = phone[1:]  # Remove +
        
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
    def correct_typos(text: str) -> str:
        """Correct common typos and variations in text"""
        text = text.lower().strip()
        
        # Apply typo corrections
        for pattern, replacement in WhatsAppBot.TYPOS.items():
            text = re.sub(pattern, replacement, text)
        
        return text
    
    @staticmethod
    def extract_intent(message: str) -> Dict[str, any]:
        """Extract user intent using keyword matching and NLP"""
        message_lower = message.lower()
        
        intents = {
            'greeting': ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'hola', 'namaste'],
            'booking': ['book', 'booking', 'appointment', 'reserve', 'schedule', 'fix', 'slot'],
            'services': ['services', 'menu', 'price list', 'what do you offer', 'offerings', 'treatments'],
            'location': ['location', 'address', 'where', 'directions', 'map', 'reach'],
            'contact': ['contact', 'phone', 'email', 'reach us', 'support', 'call'],
            'pricing': ['pricing', 'price', 'cost', 'rates', 'fees', 'charges', 'how much'],
            'hours': ['hours', 'timings', 'open', 'close', 'working hours', 'business hours'],
            'cancel': ['cancel', 'abort', 'stop', 'forget', 'never mind', 'ignore'],
            'help': ['help', 'support', 'assist', 'guide', 'what can you do'],
            'exit': ['exit', 'bye', 'goodbye', 'quit', 'end', 'close']
        }
        
        detected_intents = []
        for intent, keywords in intents.items():
            for keyword in keywords:
                if keyword in message_lower:
                    detected_intents.append(intent)
                    break
        
        return {
            'primary_intent': detected_intents[0] if detected_intents else 'unknown',
            'all_intents': detected_intents,
            'message_length': len(message),
            'has_numbers': bool(re.search(r'\d', message)),
            'has_time': bool(re.search(r'\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|hrs?)', message_lower)),
            'has_date': bool(re.search(r'\d{1,2}[/-]\d{1,2}', message)) or any(day in message_lower for day in WhatsAppBot.DAY_MAP.keys())
        }
    
    @staticmethod
    def parse_booking(text: str) -> Optional[Dict]:
        """
        Advanced natural language booking parser with AI capabilities
        Handles complex formats and variations
        """
        try:
            # Step 0: Preprocess text
            original_text = text
            text = text.lower().strip()
            
            # Correct common typos
            text = WhatsAppBot.correct_typos(text)
            
            # Extract intent to understand what user wants
            intent = WhatsAppBot.extract_intent(text)
            
            # Initialize variables
            day = None
            month = None
            year = datetime.now().year
            hour = None
            minute = '00'
            ampm = None
            name = "Guest"
            
            # ========== DATE PARSING ==========
            
            # Pattern 1: Relative dates (today, tomorrow, day after tomorrow)
            if 'day after tomorrow' in text:
                target_date = datetime.now() + timedelta(days=2)
                day = target_date.strftime('%d')
                month = target_date.strftime('%m')
                year = target_date.year
                
            elif 'tomorrow' in text:
                target_date = datetime.now() + timedelta(days=1)
                day = target_date.strftime('%d')
                month = target_date.strftime('%m')
                year = target_date.year
                
            elif 'today' in text:
                target_date = datetime.now()
                day = target_date.strftime('%d')
                month = target_date.strftime('%m')
                year = target_date.year
            
            # Pattern 2: Next/upcoming day (next monday, upcoming friday)
            # Improved day name detection with word boundaries
            if not day:
                for day_name, day_num in WhatsAppBot.DAY_MAP.items():
                    if re.search(r'\b' + day_name + r'\b', text):
                        current_day = datetime.now().weekday()
                        
                        # Check if it's "next", "upcoming", or "this"
                        if 'next' in text or 'upcoming' in text:
                            days_ahead = day_num - current_day
                            if days_ahead <= 0:
                                days_ahead += 7
                        elif 'this' in text:
                            days_ahead = day_num - current_day
                            if days_ahead < 0:
                                days_ahead += 7
                        else:  # Just the day name (assume upcoming)
                            days_ahead = day_num - current_day
                            if days_ahead <= 0:
                                days_ahead += 7
                        
                        target_date = datetime.now() + timedelta(days=days_ahead)
                        day = target_date.strftime('%d')
                        month = target_date.strftime('%m')
                        year = target_date.year
                        break
            
            # Pattern 3: Numeric dates with month names
            if not day:
                for pattern in WhatsAppBot.DATE_PATTERNS[:3]:  # Month name patterns
                    match = re.search(pattern, text)
                    if match:
                        groups = match.groups()
                        if len(groups) == 2:
                            # Check if first group is digit (day) or month name
                            if groups[0].isdigit():
                                day_num, month_name = groups
                                day = day_num.zfill(2)
                                month = WhatsAppBot.MONTH_MAP.get(month_name[:3].lower())
                            else:
                                month_name, day_num = groups
                                day = day_num.zfill(2)
                                month = WhatsAppBot.MONTH_MAP.get(month_name[:3].lower())
                        break
            
            # Pattern 4: DD/MM or DD-MM format
            if not day:
                for pattern in WhatsAppBot.DATE_PATTERNS[3:]:
                    match = re.search(pattern, text)
                    if match:
                        groups = match.groups()
                        if len(groups) == 2:  # DD/MM
                            day_num, month_num = groups
                            day = day_num.zfill(2)
                            month = month_num.zfill(2)
                        elif len(groups) == 3 and groups[2]:  # DD/MM/YYYY
                            day_num, month_num, year_num = groups
                            day = day_num.zfill(2)
                            month = month_num.zfill(2)
                            year = int(year_num) if len(year_num) == 4 else 2000 + int(year_num)
                        break
            
            if not day:
                logger.warning(f"❌ No date detected in text: {text}")
                return None
            
            # ========== TIME PARSING ==========
            
            for pattern in WhatsAppBot.TIME_PATTERNS:
                time_match = re.search(pattern, text)
                if time_match:
                    groups = time_match.groups()
                    if len(groups) == 2 and groups[1] and groups[1].replace('.', '').lower() in ['am', 'pm', 'a m', 'p m']:  # "7pm" format
                        hour, ampm = groups[0], groups[1]
                    elif len(groups) == 2:  # "7" without am/pm
                        hour = groups[0]
                        ampm = None
                    elif len(groups) == 3 and groups[1] is None:  # "7 pm" format
                        hour, _, ampm = groups
                    elif len(groups) == 3 and groups[1] is not None:  # "7:30pm" format
                        hour, minute, ampm = groups
                    break
            
            if not time_match and intent.get('has_time'):
                # Try to extract any number that might be time
                numbers = re.findall(r'\b(\d{1,2})\b', text)
                if numbers:
                    hour = numbers[-1]  # Take the last number as time
                    ampm = None
                    logger.info(f"⏰ Extracted hour from numbers: {hour}")
            
            if not time_match and not intent.get('has_time'):
                # No time specified, use default
                hour = "12"
                ampm = "pm"
                logger.info("⏰ No time specified, using default 12pm")
            
            if not hour:
                logger.warning("❌ No time detected in text")
                return None
            
            # ========== NAME EXTRACTION ==========
            
            # Remove date and time parts from text to extract name
            clean_text = text
            
            # Remove date parts
            if 'day after tomorrow' in original_text.lower():
                clean_text = clean_text.replace('day after tomorrow', '')
            if 'tomorrow' in original_text.lower():
                clean_text = clean_text.replace('tomorrow', '')
            if 'today' in original_text.lower():
                clean_text = clean_text.replace('today', '')
            
            # Remove day names
            for day_name in WhatsAppBot.DAY_MAP.keys():
                clean_text = re.sub(r'\b' + day_name + r'\b', '', clean_text)
            
            # Remove time patterns
            clean_text = re.sub(r'\d{1,2}\s*(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|hrs?)?', '', clean_text)
            
            # Remove month names
            for month_name in WhatsAppBot.MONTH_MAP.keys():
                clean_text = re.sub(r'\b' + month_name + r'\b', '', clean_text)
            
            # Remove common words and clean up
            clean_text = re.sub(r'\b(at|on|by|for|with|and|the|a|an)\b', '', clean_text)
            clean_text = re.sub(r'[^\w\s]', '', clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # If we have a name, use it
            if clean_text and len(clean_text) > 1:
                name = clean_text.title()
                logger.info(f"👤 Extracted name: {name}")
            else:
                # Try to extract name from original text by taking words after time
                if time_match:
                    time_end = time_match.end()
                    potential_name = original_text[time_end:].strip()
                    if potential_name and len(potential_name) > 1:
                        name = potential_name.title()
                        logger.info(f"👤 Extracted name from after time: {name}")
            
            # ========== TIME FORMATTING ==========
            
            hour = int(hour)
            if ampm:
                ampm = ampm.replace('.', '').lower()
                if ampm in ['pm', 'p m'] and hour < 12:
                    hour += 12
                elif ampm in ['am', 'a m'] and hour == 12:
                    hour = 0
            
            # Validate hour range
            if hour < 0 or hour > 23:
                hour = 12  # Default to noon if invalid
            
            minute = minute.zfill(2) if minute else '00'
            time = f"{hour:02d}:{minute}"
            
            # ========== DATE VALIDATION ==========
            
            date_str = f"{day}-{month}-{year}"
            logger.info(f"📅 Final date string: {date_str}")
            
            try:
                booking_date = datetime.strptime(date_str, '%d-%m-%Y')
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                # If booking date is in the past, adjust year
                if booking_date < today:
                    logger.info(f"📅 Date {date_str} is in the past, adjusting year")
                    days_diff = (today - booking_date).days
                    if days_diff < 30:
                        next_year = year + 1
                        date_str = f"{day}-{month}-{next_year}"
                        logger.info(f"📅 Adjusted to: {date_str}")
                    elif days_diff < 365:
                        next_year = year + 1
                        date_str = f"{day}-{month}-{next_year}"
                        logger.info(f"📅 Adjusted to: {date_str}")
            except Exception as e:
                logger.error(f"❌ Date parsing error: {str(e)}")
                return None
            
            return {
                "date": date_str,
                "time": time,
                "name": name,
                "original_text": original_text,
                "confidence": "high" if intent.get('has_date') and intent.get('has_time') else "medium"
            }
            
        except Exception as e:
            logger.error(f"Booking parse error: {str(e)}")
            return None
    
    @staticmethod
    def process_message(phone: str, message: str, business, db) -> str:
        """Process incoming WhatsApp message with advanced AI"""
        message = message.strip()
        lower_msg = message.lower()
        
        # First, correct typos and understand intent
        corrected_msg = WhatsAppBot.correct_typos(message)
        intent = WhatsAppBot.extract_intent(corrected_msg)
        
        state = business.flow_state or "start"
        
        logger.info(f"🤖 Processing message - State: {state}, Intent: {intent['primary_intent']}")
        
        # Smart reset detection - understands various ways to restart
        reset_phrases = [
            "reset", "restart", "help", "menu", "main menu", "start over",
            "hi", "hello", "hey", "start", "hii", "hy", "namaste",
            "go back", "back to menu", "main", "options", "what can you do"
        ]
        
        if any(phrase in lower_msg for phrase in reset_phrases) or intent['primary_intent'] in ['greeting', 'help']:
            logger.info("🔄 Reset detected, showing main menu")
            business.flow_state = "menu"
            db.commit()
            return WhatsAppBot.get_industry_menu(business)
        
        # Handle based on state and intent
        if state == "start" or state == "menu":
            return WhatsAppBot._handle_menu(message, business, db, intent)
        elif state == "booking":
            return WhatsAppBot._handle_booking(message, phone, business, db, intent)
        elif state == "confirmation":
            return WhatsAppBot._handle_confirmation(message, phone, business, db)
        else:
            business.flow_state = "menu"
            db.commit()
            return WhatsAppBot.get_industry_menu(business)
    
    @staticmethod
    def _handle_menu(message: str, business, db, intent: Dict = None) -> str:
        """Handle menu selection with AI-powered understanding"""
        message = message.strip().lower()
        
        # Intelligent option mapping
        option_mapping = {
            '1': ['1', 'one', 'option 1'],
            '2': ['2', 'two', 'option 2'],
            '3': ['3', 'three', 'option 3'],
            '4': ['4', 'four', 'option 4'],
            '5': ['5', 'five', 'option 5'],
            '6': ['6', 'six', 'option 6']
        }
        
        # Natural language to option mapping
        selected_option = None
        if intent:
            if intent['primary_intent'] == 'booking':
                selected_option = '1'
            elif intent['primary_intent'] == 'services':
                selected_option = '2'
            elif intent['primary_intent'] in ['location', 'hours']:
                selected_option = '3'
            elif intent['primary_intent'] == 'contact':
                selected_option = '4'
            elif intent['primary_intent'] == 'pricing':
                selected_option = '5'
            elif intent['primary_intent'] == 'exit':
                selected_option = '6'
        
        # If no intent match, check direct option input
        if not selected_option:
            for option, keywords in option_mapping.items():
                if any(keyword in message for keyword in keywords):
                    selected_option = option
                    break
        
        logger.info(f"📋 Menu selection: {selected_option}")
        
        if selected_option == '1':
            business.flow_state = "booking"
            db.commit()
            return (
                "📅 *Booking Details*\n\n"
                "Please provide your booking information in any format:\n\n"
                "✨ *Examples:*\n"
                "• tomorrow 5pm Yashika\n"
                "• upcoming Monday 7 pm Priya\n"
                "• 16 Mar 3PM John Doe\n"
                "• 27/02 6:30pm Rahul\n"
                "• day after tomorrow 2pm\n\n"
                "💡 *Tips:*\n"
                "• Include date, time, and name\n"
                "• Use natural language\n"
                "• Type 'cancel' to go back"
            )
        elif selected_option == '2':
            return WhatsAppBot._get_services(business)
        elif selected_option == '3':
            return WhatsAppBot._get_location(business)
        elif selected_option == '4':
            return WhatsAppBot._get_contact(business)
        elif selected_option == '5':
            return WhatsAppBot._get_pricing(business)
        elif selected_option == '6':
            business.flow_state = "start"
            db.commit()
            return "👋 Thank you for visiting! Type *'hi'* or *'menu'* to start again.\n\nHave a great day! 🌟"
        else:
            return (
                "❌ I didn't understand that.\n\n"
                "Please reply with a number (1-6) or use natural language like:\n"
                "• 'book an appointment'\n"
                "• 'show services'\n"
                "• 'location'\n"
                "• 'contact info'\n"
                "• 'pricing'\n"
                "• 'exit'"
            )
    
    @staticmethod
    def _handle_booking(message: str, phone: str, business, db, intent: Dict = None) -> str:
        """Handle booking process with advanced NLP"""
        
        logger.info(f"🔍 _handle_booking called - Phone: {phone}, Message: {message}")
        
        # Check for cancellation
        cancel_phrases = ['cancel', 'back', 'exit', 'go back', 'never mind', 'forget it', 'stop']
        if any(phrase in message.lower() for phrase in cancel_phrases):
            logger.info("❌ Booking cancelled by user")
            business.flow_state = "menu"
            db.commit()
            return "❌ Booking cancelled.\n\n" + WhatsAppBot.get_industry_menu(business)
        
        # Parse booking with advanced NLP
        booking_data = WhatsAppBot.parse_booking(message)
        logger.info(f"📊 Booking data parsed: {booking_data}")
        
        if not booking_data:
            # Try to help user by identifying what's missing
            has_numbers = bool(re.search(r'\d', message))
            has_time = bool(re.search(r'\d{1,2}(?::\d{2})?\s*(?:am|pm)?', message.lower()))
            has_date = bool(re.search(r'\d{1,2}[/-]\d{1,2}', message)) or any(day in message.lower() for day in WhatsAppBot.DAY_MAP.keys())
            
            helpful_message = "❌ *Could not understand your booking*\n\n"
            
            if not has_date and not has_time:
                helpful_message += "📅 Please include both *date* and *time*.\n\n"
            elif not has_date:
                helpful_message += "📅 Please include the *date*.\n\n"
            elif not has_time:
                helpful_message += "⏰ Please include the *time*.\n\n"
            
            helpful_message += (
                "✨ *Try these formats:*\n"
                "• tomorrow 5pm Yashika\n"
                "• upcoming Monday 7 pm Priya\n"
                "• 16 Mar 3PM John Doe\n"
                "• 27/02 6:30pm Rahul\n\n"
                "Type 'cancel' to go back"
            )
            
            return helpful_message
        
        # Check for double booking
        logger.info(f"🔍 Checking for existing booking on {booking_data['date']} at {booking_data['time']}")
        existing = db.query(Booking).filter(
            Booking.business_id == business.id,
            Booking.booking_date == booking_data['date'],
            Booking.booking_time == booking_data['time'],
            Booking.status.in_(['pending', 'confirmed'])
        ).first()
        
        if existing:
            logger.warning(f"⚠️ Time slot already booked: {booking_data['date']} {booking_data['time']}")
            # Suggest alternative times
            alternative_times = WhatsAppBot._suggest_alternative_times(business, booking_data['date'], db)
            return f"""
❌ *Time Slot Unavailable*

Sorry, {booking_data['time']} on {booking_data['date']} is already booked.

{alternative_times}

Please choose another time or type 'cancel' to go back.
"""
        
        # Create booking
        logger.info(f"✅ Creating booking for {booking_data['name']} on {booking_data['date']} at {booking_data['time']}")
        
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
        
        logger.info(f"✅ Booking created successfully with ID: {booking.id}")
        
        # Format response nicely
        booking_date_obj = datetime.strptime(booking_data['date'], '%d-%m-%Y')
        formatted_date = booking_date_obj.strftime('%A, %d %B %Y')
        
        return f"""
✅ *Booking Confirmed!*

👤 *Name:* {booking_data['name']}
📅 *Date:* {formatted_date}
⏰ *Time:* {booking_data['time']}
📱 *Phone:* {phone}

✨ *What's next?*
• You'll receive a reminder before your appointment
• To reschedule, just start a new chat
• Questions? Type 'contact' to reach us

Type *'menu'* for main menu 👋
"""
    
    @staticmethod
    def _handle_confirmation(message: str, phone: str, business, db) -> str:
        """Handle confirmation flow for complex bookings"""
        # Simple confirmation handler
        confirm_phrases = ['yes', 'confirm', 'ok', 'sure', 'proceed', 'y']
        cancel_phrases = ['no', 'cancel', 'never mind', 'stop', 'n']
    
        msg_lower = message.lower()
    
        if any(phrase in msg_lower for phrase in confirm_phrases):
            business.flow_state = "menu"
            db.commit()
            return "✅ Confirmed! Thank you.\n\n" + WhatsAppBot.get_industry_menu(business)
        elif any(phrase in msg_lower for phrase in cancel_phrases):
            business.flow_state = "menu"
            db.commit()
            return "❌ Cancelled.\n\n" + WhatsAppBot.get_industry_menu(business)
        else:
            return "Please reply with 'yes' to confirm or 'no' to cancel."
    
    @staticmethod
    def _suggest_alternative_times(business, date: str, db) -> str:
        """Suggest alternative available time slots"""
        # Get all bookings for this date
        booked_times = db.query(Booking.booking_time).filter(
            Booking.business_id == business.id,
            Booking.booking_date == date,
            Booking.status.in_(['pending', 'confirmed'])
        ).all()
        
        booked_times = [bt[0] for bt in booked_times]
        
        # Common time slots
        all_times = ['09:00', '10:00', '11:00', '12:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00']
        available_times = [t for t in all_times if t not in booked_times]
        
        if available_times:
            suggestion = "💡 *Available times on this date:*\n"
            for time in available_times[:3]:  # Show only first 3 available
                suggestion += f"• {time}\n"
            return suggestion
        else:
            return "💡 No other times available on this date. Please try another day."
    
    @staticmethod
    def _get_services(business) -> str:
        """Get enhanced services with rich formatting"""
        industry = business.business_type.lower()
        
        services_map = {
            "restaurant": """
🍽️ *Our Culinary Experience*

*Main Offerings:*
• 🍜 Dine-in Experience
• 🥡 Takeaway Orders
• 🚚 Home Delivery
• 🎉 Private Events
• 🍱 Catering Services
• 🎂 Special Occasion Booking

*Timings:* Open 7 days a week
*Special:* Weekend brunch available
""",
            "salon": """
💇 *Premium Salon Services*

*Treatments:*
• ✂️ Haircut & Styling
• 🎨 Hair Coloring
• 💆‍♀️ Facial Treatments
• 💅 Manicure/Pedicure
• 💆 Massage Therapy
• 👰 Bridal Package

*Featured:* Get 20% off on first visit
""",
            "gym": """
💪 *Fitness Center*

*Membership Includes:*
• 🏋️ Personal Training
• 🧘 Group Classes
• 🧘‍♀️ Yoga & Meditation
• 🔥 CrossFit
• 🥗 Nutrition Counseling
• ⚖️ Weight Management

*First session FREE!*
""",
            "clinic": """
🏥 *Medical Services*

*Healthcare:*
• 👨‍⚕️ General Consultation
• 🔬 Specialist Visit
• 📋 Health Checkup
• 💉 Vaccination
• 🧪 Lab Tests
• 🚑 Emergency Care

*Insurance accepted*
""",
            "realestate": """
🏠 *Real Estate Services*

*Solutions:*
• 📍 Property Listings
• 🏃 Site Visits
• 💰 Home Loans Assistance
• 📄 Legal Documentation
• 🎨 Interior Design
• 🏢 Property Management

*Free consultation*
""",
            "education": """
📚 *Educational Services*

*Programs:*
• 🎯 Demo Classes
• 📝 Course Counseling
• 📖 Study Materials
• 💻 Online Classes
• 🎓 Career Guidance
• 💰 Scholarship Info

*Quality education for all*
""",
            "automotive": """
🚗 *Auto Service Center*

*Services:*
• 🔧 Regular Service
• 🔩 Repair Work
• ⚙️ Spare Parts
• 🧼 Detailing
• 📋 Insurance Claim
• 🚐 Roadside Assistance

*Free pickup & drop*
"""
        }
        
        return services_map.get(industry, """
📋 *Our Services*

• 💼 General Consultation
• ℹ️ Information Services
• 🤝 Customer Support
• 🌐 Visit our website for complete details

*We're here to help!*
""")
    
    @staticmethod
    def _get_location(business) -> str:
        """Get enhanced location with map link"""
        addr = business.address or "📍 Main Location"
        hours = business.business_hours or "Monday - Friday: 9AM - 8PM\nSaturday: 10AM - 6PM\nSunday: Closed"
        
        # Generate Google Maps link
        maps_link = f"https://www.google.com/maps/search/?api=1&query={addr.replace(' ', '+')}"
        
        return f"""
📍 *Location & Hours*

*Address:*
{addr}

🕒 *Business Hours:*
{hours}

🗺️ *Get Directions:*
{maps_link}

*Need help finding us?* Just ask! 🚗
"""
    
    @staticmethod
    def _get_contact(business) -> str:
        """Get enhanced contact information"""
        return f"""
📞 *Contact Us*

📱 *Phone:* {business.whatsapp_number}
📧 *Email:* {business.admin_email}

⏰ *Response Time:* Within 2 hours

*For urgent inquiries, please call during business hours.*

*Connect with us on social media:* 🌐
• Instagram: @bizflow.ai
• Facebook: /bizflowai

*We're here to help!* 💬
"""
    
    @staticmethod
    def _get_pricing(business) -> str:
        """Get enhanced pricing information"""
        industry = business.business_type.lower()
        
        pricing_map = {
            "restaurant": """
💰 *Restaurant Pricing*

*Starters:* ₹150 - ₹350
*Main Course:* ₹250 - ₹600
*Desserts:* ₹100 - ₹250
*Beverages:* ₹50 - ₹200

🎉 *Special Offers:*
• 10% off on group bookings (4+ people)
• Happy Hours: 4-7 PM (Mon-Fri)
• Birthday special: Free dessert
""",
            "salon": """
💰 *Salon Prices*

*Haircut:* ₹199 - ₹499
*Hair Color:* ₹999 - ₹2999
*Facial:* ₹599 - ₹1499
*Manicure:* ₹399
*Pedicure:* ₹499
*Massage:* ₹999 - ₹1999

🎁 *First Visit:* 20% off on any service
""",
            "gym": """
💰 *Gym Membership*

*Monthly:* ₹1999
*Quarterly:* ₹5499 (Save 8%)
*Yearly:* ₹17999 (Save 25%)

*Personal Training:* ₹500/session

✨ *First session FREE!*
""",
            "clinic": """
💰 *Clinic Fees*

*Consultation:* ₹500
*Specialist Visit:* ₹800 - ₹1500
*Health Checkup:* ₹999
*Vaccination:* ₹300 - ₹1000

*Insurance accepted • EMI available*
""",
            "realestate": """
💰 *Real Estate Services*

*Booking Amount:* ₹50,000
*Visit Charges:* ₹1000 (refundable)
*Documentation:* ₹5000

*Call for property pricing* 📞
""",
            "education": """
💰 *Course Fees*

*Demo Class:* FREE
*Monthly Tuition:* ₹2000 - ₹5000
*Course Fee:* ₹15000 - ₹50000
*Study Material:* Included

*Scholarships available* 🎓
""",
            "automotive": """
💰 *Service Packages*

*Basic Service:* ₹1999
*Standard Service:* ₹3499
*Comprehensive:* ₹5999
*Repair:* Quoted after inspection

*Free pickup & drop* 🚐
"""
        }
        
        return pricing_map.get(industry, """
💰 *Pricing Information*

*Basic consultation:* ₹500
*Premium services:* Starting at ₹1000

*Check our website for detailed pricing and packages.*

*Special discounts available!* 🎉
""")

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
                "conversations": conversations,
                "now": datetime.utcnow()
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
                "conversation": conversation,
                "now": datetime.utcnow()
            }
        )
    except Exception as e:
        logger.error(f"Conversation detail error: {str(e)}")
        return RedirectResponse("/conversations", 302)

# =====================================================
# DEBUG ENDPOINTS
# =====================================================

@app.get("/debug/parse/{text:path}")
async def debug_parse(text: str):
    """Test the booking parser"""
    try:
        result = WhatsAppBot.parse_booking(text)
        return {
            "input": text,
            "parsed": result,
            "success": result is not None,
            "current_time": datetime.now().isoformat(),
            "weekday": datetime.now().weekday()
        }
    except Exception as e:
        return {
            "input": text,
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/check-business/{phone}")
async def debug_check_business(phone: str, db: Session = Depends(get_db)):
    """Check if a phone number is registered"""
    clean_phone = WhatsAppBot.clean_phone(phone)
    business = db.query(Business).filter(Business.whatsapp_number == clean_phone).first()
    
    if business:
        return {
            "found": True,
            "business_id": business.id,
            "name": business.name,
            "business_type": business.business_type,
            "is_active": business.is_active,
            "plan": business.plan,
            "flow_state": business.flow_state
        }
    else:
        return {"found": False, "phone": clean_phone}

@app.get("/debug/bookings/{phone}")
async def debug_bookings(phone: str, db: Session = Depends(get_db)):
    """Check bookings for a phone number"""
    clean_phone = WhatsAppBot.clean_phone(phone)
    business = db.query(Business).filter(Business.whatsapp_number == clean_phone).first()
    
    if not business:
        return {"error": "Business not found"}
    
    bookings = db.query(Booking).filter(
        Booking.business_id == business.id
    ).order_by(Booking.created_at.desc()).all()
    
    return {
        "business": business.name,
        "total_bookings": len(bookings),
        "bookings": [
            {
                "id": b.id,
                "name": b.name,
                "date": b.booking_date,
                "time": b.booking_time,
                "status": b.status,
                "created_at": str(b.created_at)
            }
            for b in bookings
        ]
    }

@app.get("/debug/oauth-config")
async def debug_oauth_config():
    """Debug endpoint to check OAuth configuration"""
    return {
        "google_configured": bool(OAuthConfig.GOOGLE_CLIENT_ID and OAuthConfig.GOOGLE_CLIENT_SECRET),
        "github_configured": bool(OAuthConfig.GITHUB_CLIENT_ID and OAuthConfig.GITHUB_CLIENT_SECRET),
        "google_client_id_prefix": str(OAuthConfig.GOOGLE_CLIENT_ID)[:10] + "..." if OAuthConfig.GOOGLE_CLIENT_ID else None,
        "github_client_id_prefix": str(OAuthConfig.GITHUB_CLIENT_ID)[:10] + "..." if OAuthConfig.GITHUB_CLIENT_ID else None,
        "base_url": settings.BASE_URL
    }

# =====================================================
# WHATSAPP WEBHOOK
# =====================================================

@app.post("/webhook/test")
async def test_webhook(request: Request):
    """Test webhook endpoint"""
    try:
        form = await request.form()
        logger.info(f"📱 TEST WEBHOOK | Form data: {dict(form)}")
        return JSONResponse({
            "status": "received", 
            "data": dict(form),
            "message": "Test webhook working!"
        })
    except Exception as e:
        logger.error(f"Test webhook error: {str(e)}")
        return JSONResponse({
            "status": "error", 
            "message": str(e)
        }, status_code=500)

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
                "current_plan": user.plan,
                "now": datetime.utcnow()
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
        # Get current time
        now_utc = datetime.utcnow()
        
        # Get all users
        users = db.query(Business).order_by(Business.created_at.desc()).all()
        
        # Get stats
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        total_revenue = sum([p.amount for p in db.query(Payment).filter(Payment.status == "success").all()])
        total_bookings = db.query(Booking).count()
        
        # Recent payments
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
                "recent_payments": recent_payments,
                "now": now_utc
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
                "business": user,
                "now": datetime.utcnow()
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
                "success": "Settings updated successfully!",
                "now": datetime.utcnow()
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
                "bookings": bookings,
                "now": datetime.utcnow()
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
    """New bookings management page with confirm/cancel buttons"""
    try:
        user = get_user(request, db)
        if not user:
            return RedirectResponse("/login", 302)
        
        # Get current time in Indian timezone
        now_ist = get_indian_time()
        
        # Get all bookings
        bookings = db.query(Booking)\
            .filter(Booking.business_id == user.id)\
            .order_by(Booking.created_at.desc())\
            .all()
        
        # Calculate stats
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
                "now": now_ist,
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