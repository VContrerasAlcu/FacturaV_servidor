from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import random
import re

from config import settings
from database import get_user_by_email
from models import TokenData

# Configuración de OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# Almacenamiento temporal para códigos de verificación (en producción usar Redis)
verification_codes = {}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = get_user_by_email(token_data.email)
    if user is None or not user['activo']:
        raise credentials_exception
    return user

def generate_verification_code() -> str:
    return str(random.randint(100000, 999999))

def store_verification_code(email: str, code: str, user_data: dict = None, action: str = "register"):
    verification_codes[email] = {
        'code': code,
        'user_data': user_data,
        'action': action,
        'created_at': datetime.now()
    }

def validate_verification_code(email: str, code: str) -> bool:
    if email not in verification_codes:
        return False
    
    stored_data = verification_codes[email]
    
    # Verificar que el código no haya expirado (10 minutos)
    if (datetime.now() - stored_data['created_at']).total_seconds() > 600:
        del verification_codes[email]
        return False
    
    return stored_data['code'] == code

def get_verification_data(email: str):
    return verification_codes.get(email)

def remove_verification_code(email: str):
    if email in verification_codes:
        del verification_codes[email]