from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

# Modelos para request/response
class UserBase(BaseModel):
    email: EmailStr
    nombre: Optional[str] = None
    dni_cif: Optional[str] = None
    direccion: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    activo: bool
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class VerificationRequest(BaseModel):
    email: EmailStr
    code: str

class PasswordResetRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(..., min_length=6)

class ProcessResponse(BaseModel):
    message: str
    success: bool