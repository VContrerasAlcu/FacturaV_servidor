# pdf_converter.py - VERSIÓN COMPLETA CORREGIDA
import img2pdf
from PIL import Image, ImageOps
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

# REEMPLAZAR la función compress_image_for_pdf
async def compress_image_for_pdf(image_file: UploadFile, max_size=(1200, 1600), quality=75):
    """
    Comprime y optimiza una imagen para PDF - VERSIÓN CORREGIDA
    """
    try:
        # ✅ LEER EL CONTENIDO PRIMERO
        image_content = await image_file.read()
        
        # Verificar que hay contenido
        if not image_content:
            logger.error(f"❌ Contenido vacío para: {image_file.filename}")
            await image_file.seek(0)
            return await image_file.read()
        
        # ✅ CREAR NUEVO BytesIO con el contenido
        image_buffer = io.BytesIO(image_content)
        
        try:
            # Verificar que es una imagen válida
            image = Image.open(image_buffer)
            # Verificar integridad
            image.verify()
        except Exception as e:
            logger.error(f"❌ Imagen inválida {image_file.filename}: {e}")
            # Devolver contenido original como fallback
            await image_file.seek(0)
            return image_content
        
        # ✅ REABRIR LA IMAGEN después de verify()
        image_buffer.seek(0)
        image = Image.open(image_buffer)
        
        # Convertir a RGB si es necesario
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Redimensionar manteniendo aspecto (si es muy grande)
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Optimizar y comprimir
        optimized_buffer = io.BytesIO()
        image.save(
            optimized_buffer, 
            format='JPEG', 
            quality=quality,
            optimize=True,
            progressive=True
        )
        
        # ✅ RESETEAR EL ARCHIVO ORIGINAL
        await image_file.seek(0)
        
        optimized_content = optimized_buffer.getvalue()
        logger.info(f"✅ Imagen comprimida: {len(image_content)/1024:.1f}KB → {len(optimized_content)/1024:.1f}KB")
        
        return optimized_content
        
    except Exception as e:
        logger.error(f"❌ Error comprimiendo imagen {image_file.filename}: {e}")
        # Fallback: devolver contenido original
        await image_file.seek(0)
        return await image_file.read()
    
async def convert_single_image_to_pdf(image_file):
    """
    Convierte una sola imagen a PDF - FUNCIÓN NUEVA
    """
    try:
        logger.info(f"🔄 Convirtiendo imagen única a PDF: {image_file.filename}")
        
        # Usar la función existente para una sola imagen
        pdf_bytes = await convert_images_to_pdf([image_file])
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imagen única a PDF: {e}")
        raise