from pymilvus import MilvusClient, DataType
from typing import List, Dict, Any, Optional
import json
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

class MilvusService:
    def __init__(self):
        self.collection_name = settings.milvus_collection_name
        self.collection = None
        self.client: Optional[MilvusClient] = None
        self._connected = False
        
    def connect(self):
        """Connect to Milvus"""
        if self._connected and self.client:
            return True
            
        try:
            # Validate settings
            if not settings.milvus_host:
                raise ValueError("Milvus host is not configured")
                
            logger.info(f"Attempting to connect to Milvus at {settings.milvus_host}")
            
            # Create connection parameters
            connection_params = {
                "uri": settings.milvus_host,
                "db_name": "default"
            }
            
            # Add auth if provided
            if hasattr(settings, 'milvus_username') and settings.milvus_username:
                connection_params["user"] = settings.milvus_username
            if hasattr(settings, 'milvus_password') and settings.milvus_password:
                connection_params["password"] = settings.milvus_password
                
            self.client = MilvusClient(**connection_params)
            self._connected = True
            logger.info(f"Successfully connected to Milvus at {settings.milvus_host}")
            
            self._create_collection_if_not_exists()
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Milvus at host {settings.milvus_host}: {e}")
            self._connected = False
            raise
    
    def _ensure_connected(self):
        """Ensure we have a valid connection"""
        if not self._connected or not self.client:
            self.connect()
    
    def _create_collection_if_not_exists(self):
        """Create collection if it doesn't exist"""
        try:
            if self.client.has_collection(self.collection_name):
                logger.info(f"Collection {self.collection_name} already exists")
            else:
                # Define the schema
                schema = MilvusClient.create_schema(
                    auto_id=False,
                    enable_dynamic_field=True,
                )
                schema.add_field(field_name="profile_id", datatype=DataType.VARCHAR, max_length=100, is_primary=True)
                schema.add_field(field_name="user_id", datatype=DataType.INT64)
                schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=settings.embedding_dimension)
                schema.add_field(field_name="full_name", datatype=DataType.VARCHAR, max_length=200)
                schema.add_field(field_name="email", datatype=DataType.VARCHAR, max_length=200)
                schema.add_field(field_name="summary", datatype=DataType.VARCHAR, max_length=30000)
                schema.add_field(field_name="skills_json", datatype=DataType.JSON, nullable=True)
                schema.add_field(field_name="metadata_json", datatype=DataType.JSON, nullable=True)

                index_params = self.client.prepare_index_params()            
                
                # Create index for vector field
                index_params.add_index(
                    field_name="embedding",
                    metric_type="IP",  # Inner Product (cosine similarity)
                    index_type="IVF_FLAT",
                    params={"nlist": 1024}
                )
                self.client.create_collection(
                    collection_name=self.collection_name,
                    schema=schema,
                    index_params=index_params
                )
                logger.info(f"Created collection {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise
    
    def insert_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Insert a single profile"""
        try:
            self._ensure_connected()
            
            # Validate required fields
            required_fields = ["profile_id", "user_id", "embedding", "full_name", "email", "summary"]
            for field in required_fields:
                if field not in profile_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Prepare data for insertion
            data = [
                {
                    "profile_id": profile_data["profile_id"],
                    "user_id": profile_data["user_id"],
                    "embedding": profile_data["embedding"],
                    "full_name": profile_data["full_name"],
                    "email": profile_data["email"],
                    "summary": profile_data["summary"],
                    "skills_json": json.dumps(profile_data.get("skills", [])),
                    "metadata_json": json.dumps(profile_data.get("metadata", {}))
                }
            ]
            
            # Insert data
            self.client.insert(collection_name=self.collection_name, data=data)
            self.client.flush(collection_name=self.collection_name)
            logger.info(f"Inserted profile {profile_data['profile_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert profile: {e}")
            return False
    
    def search_similar_profiles(self, query_embedding: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Search for similar profiles"""
        try:
            self._ensure_connected()
            
            # Load collection to memory if not already loaded
            try:
                self.client.load_collection(collection_name=self.collection_name)
            except Exception as load_error:
                logger.warning(f"Collection may already be loaded: {load_error}")
            
            # Search parameters
            search_params = {
                "metric_type": "IP",
                "params": {"nprobe": 10}
            }
            
            # Perform search
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                output_fields=["profile_id", "user_id", "full_name", "email", "summary", "skills_json", "metadata_json"]
            )
            
            # Format results
            formatted_results = []
            for hits in results:
                for hit in hits:
                    # Safely parse JSON fields
                    skills = []
                    metadata = {}
                    try:
                        skills = json.loads(hit.entity.get("skills_json", "[]"))
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Failed to parse skills_json for profile {hit.entity.get('profile_id')}")
                    
                    try:
                        metadata = json.loads(hit.entity.get("metadata_json", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Failed to parse metadata_json for profile {hit.entity.get('profile_id')}")
                    
                    result = {
                        "profile_id": hit.entity.get("profile_id"),
                        "user_id": hit.entity.get("user_id"),
                        "full_name": hit.entity.get("full_name"),
                        "email": hit.entity.get("email"),
                        "summary": hit.entity.get("summary"),
                        "similarity_score": hit.score,
                        "skills": skills,
                        "metadata": metadata
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile by ID"""
        try:
            self._ensure_connected()
            # ids parameter expects a list
            self.client.delete(collection_name=self.collection_name, ids=[profile_id])
            self.client.flush(collection_name=self.collection_name)
            logger.info(f"Deleted profile {profile_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete profile {profile_id}: {e}")
            return False
    
    def update_profile(self, profile_id: str, profile_data: Dict[str, Any]) -> bool:
        """Update a profile (delete and insert)"""
        try:
            self._ensure_connected()
            # Delete existing profile
            if not self.delete_profile(profile_id):
                return False
            
            # Insert updated profile
            profile_data["profile_id"] = profile_id
            return self.insert_profile(profile_data)
            
        except Exception as e:
            logger.error(f"Failed to update profile {profile_id}: {e}")
            return False
    
    def get_profile(self, profile_id: str) -> Dict[str, Any]:
        """Get a specific profile by ID"""
        try:
            self._ensure_connected()
            results = self.client.query(
                collection_name=self.collection_name,
                filter=f'profile_id == "{profile_id}"',
                output_fields=["profile_id", "user_id", "full_name", "email", "summary", "skills_json", "metadata_json"]
            )
            
            if results:
                result = results[0]
                return {
                    "profile_id": result.get("profile_id"),
                    "user_id": result.get("user_id"),
                    "full_name": result.get("full_name"),
                    "email": result.get("email"),
                    "summary": result.get("summary"),
                    "skills": json.loads(result.get("skills_json", "[]")),
                    "metadata": json.loads(result.get("metadata_json", "{}"))
                }
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get profile {profile_id}: {e}")
            return {}
    
    def health_check(self) -> bool:
        """Check if the service is healthy"""
        try:
            self._ensure_connected()
            return self.client.has_collection(self.collection_name)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

# Create instance but don't connect immediately
_milvus_service_instance = None

def get_milvus_service() -> MilvusService:
    """Get the Milvus service instance (lazy initialization)"""
    global _milvus_service_instance
    if _milvus_service_instance is None:
        _milvus_service_instance = MilvusService()
    return _milvus_service_instance

# For backward compatibility
milvus_service = get_milvus_service()