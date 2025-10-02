from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Optional
import re
import io
from datetime import datetime
from PIL import Image
import logging
import zipfile
from pdf_converter import convert_images_to_pdf, convert_single_image_to_pdf

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
from email_sender import send_verification_code, send_email, send_email_with_file
from image_processor import process_image
from excel_generator import generate_excel, generate_single_excel
from contextlib import asynccontextmanager

# Configurar logging
logging.basicConfig(level=logging.INFO)
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

# Módulo para compresión de imágenes
async def compress_image(file: UploadFile, max_size_mb: int = 4, quality: int = 85) -> UploadFile:
    """
    Comprime una imagen si excede el tamaño máximo permitido
    """
    try:
        # Leer el contenido del archivo
        content = await file.read()
        
        # Verificar si necesita compresión (4MB límite de Azure DI)
        if len(content) <= max_size_mb * 1024 * 1024:
            # Resetear el archivo para lectura posterior
            file.file.seek(0)
            return file
        
        logger.info(f"Comprimiendo imagen {file.filename} de {len(content)/1024/1024:.2f}MB")
        
        # Abrir imagen con PIL
        image = Image.open(io.BytesIO(content))
        
        # Convertir a RGB si es necesario (para JPEG)
        if image.mode in ('RGBA', 'P', 'LA'):
            image = image.convert('RGB')
        
        # Calcular factor de compresión
        original_size_mb = len(content) / 1024 / 1024
        compression_ratio = (max_size_mb * 0.9) / original_size_mb  # Usar 90% del límite
        new_quality = max(40, int(quality * compression_ratio))  # Calidad mínima 40%
        
        # Comprimir imagen
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=new_quality, optimize=True)
        compressed_content = output.getvalue()
        
        logger.info(f"Imagen comprimida: {len(compressed_content)/1024/1024:.2f}MB (calidad: {new_quality}%)")
        
        # Crear nuevo UploadFile con el contenido comprimido
        compressed_file = UploadFile(
            filename=f"compressed_{file.filename}",
            file=io.BytesIO(compressed_content),
            content_type='image/jpeg'
        )
        
        return compressed_file
        
    except Exception as e:
        logger.error(f"Error comprimiendo imagen {file.filename}: {e}")
        # En caso de error, devolver el archivo original
        file.file.seek(0)
        return file
def crear_zip_con_excels_y_pdfs(archivos_empresas, files_data):
    """
    Crea un archivo ZIP con todos los Excel de las empresas Y los PDFs originales
    """
    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. AGREGAR EXCELS DE EMPRESAS
            for archivo_empresa in archivos_empresas:
                empresa_nombre = archivo_empresa['empresa']
                excel_data = archivo_empresa['archivo']
                nombre_archivo = f"EXCEL_{empresa_nombre.replace(' ', '_')}_facturas.xlsx"
                zip_file.writestr(nombre_archivo, excel_data)
            
            # 2. AGREGAR PDFs ORIGINALES
            for file_data in files_data:
                filename = file_data['filename']
                content = file_data['content']
                # Crear nombre seguro para el archivo
                safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
                if not safe_name:
                    safe_name = f"documento_{hash(filename) % 10000:04d}"
                
                zip_file.writestr(f"ORIGINAL_{safe_name}", content)
                
            logger.info(f"✅ ZIP creado con {len(archivos_empresas)} Excel(s) y {len(files_data)} archivo(s) original(es)")
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        logger.error(f"❌ Error creando archivo ZIP con PDFs: {e}")
        return None

def crear_zip_con_excels(archivos_empresas):
    """
    Crea un archivo ZIP con todos los Excel de las empresas
    """
    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for archivo_empresa in archivos_empresas:
                empresa_nombre = archivo_empresa['empresa']
                excel_data = archivo_empresa['archivo']
                nombre_archivo = f"{empresa_nombre.replace(' ', '_')}_facturas.xlsx"
                zip_file.writestr(nombre_archivo, excel_data)
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        logger.error(f"❌ Error creando archivo ZIP: {e}")
        return None

