from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Modelos de autenticación
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    nombre: Optional[str] = None
    dni_cif: Optional[str] = None
    direccion: Optional[str] = None

class UserResponse(BaseModel):
    email: EmailStr
    nombre: Optional[str] = None
    dni_cif: Optional[str] = None
    direccion: Optional[str] = None
    activo: bool

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
    details: Optional[List[str]] = None
    processed_count: Optional[int] = 0
    failed_count: Optional[int] = 0
    total_files: Optional[int] = 0
    unique_files_processed: Optional[int] = 0
    total_elements: Optional[int] = 0
    empresas_procesadas: Optional[int] = 0
    facturas_totales: Optional[int] = 0
    facturas_multipagina: Optional[int] = 0

# Modelos para facturas multipágina
class PaginaFacturaInfo(BaseModel):
    nombre_archivo: str
    numero_pagina: int
    total_paginas: int

class FacturaAgrupada(BaseModel):
    nombre_base: str
    paginas: List[PaginaFacturaInfo]
    es_multipagina: bool

class AgrupacionFacturasResponse(BaseModel):
    total_archivos: int
    total_facturas: int
    facturas_multipagina: int
    detalles: List[FacturaAgrupada]