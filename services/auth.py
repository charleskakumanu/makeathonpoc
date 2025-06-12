# services/auth.py
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models.user import DBUser
from config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = getattr(settings, "SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    async def create_user(self, email: str, password: str, role: str = "employee", full_name: str = None):
        existing_user = self.db.query(DBUser).filter(DBUser.email == email).first()
        if existing_user:
            raise ValueError("User already exists")
        hashed_password = pwd_context.hash(password)
        user = DBUser(
            email=email,
            hashed_password=hashed_password,
            role=role,
            full_name=full_name
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str):
        user = self.db.query(DBUser).filter(DBUser.email == email).first()
        print(f"Authenticating user: {email}, found: {user}")
        if not user or not pwd_context.verify(password, user.hashed_password):
            raise ValueError("Invalid credentials")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.create_access_token(
            data={"sub": str(user.id), "role": user.role}, expires_delta=access_token_expires
        )
        return {
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_role": user.role,
            "user": user
        }

    def create_access_token(self, data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    async def get_current_user(self, token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = int(payload.get("sub"))
            user = self.db.query(DBUser).filter(DBUser.id == user_id).first()
            if not user:
                raise ValueError("User not found")
            return user
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except Exception:
            raise ValueError("Invalid token")

    async def refresh_token(self, token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
            user_id = int(payload.get("sub"))
            user = self.db.query(DBUser).filter(DBUser.id == user_id).first()
            if not user:
                raise ValueError("User not found")
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = self.create_access_token(
                data={"sub": str(user.id), "role": user.role}, expires_delta=access_token_expires
            )
            return {
                "access_token": access_token,
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
        except Exception:
            raise ValueError("Invalid or expired token")

    async def logout_user(self, token: str):
        # Stateless JWT: implement blacklist if needed
        pass

    async def change_password(self, token: str, old_password: str, new_password: str):
        user = await self.get_current_user(token)
        if not pwd_context.verify(old_password, user.hashed_password):
            raise ValueError("Old password is incorrect")
        user.hashed_password = pwd_context.hash(new_password)
        self.db.commit()
        self.db.refresh(user)

    async def request_password_reset(self, email: str):
        user = self.db.query(DBUser).filter(DBUser.email == email).first()
        if not user:
            raise ValueError("User not found")
        # Here you would send an email with a reset token
        # For demo, just pass
        pass

    async def reset_password(self, token: str, new_password: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = int(payload.get("sub"))
            user = self.db.query(DBUser).filter(DBUser.id == user_id).first()
            if not user:
                raise ValueError("User not found")
            user.hashed_password = pwd_context.hash(new_password)
            self.db.commit()
            self.db.refresh(user)
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except Exception:
            raise ValueError("Invalid token")
