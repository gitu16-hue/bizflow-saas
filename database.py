from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Get database URL from environment variable, fallback to SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bizflow.db")

# Fix for Railway's PostgreSQL URL (starts with postgres:// instead of postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine with appropriate settings
if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
    # SQLite configuration (for local development)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL configuration (for production)
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,               # Number of connections to keep in pool
        max_overflow=10,            # Maximum overflow connections
        pool_pre_ping=True,         # Test connections before using
        pool_recycle=3600,          # Recycle connections after 1 hour
        echo=False                  # Set to True for SQL logging (development only)
    )

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()