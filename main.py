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
import os
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
from pdf_optimizer import PDFOptimizer
from custom_processor import CustomModelProcessor
from excel_generator_simple import generate_simplified_excel

pdf_optimizer = PDFOptimizer()
custom_processor = CustomModelProcessor()
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
# Endpoint para procesar múltiples facturas - CON AGRUPACIÓN MULTIPÁGINA
@app.post("/api/upload-invoices", response_model=ProcessResponse)
async def upload_invoices(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        logger.info(f"🎯 INICIO PROCESAMIENTO CON AGRUPACIÓN MULTIPÁGINA")
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
        
        # PROCESAR FORM DATA PARA DETECTAR AGRUPACIONES MULTIPÁGINA
        multipage_groups = {}
        single_files = []
        multipage_metadata = {}
        
        for file in files:
            filename = file.filename
            
            # DETECTAR SI ES METADATA DE MULTIPÁGINA
            if filename == "multipage_metadata":
                try:
                    content = await file.read()
                    metadata = json.loads(content.decode('utf-8'))
                    group_id = metadata.get('group_id')
                    multipage_metadata[group_id] = metadata
                    logger.info(f"📋 Metadata multipágina recibida: {group_id} - {metadata}")
                    continue
                except Exception as e:
                    logger.error(f"❌ Error procesando metadata multipágina: {e}")
                    continue
            
            # DETECTAR SI ES ARCHIVO MULTIPÁGINA
            if filename.startswith('multipage_') and '_page_' in filename:
                # Extraer group_id del nombre: multipage_GROUPID_page_NUMERO.ext
                parts = filename.split('_')
                if len(parts) >= 4:
                    group_id = parts[1]  # El group_id está en la segunda parte
                    page_num = parts[3].split('.')[0]  # El número de página
                    
                    if group_id not in multipage_groups:
                        multipage_groups[group_id] = []
                    
                    # Guardar el archivo con su metadata
                    content = await file.read()
                    multipage_groups[group_id].append({
                        'filename': filename,
                        'content': content,
                        'page_number': int(page_num),
                        'file_object': file,
                        'original_name': multipage_metadata.get(group_id, {}).get('original_name', f'multipage_{group_id}')
                    })
                    await file.seek(0)
                    logger.info(f"📄 Página {page_num} agregada al grupo {group_id}")
                else:
                    # Si no se puede parsear, tratar como archivo simple
                    single_files.append(file)
                    logger.warning(f"⚠️ No se pudo parsear nombre multipágina: {filename}")
            else:
                # ARCHIVO SIMPLE
                single_files.append(file)
                logger.info(f"📄 Archivo simple detectado: {filename}")
        
        logger.info(f"📊 Grupos detectados: {len(multipage_groups)} multipágina, {len(single_files)} simples")
        
        # CONVERTIR GRUPOS MULTIPÁGINA A PDFs ÚNICOS
        converted_multipage_pdfs = []
        
        for group_id, pages in multipage_groups.items():
            try:
                # Ordenar páginas por número
                pages.sort(key=lambda x: x['page_number'])
                logger.info(f"🔄 Convirtiendo grupo {group_id} con {len(pages)} páginas a PDF único")
                
                # Preparar archivos para conversión - CORREGIDO
                files_for_conversion = []
                for page in pages:
                    # Crear UploadFile temporal para cada página - CORREGIDO
                    temp_file = UploadFile(
                        filename=page['filename'],
                        file=io.BytesIO(page['content'])  # ✅ CORRECCIÓN AQUÍ
                    )
                    files_for_conversion.append(temp_file)
                
                # Convertir el grupo completo a un solo PDF
                pdf_bytes = await pdf_optimizer.create_optimized_pdf(files_for_conversion)
                
                original_name = pages[0]['original_name']
                pdf_filename = f"MULTIPAGE_{original_name}.pdf"
                
                converted_multipage_pdfs.append({
                    'filename': pdf_filename,
                    'content': pdf_bytes,
                    'original_name': original_name,
                    'type': 'multipage_pdf',
                    'group_id': group_id,
                    'page_count': len(pages),
                    'size_bytes': len(pdf_bytes)
                })
                
                logger.info(f"✅ Grupo {group_id} convertido a PDF único: {pdf_filename} ({len(pages)} páginas, {len(pdf_bytes)} bytes)")
                
            except Exception as e:
                logger.error(f"❌ Error convirtiendo grupo multipágina {group_id}: {e}")
                # Fallback: enviar páginas individualmente
                for page in pages:
                    # Resetear el archivo original
                    page['file_object'].file = io.BytesIO(page['content'])
                    single_files.append(page['file_object'])
                    logger.info(f"🔄 Fallback: página {page['page_number']} del grupo {group_id} enviada individualmente")
        
        # CONVERTIR ARCHIVOS SIMPLES (IMÁGENES) A PDFs
        converted_single_pdfs = []
        pdf_files = []
        
        for file in single_files:
            content = await file.read()
            file_type = file.content_type
            
            if file_type == 'application/pdf':
                # Ya es PDF, usar directamente
                pdf_files.append({
                    'filename': f"SINGLE_{file.filename}",
                    'content': content,
                    'original_name': file.filename,
                    'type': 'pdf_original',
                    'size_bytes': len(content)
                })
                logger.info(f"📄 PDF original: {file.filename}")
            elif file_type and file_type.startswith('image/'):
                # Convertir imagen a PDF
                try:
                    # Resetear el archivo para la conversión
                    file.file = io.BytesIO(content)
                    pdf_bytes = await convert_single_image_to_pdf(file)
                    converted_single_pdfs.append({
                        'filename': f"CONVERTED_{file.filename.split('.')[0]}.pdf",
                        'content': pdf_bytes,
                        'original_name': file.filename,
                        'type': 'converted_single',
                        'size_bytes': len(pdf_bytes)
                    })
                    logger.info(f"✅ Imagen convertida: {file.filename} → PDF")
                except Exception as e:
                    logger.error(f"❌ Error convirtiendo imagen {file.filename}: {e}")
                    # Fallback: mantener como imagen
                    pdf_files.append({
                        'filename': file.filename,
                        'content': content,
                        'original_name': file.filename,
                        'type': 'image_fallback',
                        'size_bytes': len(content)
                    })
            else:
                logger.warning(f"⚠️ Tipo de archivo no soportado: {file.filename} ({file_type})")
                # Tratar como binario genérico
                pdf_files.append({
                    'filename': file.filename,
                    'content': content,
                    'original_name': file.filename,
                    'type': 'unknown',
                    'size_bytes': len(content)
                })
            
            await file.seek(0)
        
        # COMBINAR TODOS LOS ARCHIVOS PARA PROCESAMIENTO - CORREGIDO
        all_files_to_process = []
        
        # Agregar PDFs multipágina convertidos
        for multipage_pdf in converted_multipage_pdfs:
            # CORREGIDO: Pasar file en el constructor
            temp_upload_file = UploadFile(
                filename=multipage_pdf['filename'],
                file=io.BytesIO(multipage_pdf['content'])  # ✅ CORRECCIÓN AQUÍ
            )
            all_files_to_process.append({
                'file_object': temp_upload_file,
                'content': multipage_pdf['content'],
                'type': multipage_pdf['type'],
                'filename': multipage_pdf['filename'],
                'original_name': multipage_pdf['original_name'],
                'group_id': multipage_pdf['group_id'],
                'page_count': multipage_pdf['page_count'],
                'size_bytes': multipage_pdf['size_bytes']
            })
        
        # Agregar PDFs simples convertidos
        for single_pdf in converted_single_pdfs:
            temp_upload_file = UploadFile(
                filename=single_pdf['filename'],
                file=io.BytesIO(single_pdf['content'])  # ✅ CORRECCIÓN AQUÍ
            )
            all_files_to_process.append({
                'file_object': temp_upload_file,
                'content': single_pdf['content'],
                'type': single_pdf['type'],
                'filename': single_pdf['filename'],
                'original_name': single_pdf['original_name'],
                'size_bytes': single_pdf['size_bytes']
            })
        
        # Agregar PDFs originales
        for pdf_file in pdf_files:
            temp_upload_file = UploadFile(
                filename=pdf_file['filename'],
                file=io.BytesIO(pdf_file['content'])  # ✅ CORRECCIÓN AQUÍ
            )
            all_files_to_process.append({
                'file_object': temp_upload_file,
                'content': pdf_file['content'],
                'type': pdf_file['type'],
                'filename': pdf_file['filename'],
                'original_name': pdf_file['original_name'],
                'size_bytes': pdf_file['size_bytes']
            })
        
        logger.info(f"📦 Total archivos para procesar con Azure: {len(all_files_to_process)}")
        logger.info(f"   • Multipágina: {len(converted_multipage_pdfs)}")
        logger.info(f"   • Simples convertidos: {len(converted_single_pdfs)}")
        logger.info(f"   • PDFs originales: {len(pdf_files)}")
        
        if not all_files_to_process:
            logger.error("❌ No hay archivos válidos para procesar")
            return ProcessResponse(
                message="No hay archivos válidos para procesar",
                success=False
            )
        
        # ... (el resto del código permanece igual hasta el final del endpoint)
        
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
            group_id = file_data.get('group_id')
            page_count = file_data.get('page_count', 1)
            
            try:
                logger.info(f"🔄 Procesando archivo {i+1}/{len(all_files_to_process)}: {filename}")
                
                if file_type == 'multipage_pdf':
                    logger.info(f"   📚 Factura multipágina: {original_name} ({page_count} páginas)")
                
                # PROCESAR CON AZURE DOCUMENT INTELLIGENCE
                processed_data = await custom_processor.process_document(file)
                
                if processed_data and len(processed_data) > 0:
                    for data_item in processed_data:
                        data_item['archivo_origen'] = original_name
                        data_item['archivo_procesado'] = filename
                        data_item['tipo_archivo'] = file_type
                        
                        if file_type == 'multipage_pdf':
                            data_item['es_multipagina'] = True
                            data_item['total_paginas'] = page_count
                            data_item['grupo_id'] = group_id
                        else:
                            data_item['es_multipagina'] = False
                            data_item['total_paginas'] = 1
                        
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
                    if file_type == 'multipage_pdf':
                        detail = f"✓ {original_name} ({page_count} páginas): {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    elif file_type == 'converted_single':
                        detail = f"✓ {original_name} → PDF: {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    elif file_type == 'pdf_original':
                        detail = f"✓ {original_name}: {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    else:
                        detail = f"✓ {original_name}: {len(processed_data)} factura(s) [{enhanced_items} mejoradas]"
                    
                    processing_details.append(detail)
                    logger.info(f"✅ {filename} procesado exitosamente - {len(processed_data)} elementos")
                    
                else:
                    failed_count += 1
                    processing_details.append(f"✗ {original_name}: no se pudieron extraer datos")
                    logger.warning(f"⚠️ No se pudieron extraer datos del archivo: {original_name}")
                    
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                processing_details.append(f"✗ {original_name}: error - {error_msg}")
                logger.error(f"❌ Error procesando {original_name}: {e}")

        # GENERAR ARCHIVOS EXCEL POR EMPRESA
        logger.info(f"📊 Generando Excel para {len(all_processed_data)} elementos procesados...")
        archivos_empresas = generate_simplified_excel(processed_data)
        
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
        
        # PREPARAR ARCHIVOS PARA EL ZIP
        files_data = []
        
        # Agregar PDFs multipágina
        for multipage_pdf in converted_multipage_pdfs:
            files_data.append({
                'filename': multipage_pdf['filename'],
                'content': multipage_pdf['content'],
                'type': multipage_pdf['type'],
                'original_name': multipage_pdf['original_name'],
                'page_count': multipage_pdf['page_count']
            })
        
        # Agregar PDFs simples
        for single_pdf in converted_single_pdfs + pdf_files:
            files_data.append({
                'filename': single_pdf['filename'],
                'content': single_pdf['content'],
                'type': single_pdf['type'],
                'original_name': single_pdf['original_name']
            })
        
        # CREAR ARCHIVO ZIP
        zip_file = crear_zip_con_excels_y_pdfs(archivos_empresas, files_data)
        
        if not zip_file:
            logger.error("❌ Error creando archivo ZIP")
            if archivos_empresas:
                # Fallback: enviar solo el primer Excel
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
        multipage_count = len(converted_multipage_pdfs)
        single_count = len(converted_single_pdfs) + len(pdf_files)
        
        result_message = f"Procesamiento completado: {processed_count} archivos procesados"
        
        if multipage_count > 0:
            result_message += f", {multipage_count} factura(s) multipágina"
        if single_count > 0:
            result_message += f", {single_count} factura(s) simple(s)"
        
        if enhanced_count > 0:
            result_message += f", {enhanced_count} con datos mejorados"
        if fallback_count > 0:
            result_message += f", {fallback_count} con datos básicos"
        if failed_count > 0:
            result_message += f", {failed_count} archivos fallaron"

        # PREPARAR CONTENIDO DEL EMAIL MEJORADO
        email_subject = f"Facturas procesadas ({processed_count}) - FacturaV"
        
        email_content = f"""
        <h3>Procesamiento de facturas completado</h3>
        <p><strong>Resultado:</strong> {result_message}</p>
        <p><strong>Facturas multipágina:</strong> {multipage_count}</p>
        <p><strong>Facturas simples:</strong> {single_count}</p>
        <p><strong>Empresas detectadas:</strong> {total_empresas}</p>
        <p><strong>Facturas procesadas:</strong> {total_facturas}</p>
        <p><strong>Calidad de extracción:</strong> {enhanced_count} mejoradas, {fallback_count} básicas</p>
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
            <li><strong>MULTIPAGE_*.pdf:</strong> Facturas multipágina convertidas a PDF único</li>
            <li><strong>CONVERTED_*.pdf:</strong> Imágenes simples convertidas a PDF</li>
            <li><strong>SINGLE_*.pdf:</strong> PDFs originales subidos</li>
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
        
        logger.info("✅ Email programado para envío en background")
        
        return ProcessResponse(
            message=result_message,
            success=True,
            details=processing_details,
            processed_count=processed_count,
            failed_count=failed_count,
            total_files=len(files),
            multipage_files=multipage_count,
            single_files=single_count,
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
                
                # Determinar content_type basado en el tipo de archivo
                content_type = file_data.get('type', 'unknown')
                
                # Crear nombre seguro para el archivo
                safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
                if not safe_name:
                    safe_name = f"documento_{hash(filename) % 10000:04d}"
                
                # Determinar extensión basada en content_type o nombre original
                if content_type == 'multipage_pdf' or filename.endswith('.pdf'):
                    safe_name += '.pdf'
                elif content_type in ['converted_single', 'image_fallback'] or any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                    safe_name += '.jpg'
                else:
                    safe_name += '.pdf'  # Default a PDF
                
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
    
@app.post("/api/test-pdf-processing")
async def test_pdf_processing(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Procesa el archivo 'prueba.pdf' exactamente igual que las facturas del móvil
    Genera Excel y lo envía por email
    """
    try:
        logger.info("🎯 INICIANDO PROCESAMIENTO DE PRUEBA.PDF")
        
        # Ruta al archivo de prueba (debes subir prueba.pdf a tu servidor)
        pdf_path = "prueba.pdf"
        
        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            logger.error(f"❌ Archivo de prueba no encontrado: {pdf_path}")
            return {
                "success": False,
                "message": f"Archivo de prueba no encontrado: {pdf_path}"
            }
        
        # Leer el archivo PDF como si fuera un UploadFile
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
        
        # Crear un UploadFile temporal con el PDF
        pdf_file = UploadFile(
            filename="prueba.pdf",
            file=io.BytesIO(pdf_content)
        )
        
        logger.info(f"📄 PDF de prueba cargado: {len(pdf_content)} bytes")
        
        # PROCESAR CON AZURE (igual que en el procesamiento normal)
        processed_data = process_image(pdf_file)
        
        if not processed_data:
            logger.error("❌ No se pudieron extraer datos del PDF de prueba")
            return {
                "success": False,
                "message": "No se pudieron extraer datos del PDF de prueba"
            }
        
        logger.info(f"✅ PDF procesado: {len(processed_data)} documentos extraídos")
        
        # Agregar información de origen a los datos (igual que en procesamiento normal)
        for data_item in processed_data:
            data_item['archivo_origen'] = "prueba.pdf"
            data_item['timestamp_procesamiento'] = datetime.now().isoformat()
        
        # GENERAR EXCEL (igual que en procesamiento normal)
        archivos_empresas = generate_excel(processed_data)
        
        if not archivos_empresas:
            logger.error("❌ Error generando Excel desde PDF de prueba")
            return {
                "success": False, 
                "message": "Error generando Excel desde PDF de prueba"
            }
        
        # PREPARAR ARCHIVOS PARA EL ZIP (igual que en procesamiento normal)
        files_data = [{
            'filename': 'prueba.pdf',
            'content': pdf_content,
            'type': 'pdf_original',
            'original_name': 'prueba.pdf'
        }]
        
        # CREAR ARCHIVO ZIP
        zip_file = crear_zip_con_excels_y_pdfs(archivos_empresas, files_data)
        
        if not zip_file:
            logger.warning("⚠️ Error creando ZIP, enviando solo Excel")
            if archivos_empresas:
                excel_data = archivos_empresas[0]['archivo']
                zip_file = io.BytesIO(excel_data)
                zip_filename = f"prueba_factura.xlsx"
            else:
                return {
                    "success": False,
                    "message": "Error generando archivos de resultados"
                }
        else:
            zip_filename = f"prueba_factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        # PREPARAR CONTENIDO DEL EMAIL
        email_subject = "✅ Prueba PDF Procesado - FacturaV"
        
        email_content = f"""
        <h3>Prueba de Procesamiento PDF Completada</h3>
        <p>Se ha procesado exitosamente el archivo <strong>prueba.pdf</strong> mediante el endpoint de prueba.</p>
        
        <h4>Resultados del procesamiento:</h4>
        <ul>
            <li><strong>Archivo procesado:</strong> prueba.pdf</li>
            <li><strong>Documentos extraídos:</strong> {len(processed_data)}</li>
            <li><strong>Empresas detectadas:</strong> {len(archivos_empresas)}</li>
            <li><strong>Fecha de procesamiento:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
        
        <h4>Empresas procesadas:</h4>
        <ul>
        """
        
        for empresa in archivos_empresas:
            email_content += f"<li><strong>{empresa['empresa']}</strong>: {empresa['cantidad_facturas']} factura(s)</li>"
        
        email_content += f"""
        </ul>
        
        <h4>Detalles de los documentos extraídos:</h4>
        <ul>
        """
        
        for i, doc in enumerate(processed_data):
            vendor = doc.get('VendorName', 'No identificado')
            invoice_id = doc.get('InvoiceId', 'Sin número')
            total = doc.get('InvoiceTotal', 0)
            email_content += f"<li>Documento {i+1}: {vendor} - {invoice_id} - {total}€</li>"
        
        email_content += """
        </ul>
        
        <p><strong>Contenido del archivo adjunto:</strong></p>
        <ul>
            <li>Archivos Excel organizados por empresa</li>
            <li>Copia del PDF original procesado</li>
        </ul>
        
        <p>Este es un email de prueba generado automáticamente.</p>
        """
        
        # ENVIAR POR EMAIL (usando el email específico que mencionaste)
        test_email = "vcontrerasalcu@gmail.com"
        
        background_tasks.add_task(
            send_email_with_file,
            test_email, 
            email_subject, 
            email_content,
            zip_file, 
            zip_filename
        )
        
        logger.info(f"✅ Email de prueba programado para: {test_email}")
        
        # INFORMACIÓN DE DEBUG PARA LA RESPUESTA
        debug_info = {
            "success": True,
            "message": f"PDF de prueba procesado exitosamente. Email enviado a {test_email}",
            "processing_details": {
                "pdf_file": "prueba.pdf",
                "documents_extracted": len(processed_data),
                "companies_detected": len(archivos_empresas),
                "email_recipient": test_email,
                "companies": [
                    {
                        'name': emp['empresa'],
                        'invoice_count': emp['cantidad_facturas']
                    } for emp in archivos_empresas
                ],
                "extracted_data_preview": [
                    {
                        'VendorName': doc.get('VendorName'),
                        'InvoiceId': doc.get('InvoiceId'),
                        'InvoiceTotal': doc.get('InvoiceTotal'),
                        'confidence_level': doc.get('confidence_level', 'unknown')
                    } for doc in processed_data
                ]
            }
        }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"💥 Error procesando PDF de prueba: {e}")
        return {
            "success": False,
            "message": f"Error procesando PDF de prueba: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)