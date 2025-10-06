# pdf_converter.py - VERSIÓN CORREGIDA
import img2pdf
from PIL import Image, ImageOps
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

async def compress_image_for_pdf(image_file: UploadFile, max_size=(1200, 1600), quality=75):
    """
    Comprime y optimiza una imagen para PDF - SOLO para imágenes reales
    """
    try:
        # Verificar si es realmente una imagen
        if not image_file.content_type or not image_file.content_type.startswith('image/'):
            logger.warning(f"⚠️ No es una imagen: {image_file.filename}, saltando compresión")
            content = await image_file.read()
            await image_file.seek(0)
            return content
        
        # Leer imagen original
        image_content = await image_file.read()
        
        try:
            image = Image.open(io.BytesIO(image_content))
        except Exception as e:
            logger.warning(f"⚠️ No se pudo abrir como imagen: {image_file.filename}, error: {e}")
            await image_file.seek(0)
            return image_content
        
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
        
        await image_file.seek(0)
        return optimized_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error comprimiendo imagen {image_file.filename}: {e}")
        await image_file.seek(0)
        return await image_file.read()

async def convert_images_to_pdf(images: list) -> bytes:
    """
    Convierte una lista de imágenes a PDF optimizado
    """
    try:
        logger.info(f"🔄 Convirtiendo {len(images)} archivos a PDF...")
        
        optimized_images = []
        
        for i, image_file in enumerate(images):
            try:
                # Leer contenido directamente sin comprimir si no es imagen
                content = await image_file.read()
                
                # Verificar si es PDF (ya convertido)
                if image_file.filename.lower().endswith('.pdf') or image_file.content_type == 'application/pdf':
                    logger.info(f"📄 Archivo ya es PDF: {image_file.filename}")
                    optimized_images.append(content)
                else:
                    # Intentar comprimir como imagen
                    optimized_content = await compress_image_for_pdf(image_file)
                    optimized_images.append(optimized_content)
                    logger.info(f"✅ Archivo {image_file.filename} procesado")
                
            except Exception as e:
                logger.error(f"❌ Error procesando archivo {image_file.filename}: {e}")
                continue
        
        if not optimized_images:
            raise Exception("No hay archivos válidos para convertir a PDF")
        
        # Convertir a PDF
        pdf_bytes = img2pdf.convert(optimized_images)
        
        logger.info(f"✅ PDF generado: {len(pdf_bytes)/1024:.1f}KB, {len(optimized_images)} páginas")
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo archivos a PDF: {e}")
        raise