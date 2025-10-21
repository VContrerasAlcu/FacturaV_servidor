from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import random
import re
import logging

from config import settings
from database import get_user_by_email
from models import TokenData
import httpx
from config import settings

# Configurar logging
logger = logging.getLogger(__name__)

# Configuración de OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# Almacenamiento temporal para códigos de verificación (en producción usar Redis)
verification_codes = {}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creando token: {e}")
        raise

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
    except JWTError as e:
        logger.warning(f"Error decodificando token: {e}")
        raise credentials_exception
    
    user = get_user_by_email(token_data.email)
    if user is None or not user['activo']:
        logger.warning(f"Usuario no encontrado o inactivo: {token_data.email}")
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
    logger.info(f"Código de verificación almacenado para: {email}")

def validate_verification_code(email: str, code: str) -> bool:
    if email not in verification_codes:
        logger.warning(f"Código no encontrado para: {email}")
        return False
    
    stored_data = verification_codes[email]
    
    # Verificar que el código no haya expirado (10 minutos)
    if (datetime.now() - stored_data['created_at']).total_seconds() > 600:
        del verification_codes[email]
        logger.warning(f"Código expirado para: {email}")
        return False
    
    return stored_data['code'] == code

def get_verification_data(email: str):
    return verification_codes.get(email)

def remove_verification_code(email: str):
    if email in verification_codes:
        del verification_codes[email]
        logger.info(f"Código eliminado para: {email}")


async def verify_google_token(token: str) -> dict:
    """
    Verifica el token de Google y obtiene la información del usuario
    """
    try:
        async with httpx.AsyncClient() as client:
            # Verificar token con Google
            response = await client.get(
                f"https://www.googleapis.com/oauth2/v3/tokeninfo?id_token={token}"
            )
            
            if response.status_code != 200:
                logger.error(f"Error verificando token Google: {response.text}")
                return None
            
            user_info = response.json()
            
            # Validar audiencia (nuestro client ID)
            if user_info.get('aud') != settings.GOOGLE_CLIENT_ID:
                logger.error("Token Google: Client ID no coincide")
                return None
            
            return user_info
            
    except Exception as e:
        logger.error(f"Error verificando token Google: {e}")
        return None

def create_or_get_user_from_google(google_user: dict):
    """
    Crea o obtiene usuario basado en información de Google
    """
    email = google_user.get('email')
    if not email:
        return None
    
    # Buscar usuario existente
    user = get_user_by_email(email)
    
    if user:
        # Usuario existe, actualizar información si es necesario
        return user
    else:
        # Crear nuevo usuario
        user_data = {
            'email': email,
            'nombre': google_user.get('name', ''),
            'password': hash_password(f"google_auth_{google_user.get('sub')}"),  # Password dummy
            'activo': True
        }
        save_user(user_data)
        return get_user_by_email(email)