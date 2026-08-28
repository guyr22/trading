import os

import bcrypt
from jose import JWTError, jwt

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me-in-production-please-set-JWT_SECRET_KEY")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, email: str) -> str:
    """Mint a session token. Deliberately carries no `exp` claim: sessions
    never expire on their own, they end when the user logs out."""
    return jwt.encode(
        {"sub": str(user_id), "email": email},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
