from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
import re
import os
import uuid
from datetime import datetime

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
import logging

# Configurar logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar base de datos
    try:
        init_db()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")
    yield

# Inicializar aplicación FastAPI
app = FastAPI(title="FacturaV API", version="1.0.0", lifespan=lifespan)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas de autenticación
@app.post("/api/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
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
    except Exception as e:
        logger.error(f"Error en login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@app.post("/api/register")
async def register(user_data: UserCreate, background_tasks: BackgroundTasks):
    try:
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
    except Exception as e:
        logger.error(f"Error en registro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@app.post("/api/verify-code", response_model=Token)
async def verify_code(verification_request: VerificationRequest):
    try:
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
    except Exception as e:
        logger.error(f"Error en verificación: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@app.post("/api/forgot-password")
async def forgot_password(email: str, background_tasks: BackgroundTasks):
    try:
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
    except Exception as e:
        logger.error(f"Error en forgot-password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@app.post("/api/reset-password")
async def reset_password(password_request: PasswordResetRequest):
    try:
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
    except Exception as e:
        logger.error(f"Error en reset-password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@app.get("/api/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    try:
        return current_user
    except Exception as e:
        logger.error(f"Error obteniendo usuario: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

# Ruta para procesar una sola factura (mantener para compatibilidad)
@app.post("/api/upload-invoice", response_model=ProcessResponse)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Validar tipo de archivo
        if not file.content_type.startswith('image/'):
            return ProcessResponse(
                message="El archivo debe ser una imagen",
                success=False
            )
        
        # Procesar imagen con Azure Document Intelligence
        processed_data = process_image(file)
        
        if not processed_data or not processed_data[0]:
            return ProcessResponse(
                message="No se pudieron extraer datos de la factura",
                success=False
            )
        
        # Generar archivo Excel
        excel_file = generate_excel(processed_data)
        
        # Enviar por email (en background)
        background_tasks.add_task(
            send_email,
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
        logger.error(f"Error procesando factura: {e}")
        return ProcessResponse(
            message=f"Error procesando imagen: {str(e)}",
            success=False
        )

# NUEVO ENDPOINT para procesar múltiples facturas con el cambio realizado
@app.post("/api/upload-invoices", response_model=ProcessResponse)
async def upload_invoices(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Validar que se hayan subido archivos
        if not files:
            return ProcessResponse(
                message="No se han subido archivos",
                success=False
            )
        
        # Validar número máximo de archivos
        max_files = 10  # Puedes ajustar este límite
        if len(files) > max_files:
            return ProcessResponse(
                message=f"Máximo {max_files} archivos permitidos",
                success=False
            )
        
        # Validar tipos de archivo
        invalid_files = []
        valid_files = []
        
        for file in files:
            if file.content_type and file.content_type.startswith('image/'):
                valid_files.append(file)
            else:
                invalid_files.append(file.filename)
        
        if invalid_files:
            logger.warning(f"Archivos inválidos rechazados: {invalid_files}")
        
        if not valid_files:
            return ProcessResponse(
                message="Ninguno de los archivos es una imagen válida",
                success=False
            )
        
        # Procesar cada imagen
        all_processed_data = []
        processed_count = 0
        failed_count = 0
        processing_details = []

        for i, file in enumerate(valid_files):
            try:
                logger.info(f"Procesando archivo {i+1}/{len(valid_files)}: {file.filename}")
                
                # Procesar imagen con Azure Document Intelligence
                processed_data = process_image(file)
                
                if processed_data and processed_data[0]:
                    # Agregar información del archivo a los datos procesados
                    for data in processed_data:
                        data['archivo_origen'] = file.filename
                        data['numero_factura'] = f"{i+1}"
                    
                    all_processed_data.extend(processed_data)
                    processed_count += 1
                    processing_details.append(f"✓ {file.filename}: procesado exitosamente")
                    logger.info(f"Archivo {file.filename} procesado exitosamente")
                else:
                    failed_count += 1
                    processing_details.append(f"✗ {file.filename}: no se pudieron extraer datos")
                    logger.warning(f"No se pudieron extraer datos del archivo: {file.filename}")
                    
            except Exception as e:
                failed_count += 1
                processing_details.append(f"✗ {file.filename}: error - {str(e)}")
                logger.error(f"Error procesando archivo {file.filename}: {e}")
        
        # Verificar si se procesó al menos una factura
        if not all_processed_data:
            return ProcessResponse(
                message="No se pudieron procesar ninguna de las facturas",
                success=False,
                details=processing_details
            )
        
        # Generar archivo Excel con todas las facturas procesadas
        excel_file = generate_excel(all_processed_data)
        
        # Preparar mensaje de resultado
        result_message = f"Procesamiento completado: {processed_count} factura(s) procesada(s) correctamente"
        if failed_count > 0:
            result_message += f", {failed_count} factura(s) fallaron"
        
        # Preparar contenido del email
        email_subject = f"Facturas procesadas ({processed_count}) - FacturaV"
        
        email_content = f"""
        <h3>Procesamiento de facturas completado</h3>
        <p><strong>Resultado:</strong> {result_message}</p>
        <p><strong>Total de archivos procesados:</strong> {len(valid_files)}</p>
        <p><strong>Fecha de procesamiento:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h4>Detalles del procesamiento:</h4>
        <ul>
        """
        
        for detail in processing_details:
            email_content += f"<li>{detail}</li>"
        
        email_content += """
        </ul>
        <p>Adjunto encontrará el archivo Excel con los datos de todas las facturas procesadas correctamente.</p>
        """
        
        # Enviar por email (en background)
        background_tasks.add_task(
            send_email,
            current_user['email'], 
            email_subject, 
            email_content,
            excel_file, 
            f"facturas_procesadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        
        return ProcessResponse(
            message=result_message,
            success=True,
            details=processing_details,
            processed_count=processed_count,
            failed_count=failed_count,
            total_files=len(valid_files)
        )
        
    except Exception as e:
        logger.error(f"Error procesando múltiples facturas: {e}")
        return ProcessResponse(
            message=f"Error procesando las imágenes: {str(e)}",
            success=False
        )

# Ruta para verificar estado del servidor
@app.get("/")
async def root():
    return {"message": "FacturaV API está funcionando correctamente"}

# Ruta de health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "FacturaV API"
    }

# Ruta para obtener información del sistema
@app.get("/api/system-info")
async def system_info(current_user: dict = Depends(get_current_user)):
    return {
        "service": "FacturaV API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "user": current_user['email'],
        "features": {
            "single_upload": True,
            "multiple_upload": True,
            "max_files": 10
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)