def combine_multipage_data(processed_data, group_name):
    """
    Combina datos extraídos de múltiples páginas de una misma factura
    """
    if not processed_data:
        return []
    
    # Por ahora, devolvemos todos los datos como están
    # En una implementación más avanzada, podrías combinar items, totales, etc.
    for data in processed_data:
        data['procesamiento'] = 'multipagina'
        data['grupo'] = group_name
    
    return processed_data

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
        logger.info(f"📄 Procesando factura individual: {file.filename}")
        
        # Validar tipo de archivo
        if not file.content_type.startswith('image/'):
            return ProcessResponse(
                message="El archivo debe ser una imagen",
                success=False
            )
        
        # Comprimir imagen si es necesario
        compressed_file = await compress_image(file)
        
        # Procesar imagen con Azure Document Intelligence
        processed_data = process_image(compressed_file)
        
        if not processed_data or not processed_data[0]:
            return ProcessResponse(
                message="No se pudieron extraer datos de la factura",
                success=False
            )
        
        # Agregar información de origen a los datos
        for data_item in processed_data:
            data_item['archivo_origen'] = file.filename
            data_item['timestamp_procesamiento'] = datetime.now().isoformat()
        
        # Generar archivo Excel (usar función de compatibilidad para una sola factura)
        excel_file = generate_single_excel(processed_data)
        
        if not excel_file:
            return ProcessResponse(
                message="Error generando el archivo Excel",
                success=False
            )
        
        # Enviar por email (en background)
        background_tasks.add_task(
            send_email_with_file,
            current_user['email'], 
            "Factura procesada - FacturaV", 
            "Adjunto encontrará el archivo Excel con los datos de su factura procesada.",
            excel_file, 
            f"factura_{file.filename.split('.')[0]}.xlsx"
        )
        
        return ProcessResponse(
            message="Imagen procesada y enviada al email",
            success=True
        )
        
    except Exception as e:
        logger.error(f"❌ Error procesando factura individual: {e}")
        return ProcessResponse(
            message=f"Error procesando imagen: {str(e)}",
            success=False
        )

