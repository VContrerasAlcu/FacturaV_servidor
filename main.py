from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
import re

from config import settings
from database import init_db, get_user_by_email, save_user, verify_password, hash_password
from auth import (
    create_access_token, 
    get_current_user, 
    generate_verification_code, 
    store_verification_code, 
    validate_verification_code,
    get_verification_data,
    remove_verification_code
)
from models import (
    UserCreate, 
    UserResponse, 
    Token, 
    VerificationRequest, 
    PasswordResetRequest,
    ProcessResponse
)
from email_sender import send_verification_code, send_email
from image_processor import process_image
from excel_generator import generate_excel
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# Inicializar aplicación FastAPI
app = FastAPI(title="FacturaV API", version="1.0.0", lifespan=lifespan)



# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rutas de autenticación
@app.post("/api/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_email(form_data.username)
    
    if not user or not verify_password(form_data.password, user['password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user['activo']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cuenta desactivada",
        )
    
    access_token = create_access_token(data={"sub": user['email']})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/register")
async def register(user_data: UserCreate, background_tasks: BackgroundTasks):
    # Validar formato de email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de email inválido"
        )
    
    # Verificar si el usuario ya existe
    if get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya existe"
        )
    
    # Generar código de verificación
    code = generate_verification_code()
    store_verification_code(
        user_data.email, 
        code, 
        user_data.model_dump(),
        "register"
    )
    
    # Enviar código por email (en background)
    background_tasks.add_task(send_verification_code, user_data.email, code)
    
    return {"message": "Código de verificación enviado"}

@app.post("/api/verify-code", response_model=Token)
async def verify_code(verification_request: VerificationRequest):
    if not validate_verification_code(verification_request.email, verification_request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado"
        )
    
    # Obtener datos del usuario
    verification_data = get_verification_data(verification_request.email)
    
    if verification_data['action'] == "register":
        # Crear usuario
        user_data = verification_data['user_data']
        hashed_password = hash_password(user_data['password'])
        
        user = {
            'email': user_data['email'],
            'password': hashed_password,
            'nombre': user_data.get('nombre'),
            'dni_cif': user_data.get('dni_cif'),
            'direccion': user_data.get('direccion'),
            'activo': True
        }
        
        save_user(user)
    
    # Eliminar código de verificación
    remove_verification_code(verification_request.email)
    
    # Crear token JWT
    access_token = create_access_token(data={"sub": verification_request.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/forgot-password")
async def forgot_password(email: str, background_tasks: BackgroundTasks):
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Generar código de verificación
    code = generate_verification_code()
    store_verification_code(
        email, 
        code, 
        None,
        "password_reset"
    )
    
    # Enviar código por email (en background)
    background_tasks.add_task(send_verification_code, email, code)
    
    return {"message": "Código de verificación enviado"}

@app.post("/api/reset-password")
async def reset_password(password_request: PasswordResetRequest):
    if not validate_verification_code(password_request.email, password_request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado"
        )
    
    # Actualizar contraseña
    hashed_password = hash_password(password_request.new_password)
    user = get_user_by_email(password_request.email)
    
    if user:
        user['password'] = hashed_password
        save_user(user)
    
    # Eliminar código de verificación
    remove_verification_code(password_request.email)
    
    return {"message": "Contraseña actualizada correctamente"}

@app.get("/api/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return current_user

# Ruta para procesar facturas
@app.post("/api/upload-invoice", response_model=ProcessResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Procesar imagen con Azure Document Intelligence
        processed_data = process_image(file)
        
        # Generar archivo Excel
        excel_file = generate_excel(processed_data)
        
        # Enviar por email (en background)
        send_email(
            current_user['email'], 
            "Factura procesada - FacturaV", 
            "Adjunto encontrará el archivo Excel con los datos de su factura procesada.",
            excel_file, 
            "factura.xlsx"
        )
        
        return ProcessResponse(
            message="Imagen procesada y enviada al email",
            success=True
        )
        
    except Exception as e:
        return ProcessResponse(
            message=f"Error procesando imagen: {str(e)}",
            success=False
        )

# Ruta para verificar estado del servidor
@app.get("/")
async def root():
    return {"message": "FacturaV API está funcionando correctamente"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)