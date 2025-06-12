"""
Database initialization and migration script.
Run this script to create tables and set up initial data.
"""
from config.database import engine
from models.base import Base
from models.user import DBUser
from models.profile import DBProfile
from models.job_posting import DBJobPosting
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    try:
        # Let SQLAlchemy handle dependency order
        Base.metadata.drop_all(bind=engine)  # Clean slate
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully created database tables")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

if __name__ == "__main__":
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialization completed")
