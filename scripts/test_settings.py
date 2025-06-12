from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_settings():
    try:
        # Test Milvus settings
        logger.info(f"Milvus Host: {settings.milvus_host}")
        logger.info(f"Milvus Collection: {settings.milvus_collection_name}")
        logger.info(f"Milvus Username: {settings.milvus_username}")
        logger.info("Milvus Password is set" if settings.milvus_password else "Milvus Password is not set")
        
        # Test database settings
        logger.info(f"Database URL: {settings.database_url}")
        
        # Test security settings
        logger.info("Secret Key is set" if settings.secret_key else "Secret Key is not set")
        
        return True
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return False

if __name__ == "__main__":
    if test_settings():
        print("✅ Settings loaded successfully")
    else:
        print("❌ Error loading settings")