# Endpoint para procesar múltiples facturas - CON SOPORTE PARA PDFs Y ENVÍO DE ARCHIVOS ORIGINALES
# Endpoint para procesar múltiples facturas - CON CONVERSIÓN DE IMÁGENES A PDF
@app.post("/api/upload-invoices", response_model=ProcessResponse)
async def upload_invoices(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        logger.info(f"🎯 INICIO PROCESAMIENTO CON CONVERSIÓN A PDF")
        logger.info(f"📦 Número de archivos recibidos: {len(files)}")
        
        # Validar que se hayan subido archivos
        if not files:
            logger.warning("❌ No se han subido archivos")
            return ProcessResponse(
                message="No se han subido archivos",
                success=False
            )
        
        # Validar número máximo de archivos
        max_files = 10
        if len(files) > max_files:
            logger.warning(f"❌ Demasiados archivos: {len(files)} (máximo {max_files})")
            return ProcessResponse(
                message=f"Máximo {max_files} archivos permitidos",
                success=False
            )
        
        # SEPARAR ARCHIVOS POR TIPO
        pdf_files = []
        image_files = []
        invalid_files = []
        
        for file in files:
            if file.content_type == 'application/pdf':
                pdf_files.append(file)
                logger.info(f"📄 PDF detectado: {file.filename}")
            elif file.content_type and file.content_type.startswith('image/'):
                image_files.append(file)
                logger.info(f"🖼️ Imagen detectada: {file.filename} ({file.content_type})")
            else:
                invalid_files.append(file.filename)
                logger.warning(f"📛 Archivo inválido: {file.filename} ({file.content_type})")
        
        logger.info(f"📊 Archivos recibidos - PDFs: {len(pdf_files)}, Imágenes: {len(image_files)}, Inválidos: {len(invalid_files)}")
        
        if invalid_files:
            logger.warning(f"📛 Archivos inválidos rechazados: {invalid_files}")
        
        if not pdf_files and not image_files:
            logger.error("❌ Ningún archivo válido encontrado")
            return ProcessResponse(
                message="Los archivos deben ser imágenes (JPEG, PNG) o PDFs",
                success=False
            )
        
        # CONVERTIR IMÁGENES A PDFs
        converted_pdfs = []
        conversion_errors = []
        
        if image_files:
            try:
                logger.info(f"🔄 Convirtiendo {len(image_files)} imágenes a PDF...")
                
                # Convertir cada imagen individualmente a PDF
                for image_file in image_files:
                    try:
                        logger.info(f"   🔄 Convirtiendo: {image_file.filename}")
                        pdf_bytes = await convert_single_image_to_pdf(image_file)
                        
                        # Crear nombre seguro para el PDF convertido
                        original_name = image_file.filename
                        safe_name = "".join(c for c in original_name.split('.')[0] if c.isalnum() or c in (' ', '-', '_'))
                        if not safe_name:
                            safe_name = f"imagen_{hash(original_name) % 10000:04d}"
                        
                        pdf_filename = f"CONVERTED_{safe_name}.pdf"
                        
                        converted_pdfs.append({
                            'filename': pdf_filename,
                            'content': pdf_bytes,
                            'original_name': original_name,
                            'type': 'converted',
                            'size_bytes': len(pdf_bytes)
                        })
                        logger.info(f"   ✅ Imagen convertida: {original_name} → {pdf_filename} ({len(pdf_bytes)} bytes)")
                        
                    except Exception as e:
                        error_msg = f"Error convirtiendo {image_file.filename}: {str(e)}"
                        conversion_errors.append(error_msg)
                        logger.error(f"   ❌ {error_msg}")
                        
                        # Fallback: mantener la imagen original
                        try:
                            image_content = await image_file.read()
                            converted_pdfs.append({
                                'filename': image_file.filename,
                                'content': image_content,
                                'original_name': image_file.filename,
                                'type': 'image_fallback',
                                'size_bytes': len(image_content)
                            })
                            await image_file.seek(0)
                            logger.info(f"   🔄 Fallback: manteniendo imagen original {image_file.filename}")
                        except Exception as fallback_error:
                            logger.error(f"   💥 Error incluso en fallback: {fallback_error}")
                
                logger.info(f"✅ Conversión completada: {len(converted_pdfs)} archivos convertidos, {len(conversion_errors)} errores")
                
            except Exception as e:
                logger.error(f"❌ Error en conversión masiva de imágenes: {e}")
                # Fallback: mantener todas las imágenes originales
                for image_file in image_files:
                    try:
                        image_content = await image_file.read()
                        converted_pdfs.append({
                            'filename': image_file.filename,
                            'content': image_content,
                            'original_name': image_file.filename,
                            'type': 'image_fallback',
                            'size_bytes': len(image_content)
                        })
                        await image_file.seek(0)
                        logger.info(f"🔄 Fallback global: manteniendo imagen original {image_file.filename}")
                    except Exception as fallback_error:
                        logger.error(f"💥 Error en fallback global para {image_file.filename}: {fallback_error}")
        
        # PREPARAR TODOS LOS ARCHIVOS PARA PROCESAMIENTO
        all_files_to_process = []
        
        # Agregar PDFs originales
        for pdf_file in pdf_files:
            try:
                content = await pdf_file.read()
                all_files_to_process.append({
                    'file_object': pdf_file,
                    'content': content,
                    'type': 'pdf_original',
                    'filename': pdf_file.filename,
                    'original_name': pdf_file.filename,
                    'size_bytes': len(content)
                })
                await pdf_file.seek(0)
                logger.info(f"📄 PDF original listo: {pdf_file.filename} ({len(content)} bytes)")
            except Exception as e:
                logger.error(f"❌ Error preparando PDF {pdf_file.filename}: {e}")
        
        # Agregar PDFs convertidos
        for converted_pdf in converted_pdfs:
            try:
                # Crear UploadFile temporal para el PDF convertido
                temp_upload_file = UploadFile(
                    filename=converted_pdf['filename'],
                    file=io.BytesIO(converted_pdf['content']),
                    content_type='application/pdf'
                )
                all_files_to_process.append({
                    'file_object': temp_upload_file,
                    'content': converted_pdf['content'],
                    'type': converted_pdf['type'],
                    'filename': converted_pdf['filename'],
                    'original_name': converted_pdf.get('original_name', converted_pdf['filename']),
                    'size_bytes': converted_pdf['size_bytes']
                })
                logger.info(f"📄 PDF convertido listo: {converted_pdf['filename']} (de {converted_pdf['original_name']})")
            except Exception as e:
                logger.error(f"❌ Error preparando PDF convertido {converted_pdf['filename']}: {e}")
        
        logger.info(f"📦 Total archivos para procesar con Azure: {len(all_files_to_process)}")
        
        if not all_files_to_process:
            logger.error("❌ No hay archivos válidos para procesar")
            return ProcessResponse(
                message="No hay archivos válidos para procesar",
                success=False
            )
        
        # PROCESAR TODOS LOS ARCHIVOS CON AZURE
        all_processed_data = []
        processed_count = 0
        failed_count = 0
        processing_details = []
        enhanced_count = 0
        fallback_count = 0

        for i, file_data in enumerate(all_files_to_process):
            file = file_data['file_object']
            file_type = file_data['type']
            original_name = file_data['original_name']
            filename = file_data['filename']
            
            try:
                logger.info(f"🔄 Procesando archivo {i+1}/{len(all_files_to_process)}: {filename} (Original: {original_name})")
                
                # Comprimir si es necesario (para imágenes en fallback)
                if file_type == 'image_fallback':
                    compressed_file = await compress_image(file)
                else:
                    compressed_file = file
                
                # PROCESAR CON AZURE DOCUMENT INTELLIGENCE
                processed_data = process_image(compressed_file)
                
                if processed_data and len(processed_data) > 0:
                    for data_item in processed_data:
                        data_item['archivo_origen'] = original_name
                        data_item['archivo_procesado'] = filename
                        data_item['tipo_archivo'] = file_type
                        data_item['tipo_original'] = 'pdf' if file_type == 'pdf_original' else 'imagen'
                        data_item['indice_procesamiento'] = i + 1
                        data_item['timestamp_procesamiento'] = datetime.now().isoformat()
                        
                        if data_item.get('procesamiento') == 'azure_enhanced':
                            enhanced_count += 1
                        elif data_item.get('procesamiento') == 'fallback_basico':
                            fallback_count += 1
                    
                    all_processed_data.extend(processed_data)
                    processed_count += 1
                    
                    confidence_levels = [item.get('confidence_level', 'unknown') for item in processed_data]
                    enhanced_items = len([c for c in confidence_levels if c == 'enhanced'])
                    
                    # Detalle del procesamiento
                    if file_type == 'pdf_original':
                        detail = f"✓ {original_name}: {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    elif file_type == 'converted':
                        detail = f"✓ {original_name} → {filename}: {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    else:  # image_fallback
                        detail = f"✓ {original_name} (fallback): {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    
                    processing_details.append(detail)
                    logger.info(f"✅ {filename} procesado exitosamente - {len(processed_data)} elementos")
                    
                    # DEBUG: Mostrar datos extraídos
                    for j, data in enumerate(processed_data):
                        confidence = data.get('confidence_level', 'unknown')
                        logger.info(f"   📋 Factura {j+1}: {data.get('VendorName', 'No identificado')} - "
                                  f"{data.get('InvoiceId', 'Sin número')} - "
                                  f"Confianza: {confidence}")
                        
                else:
                    failed_count += 1
                    processing_details.append(f"✗ {original_name}: no se pudieron extraer datos")
                    logger.warning(f"⚠️ No se pudieron extraer datos del archivo: {original_name}")
                    
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                
                # Mensajes de error específicos
                if "too large" in error_msg.lower():
                    error_msg = "archivo demasiado grande"
                elif "timeout" in error_msg.lower():
                    error_msg = "tiempo de espera agotado"
                elif "invalid" in error_msg.lower():
                    error_msg = "formato no válido"
                elif "credential" in error_msg.lower():
                    error_msg = "error de autenticación Azure"
                
                processing_details.append(f"✗ {original_name}: error - {error_msg}")
                logger.error(f"❌ Error procesando {original_name}: {e}")

        # VERIFICAR RESULTADOS DEL PROCESAMIENTO
        logger.info(f"📊 RESULTADO DEL PROCESAMIENTO:")
        logger.info(f"   • Archivos procesados exitosamente: {processed_count}")
        logger.info(f"   • Archivos fallidos: {failed_count}")
        logger.info(f"   • Total elementos extraídos: {len(all_processed_data)}")
        logger.info(f"   • Procesamientos mejorados: {enhanced_count}")
        logger.info(f"   • Procesamientos fallback: {fallback_count}")
        logger.info(f"   • Conversiones exitosas: {len([c for c in converted_pdfs if c['type'] == 'converted'])}")
        logger.info(f"   • Conversiones fallback: {len([c for c in converted_pdfs if c['type'] == 'image_fallback'])}")

        # Verificar si se procesó al menos una factura
        if not all_processed_data:
            logger.error("❌ No se pudo procesar ninguna factura")
            return ProcessResponse(
                message="No se pudieron procesar ninguna de las facturas",
                success=False,
                details=processing_details
            )
        
        # GENERAR ARCHIVOS EXCEL POR EMPRESA
        logger.info(f"📊 Generando Excel para {len(all_processed_data)} elementos procesados...")
        archivos_empresas = generate_excel(all_processed_data)
        
        if not archivos_empresas:
            logger.error("❌ No se pudieron generar los archivos Excel")
            return ProcessResponse(
                message="Error generando los archivos de resultados",
                success=False,
                details=processing_details
            )
        
        # VERIFICAR LOS EXCEL GENERADOS
        total_empresas = len(archivos_empresas)
        total_facturas = sum(empresa['cantidad_facturas'] for empresa in archivos_empresas)
        
        logger.info(f"✅ Se generaron {total_empresas} archivos Excel para {total_facturas} facturas")
        
        for i, empresa in enumerate(archivos_empresas):
            logger.info(f"   📊 Empresa {i+1}: {empresa['empresa']} - {empresa['cantidad_facturas']} facturas")
        
        # GUARDAR ARCHIVOS ORIGINALES Y CONVERTIDOS PARA EL ZIP
        files_data = []
        
        # Agregar PDFs originales
        for pdf_file in pdf_files:
            try:
                content = await pdf_file.read()
                files_data.append({
                    'filename': f"ORIGINAL_{pdf_file.filename}",
                    'content': content,
                    'type': 'pdf_original',
                    'size_bytes': len(content)
                })
                await pdf_file.seek(0)
                logger.info(f"💾 PDF original guardado: {pdf_file.filename}")
            except Exception as e:
                logger.error(f"❌ Error guardando PDF original {pdf_file.filename}: {e}")
        
        # Agregar PDFs convertidos e imágenes de fallback
        for converted_pdf in converted_pdfs:
            files_data.append({
                'filename': converted_pdf['filename'],
                'content': converted_pdf['content'],
                'type': converted_pdf['type'],
                'original_name': converted_pdf.get('original_name'),
                'size_bytes': converted_pdf['size_bytes']
            })
            logger.info(f"💾 Archivo procesado guardado: {converted_pdf['filename']}")
        
        # CREAR ARCHIVO ZIP CON TODOS LOS EXCEL Y ARCHIVOS
        zip_file = crear_zip_con_excels_y_pdfs(archivos_empresas, files_data)
        
        if not zip_file:
            logger.error("❌ Error creando archivo ZIP")
            # Fallback: enviar solo el primer Excel
            if archivos_empresas:
                excel_data = archivos_empresas[0]['archivo']
                empresa_nombre = archivos_empresas[0]['empresa']
                zip_file = io.BytesIO(excel_data)
                zip_filename = f"{empresa_nombre.replace(' ', '_')}_facturas.xlsx"
            else:
                return ProcessResponse(
                    message="Error generando archivos de resultados",
                    success=False,
                    details=processing_details
                )
        else:
            zip_filename = f"facturas_empresas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        # PREPARAR MENSAJE DE RESULTADO
        result_message = f"Procesamiento completado: {processed_count} archivos procesados"
        
        if len(pdf_files) > 0:
            result_message += f", {len(pdf_files)} PDF(s) original(es)"
        if len(image_files) > 0:
            result_message += f", {len(image_files)} imagen(es)"
        
        successful_conversions = len([c for c in converted_pdfs if c['type'] == 'converted'])
        if successful_conversions > 0:
            result_message += f", {successful_conversions} imagen(es) convertida(s) a PDF"
        
        if enhanced_count > 0:
            result_message += f", {enhanced_count} con datos mejorados"
        if fallback_count > 0:
            result_message += f", {fallback_count} con datos básicos"
        if failed_count > 0:
            result_message += f", {failed_count} archivos fallaron"
        
        if conversion_errors:
            result_message += f", {len(conversion_errors)} error(es) en conversión"

        # PREPARAR CONTENIDO DEL EMAIL MEJORADO
        email_subject = f"Facturas procesadas ({processed_count}) - FacturaV"
        
        email_content = f"""
        <h3>Procesamiento de facturas completado</h3>
        <p><strong>Resultado:</strong> {result_message}</p>
        <p><strong>Archivos originales:</strong> {len(pdf_files)} PDF(s), {len(image_files)} imagen(es)</p>
        <p><strong>Archivos procesados:</strong> {len(all_files_to_process)}</p>
        <p><strong>Empresas detectadas:</strong> {total_empresas}</p>
        <p><strong>Facturas procesadas:</strong> {total_facturas}</p>
        <p><strong>Calidad de extracción:</strong> {enhanced_count} mejoradas, {fallback_count} básicas</p>
        <p><strong>Conversiones:</strong> {successful_conversions} imagen(es) convertida(s) a PDF</p>
        """
        
        if conversion_errors:
            email_content += f"""
            <p><strong>Errores en conversión:</strong></p>
            <ul>
            """
            for error in conversion_errors:
                email_content += f"<li>{error}</li>"
            email_content += "</ul>"
        
        email_content += f"""
        <p><strong>Fecha de procesamiento:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h4>Detalles del procesamiento:</h4>
        <ul>
        """
        
        for detail in processing_details:
            email_content += f"<li>{detail}</li>"
        
        email_content += f"""
        </ul>
        
        <h4>Empresas procesadas:</h4>
        <ul>
        """
        
        for empresa in archivos_empresas:
            email_content += f"<li><strong>{empresa['empresa']}</strong>: {empresa['cantidad_facturas']} factura(s)</li>"
        
        email_content += f"""
        </ul>
        
        <h4>Contenido del archivo ZIP:</h4>
        <ul>
            <li><strong>EXCEL_*.xlsx:</strong> Archivos Excel organizados por empresa</li>
            <li><strong>ORIGINAL_*:</strong> Archivos PDF originales subidos</li>
            <li><strong>CONVERTED_*.pdf:</strong> Imágenes convertidas a PDF</li>
            <li><strong>[nombre_imagen].jpg/png:</strong> Imágenes originales (solo en caso de error)</li>
        </ul>
        
        <h4>Notas importantes:</h4>
        <ul>
            <li><strong>Mejoradas:</strong> Azure extrajo datos clave automáticamente</li>
            <li><strong>Básicas:</strong> Se usaron datos mínimos (revisar manualmente)</li>
            <li><strong>CONVERTED_*:</strong> Imágenes convertidas a PDF para mejor procesamiento</li>
            <li><strong>Archivos originales:</strong> Incluidos para referencia y verificación</li>
        </ul>
        
        <p>Adjunto encontrará el archivo ZIP con los Excel organizados por empresa Y los archivos procesados.</p>
        """
        
        # ENVIAR POR EMAIL (EN BACKGROUND)
        background_tasks.add_task(
            send_email_with_file,
            current_user['email'], 
            email_subject, 
            email_content,
            zip_file, 
            zip_filename
        )
        
        logger.info("✅ Email programado para envío en background con Excel + archivos procesados")
        
        return ProcessResponse(
            message=result_message,
            success=True,
            details=processing_details,
            processed_count=processed_count,
            failed_count=failed_count,
            total_files=len(files),
            pdf_files=len(pdf_files),
            image_files=len(image_files),
            converted_files=successful_conversions,
            conversion_errors=len(conversion_errors),
            enhanced_extractions=enhanced_count,
            basic_extractions=fallback_count,
            total_elements=len(all_processed_data),
            empresas_procesadas=total_empresas,
            facturas_totales=total_facturas
        )
        
    except Exception as e:
        logger.error(f"💥 Error crítico procesando facturas: {e}")
        return ProcessResponse(
            message=f"Error procesando los archivos: {str(e)}",
            success=False
        )

# AGREGAR LA FUNCIÓN AUXILIAR PARA CREAR EL ZIP
def crear_zip_con_excels_y_pdfs(archivos_empresas, files_data):
    """
    Crea un archivo ZIP con todos los Excel de las empresas Y los archivos originales
    """
    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. AGREGAR EXCELS DE EMPRESAS
            for archivo_empresa in archivos_empresas:
                empresa_nombre = archivo_empresa['empresa']
                excel_data = archivo_empresa['archivo']
                # Crear nombre seguro para el archivo
                safe_empresa_name = "".join(c for c in empresa_nombre if c.isalnum() or c in (' ', '-', '_'))
                if not safe_empresa_name:
                    safe_empresa_name = f"Empresa_{hash(empresa_nombre) % 10000:04d}"
                
                nombre_archivo = f"EXCEL_{safe_empresa_name}_facturas.xlsx"
                zip_file.writestr(nombre_archivo, excel_data)
                logger.info(f"📊 Excel agregado al ZIP: {nombre_archivo}")
            
            # 2. AGREGAR ARCHIVOS ORIGINALES (PDFs/Imágenes)
            for file_data in files_data:
                filename = file_data['filename']
                content = file_data['content']
                content_type = file_data['content_type']
                
                # Crear nombre seguro para el archivo
                safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
                if not safe_name:
                    safe_name = f"documento_{hash(filename) % 10000:04d}"
                
                # Determinar extensión basada en content_type
                extension = ".pdf" if content_type == 'application/pdf' else ".jpg"
                if '.' in safe_name:
                    # Mantener extensión original si es segura
                    pass
                else:
                    safe_name += extension
                
                nombre_archivo = f"ORIGINAL_{safe_name}"
                zip_file.writestr(nombre_archivo, content)
                logger.info(f"📎 Archivo original agregado al ZIP: {nombre_archivo} ({len(content)} bytes)")
                
            logger.info(f"✅ ZIP creado con {len(archivos_empresas)} Excel(s) y {len(files_data)} archivo(s) original(es)")
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        logger.error(f"❌ Error creando archivo ZIP con archivos originales: {e}")
        return None
    

@app.post("/api/debug-azure-processing")
async def debug_azure_processing(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint especial para diagnosticar problemas con Azure Document Intelligence
    """
    try:
        logger.info(f"🔍 Iniciando diagnóstico Azure para: {file.filename}")
        
        # Configurar cliente de Azure Document Intelligence
        from azure.ai.formrecognizer import DocumentAnalysisClient
        from azure.core.credentials import AzureKeyCredential
        
        document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        
        file_data = await file.read()
        file_size_mb = len(file_data) / 1024 / 1024
        
        logger.info(f"📄 Analizando archivo: {file.filename} ({file_size_mb:.2f} MB)")
        
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=io.BytesIO(file_data)
        )
        result = poller.result()
        
        # Analizar resultados en detalle
        debug_info = {
            "filename": file.filename,
            "file_size_mb": round(file_size_mb, 2),
            "total_documents": len(result.documents),
            "azure_model": "prebuilt-invoice",
            "documents_detail": []
        }
        
        for doc_idx, doc in enumerate(result.documents):
            doc_info = {
                "document_index": doc_idx + 1,
                "doc_type": doc.doc_type,
                "confidence": doc.confidence,
                "fields_found": [],
                "all_fields_available": list(doc.fields.keys()) if doc.fields else []
            }
            
            # Listar todos los campos que Azure detectó
            if doc.fields:
                for field_name, field in doc.fields.items():
                    field_info = {
                        "field": field_name,
                        "value": str(field.value) if field and field.value else "None",
                        "confidence": field.confidence if field else 0,
                        "type": type(field.value).__name__ if field and field.value else "None"
                    }
                    doc_info["fields_found"].append(field_info)
            
            debug_info["documents_detail"].append(doc_info)
        
        logger.info(f"✅ Diagnóstico completado: {len(result.documents)} documentos analizados")
        return debug_info
        
    except Exception as e:
        logger.error(f"❌ Error en diagnóstico Azure: {e}")
        return {
            "error": str(e),
            "filename": file.filename if 'file' in locals() else "unknown",
            "azure_endpoint": settings.AZURE_FORM_RECOGNIZER_ENDPOINT
        }

@app.post("/api/test-enhanced-processing")
async def test_enhanced_processing(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint para probar el procesamiento mejorado vs el original
    """
    try:
        # Procesar con el método original
        from image_processor import process_image
        
        original_result = process_image(file)
        
        # Resetear archivo para reprocesar
        await file.seek(0)
        
        # Procesar con método mejorado (ya está integrado en process_image)
        enhanced_result = process_image(file)
        
        return {
            "filename": file.filename,
            "original_processing": {
                "total_documents": len(original_result) if original_result else 0,
                "documents": original_result
            },
            "enhanced_processing": {
                "total_documents": len(enhanced_result) if enhanced_result else 0, 
                "documents": enhanced_result
            },
            "comparison": {
                "documents_difference": len(enhanced_result) - len(original_result) if original_result and enhanced_result else 0,
                "enhancement_applied": any(doc.get('confidence_level') == 'enhanced' for doc in enhanced_result) if enhanced_result else False
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error en test-enhanced-processing: {e}")
        return {"error": str(e)}

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
        "service": "FacturaV API",
        "features": {
            "single_upload": True,
            "multiple_upload": True,
            "multipage_support": True,
            "image_compression": True,
            "max_file_size_mb": 4,
            "max_files_per_request": 10
        }
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
            "multipage_support": True,
            "image_compression": True,
            "max_files": 10,
            "max_file_size": "4MB"
        }
    }

# Endpoint de prueba para verificar que la API está funcionando
@app.get("/api/test")
async def test_endpoint():
    return {
        "message": "API funcionando correctamente",
        "timestamp": datetime.now().isoformat(),
        "endpoints_available": [
            "/api/upload-invoice",
            "/api/upload-invoices", 
            "/api/login",
            "/api/register",
            "/api/verify-code"
        ]
    }

# Endpoint para probar compresión de imágenes
@app.post("/api/test-compression")
async def test_compression(file: UploadFile = File(...)):
    try:
        original_size = len(await file.read())
        file.file.seek(0)
        
        compressed_file = await compress_image(file)
        compressed_size = len(await compressed_file.read())
        
        return {
            "original_size_mb": round(original_size / 1024 / 1024, 2),
            "compressed_size_mb": round(compressed_size / 1024 / 1024, 2),
            "compression_ratio": round((original_size - compressed_size) / original_size * 100, 1),
            "filename": file.filename
        }
    except Exception as e:
        return {"error": str(e)}

# Endpoint para debug de múltiples archivos
@app.post("/api/debug-upload")
async def debug_upload(files: List[UploadFile] = File(...)):
    """
    Endpoint especial para debug que muestra información detallada de los archivos recibidos
    """
    file_info = []
    
    for i, file in enumerate(files):
        content = await file.read()
        file_info.append({
            "index": i + 1,
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(content),
            "size_mb": round(len(content) / 1024 / 1024, 2)
        })
        # Resetear el archivo para lectura posterior
        await file.seek(0)
    
    return {
        "total_files": len(files),
        "files_received": file_info,
        "timestamp": datetime.now().isoformat()
    }

# Endpoint para test específico de generación de Excel con múltiples facturas
@app.post("/api/debug-excel")
async def debug_excel_generation(files: List[UploadFile] = File(...)):
    """
    Endpoint para debug específico del Excel
    """
    try:
        all_processed_data = []
        
        for i, file in enumerate(files):
            logger.info(f"🔍 Procesando {file.filename}...")
            
            compressed_file = await compress_image(file)
            processed_data = process_image(compressed_file)
            
            if processed_data:
                for data_item in processed_data:
                    data_item['archivo_origen'] = file.filename
                    data_item['indice'] = i + 1
                    data_item['timestamp'] = datetime.now().isoformat()
                
                all_processed_data.extend(processed_data)
                logger.info(f"✅ {file.filename} → {len(processed_data)} elementos")
            else:
                logger.warning(f"⚠️ {file.filename} → 0 elementos")
        
        # Generar Excel por empresa
        archivos_empresas = generate_excel(all_processed_data)
        
        if archivos_empresas:
            return {
                "success": True,
                "archivos_procesados": len(files),
                "elementos_totales": len(all_processed_data),
                "empresas_detectadas": len(archivos_empresas),
                "detalle_empresas": [
                    {
                        'empresa': emp['empresa'],
                        'facturas': emp['cantidad_facturas'],
                        'resumen_iva': emp['resumen_iva']
                    } for emp in archivos_empresas
                ],
                "mensaje": f"Se generaron {len(archivos_empresas)} archivos Excel"
            }
        else:
            return {
                "success": False,
                "mensaje": "Error generando Excel"
            }
            
    except Exception as e:
        logger.error(f"❌ Error en debug-excel: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/check-sendgrid")
async def check_sendgrid():
    """Endpoint para verificar la configuración de SendGrid"""
    return {
        "sendgrid_configured": bool(settings.SENDGRID_API_KEY),
        "from_email": settings.FROM_EMAIL,
        "api_key_length": len(settings.SENDGRID_API_KEY) if settings.SENDGRID_API_KEY else 0
    }

# Agrega estos endpoints en main.py para debugging

@app.get("/api/debug/email-config")
async def debug_email_config():
    """Verificar configuración de email"""
    return {
        "sendgrid_configured": bool(settings.SENDGRID_API_KEY),
        "from_email": settings.FROM_EMAIL,
        "api_key_prefix": settings.SENDGRID_API_KEY[:10] + "..." if settings.SENDGRID_API_KEY else "No configurada"
    }

@app.post("/api/debug/test-email-simple")
async def test_email_simple(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Test simple de email sin adjuntos"""
    try:
        # Email simple sin adjuntos
        success = send_email(
            current_user['email'],
            "TEST Simple - FacturaV",
            "<h1>Test Simple</h1><p>Si recibes esto, el email básico funciona.</p>"
        )
        
        return {
            "success": success,
            "message": "Email de prueba enviado" if success else "Error enviando email",
            "user_email": current_user['email']
        }
        
    except Exception as e:
        logger.error(f"❌ Error en test-email-simple: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/debug/test-email-with-attachment")
async def test_email_with_attachment(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Test de email con archivo adjunto"""
    try:
        from io import BytesIO
        
        # Crear un archivo de prueba simple
        test_content = b"Este es un archivo de prueba generado por FacturaV"
        test_file = BytesIO(test_content)
        
        success = send_email_with_file(
            current_user['email'],
            "TEST Con Adjunto - FacturaV",
            "<h1>Test con Adjunto</h1><p>Si recibes esto con el archivo, todo funciona.</p>",
            test_file,
            "test.txt"
        )
        
        return {
            "success": success,
            "message": "Email con adjunto enviado" if success else "Error enviando email con adjunto",
            "user_email": current_user['email'],
            "file_size": len(test_content)
        }
        
    except Exception as e:
        logger.error(f"❌ Error en test-email-with-attachment: {e}")
        return {"success": False, "error": str(e)}
    
@app.post("/api/debug/test-with-verified-email")
async def test_with_verified_email():
    """Test con email FROM verificado en SendGrid"""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        # Usar un dominio verificado en SendGrid
        message = Mail(
            from_email='vcapost23@gmail.com',  # Cambia esto
            to_emails='vcontrerasalcu@gmail.com',
            subject='TEST con Email Verificado',
            html_content='<h1>Test con email verificado</h1>'
        )
        
        sg = SendGridAPIClient("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")
        response = sg.send(message)
        
        return {"status": response.status_code, "success": response.status_code == 202}
        
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)