import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


@retry(wait=wait_fixed(2), stop=stop_after_attempt(30))
def wait_for_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection established")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
