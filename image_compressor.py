# image_compressor.py - VERSIÓN MEJORADA
import io
from PIL import Image, ImageFilter
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

async def compress_image_for_pdf(file: UploadFile, target_size_kb: int = 500) -> UploadFile:
    """
    Comprime imágenes optimizadas para PDF - VERSIÓN MEJORADA
    """
    try:
        # Leer el contenido del archivo
        content = await file.read()
        original_size_kb = len(content) / 1024
        
        # Si ya es pequeño, no comprimir
        if original_size_kb <= target_size_kb:
            logger.info(f"✅ Imagen ya optimizada: {file.filename} ({original_size_kb:.1f}KB)")
            await file.seek(0)
            return file
        
        logger.info(f"🔄 Comprimiendo {file.filename} de {original_size_kb:.1f}KB a ~{target_size_kb}KB")
        
        # Abrir imagen con PIL
        image = Image.open(io.BytesIO(content))
        
        # ✅ CONVERTIR A RGB (importante para JPEG)
        if image.mode in ('RGBA', 'P', 'LA'):
            image = image.convert('RGB')
        
        # ✅ CALCULAR NUEVO TAMAÑO MÁXIMO
        max_dimension = 1600  # Reducir dimensión máxima
        if max(image.size) > max_dimension:
            ratio = max_dimension / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"   📐 Redimensionada: {image.size} -> {new_size}")
        
        # ✅ COMPRESIÓN INTELIGENTE
        # Calcular calidad basada en el tamaño objetivo
        original_size_mb = original_size_kb / 1024
        target_size_mb = target_size_kb / 1024
        
        # Calcular calidad inicial (más agresiva)
        initial_quality = max(30, int(70 * (target_size_mb / original_size_mb)))
        
        # Probar diferentes niveles de compresión
        qualities_to_try = [initial_quality, initial_quality - 10, initial_quality - 20]
        qualities_to_try = [q for q in qualities_to_try if q >= 20]  # Mínimo 20% de calidad
        
        compressed_content = None
        final_quality = initial_quality
        
        for quality in qualities_to_try:
            output = io.BytesIO()
            image.save(
                output, 
                format='JPEG', 
                quality=quality,
                optimize=True,
                progressive=True  # ✅ MEJOR COMPRESIÓN
            )
            
            temp_content = output.getvalue()
            temp_size_kb = len(temp_content) / 1024
            
            logger.info(f"   🧪 Probando calidad {quality}% -> {temp_size_kb:.1f}KB")
            
            if temp_size_kb <= target_size_kb * 1.2:  # Permitir 20% más del objetivo
                compressed_content = temp_content
                final_quality = quality
                break
        
        # Si ninguna calidad alcanzó el objetivo, usar la más pequeña
        if compressed_content is None:
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=20, optimize=True)
            compressed_content = output.getvalue()
            final_quality = 20
        
        compressed_size_kb = len(compressed_content) / 1024
        compression_ratio = (original_size_kb - compressed_size_kb) / original_size_kb * 100
        
        logger.info(f"✅ Imagen comprimida: {compressed_size_kb:.1f}KB (calidad: {final_quality}%, reducción: {compression_ratio:.1f}%)")
        
        # Crear nuevo UploadFile
        compressed_file = UploadFile(
            filename=f"compressed_{file.filename}",
            file=io.BytesIO(compressed_content),
            content_type='image/jpeg'
        )
        
        return compressed_file
        
    except Exception as e:
        logger.error(f"❌ Error comprimiendo imagen {file.filename}: {e}")
        # En caso de error, devolver el archivo original
        await file.seek(0)
        return file

async def optimize_image_for_ocr(file: UploadFile) -> UploadFile:
    """
    Optimiza imagen específicamente para OCR (mejor legibilidad)
    """
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content))
        
        # Convertir a escala de grises para OCR (mejor rendimiento)
        if image.mode != 'L':
            image = image.convert('L')
        
        # Mejorar contraste suavemente
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.2)  # Aumentar contraste 20%
        
        # Reducir ruido
        image = image.filter(ImageFilter.SMOOTH)
        
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85, optimize=True)
        
        optimized_file = UploadFile(
            filename=f"ocr_optimized_{file.filename}",
            file=io.BytesIO(output.getvalue()),
            content_type='image/jpeg'
        )
        
        logger.info(f"✅ Imagen optimizada para OCR: {file.filename}")
        return optimized_file
        
    except Exception as e:
        logger.error(f"Error optimizando para OCR: {e}")
        await file.seek(0)
        return file