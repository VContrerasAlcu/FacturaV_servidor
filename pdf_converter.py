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
        # ✅ LEER EL CONTENIDO PRIMERO Y CREAR BytesIO NUEVO
        image_content = await image_file.read()
        
        # Verificar que es una imagen válida
        if not image_content:
            raise ValueError("Contenido de imagen vacío")
        
        # ✅ CREAR NUEVO BytesIO con el contenido
        image_buffer = io.BytesIO(image_content)
        
        try:
            image = Image.open(image_buffer)
            
            # Verificar que es una imagen válida
            image.verify()  # Verificar integridad
        except Exception as e:
            logger.error(f"❌ Imagen inválida {image_file.filename}: {e}")
            # Devolver contenido original como fallback
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
        
        return optimized_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error comprimiendo imagen {image_file.filename}: {e}")
        # Fallback: devolver contenido original
        await image_file.seek(0)
        return await image_file.read()

async def convert_images_to_pdf(images: list) -> bytes:
    """
    Convierte una lista de imágenes a PDF optimizado
    """
    try:
        logger.info(f"🔄 Convirtiendo {len(images)} imágenes a PDF optimizado...")
        
        optimized_images = []
        total_original_size = 0
        total_optimized_size = 0
        
        for i, image_file in enumerate(images):
            try:
                # Comprimir cada imagen
                original_content = await image_file.read()
                total_original_size += len(original_content)
                
                optimized_content = await compress_image_for_pdf(image_file)
                total_optimized_size += len(optimized_content)
                
                optimized_images.append(optimized_content)
                logger.info(f"✅ Imagen {i+1} optimizada: {len(original_content)/1024:.1f}KB → {len(optimized_content)/1024:.1f}KB")
                
            except Exception as e:
                logger.error(f"❌ Error procesando imagen {image_file.filename}: {e}")
                continue
        
        if not optimized_images:
            raise Exception("No hay imágenes válidas para convertir a PDF")
        
        # Convertir a PDF
        pdf_bytes = img2pdf.convert(
            optimized_images,
            rotation=img2pdf.Rotation.ifvalid
        )
        
        compression_ratio = (total_original_size - total_optimized_size) / total_original_size * 100
        logger.info(f"✅ PDF generado: {len(pdf_bytes)/1024:.1f}KB, {len(optimized_images)} páginas")
        logger.info(f"📊 Compresión: {compression_ratio:.1f}% de reducción")
        
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imágenes a PDF: {e}")
        raise

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