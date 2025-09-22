# image_compressor.py
import io
from PIL import Image
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

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
            await file.seek(0)
            return file
        
        logger.info(f"Comprimiendo imagen {file.filename} de {len(content)/1024/1024:.2f}MB")
        
        # Abrir imagen con PIL
        image = Image.open(io.BytesIO(content))
        
        # Convertir a RGB si es necesario (para JPEG)
        if image.mode in ('RGBA', 'P'):
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
            filename=file.filename,
            file=io.BytesIO(compressed_content),
            content_type='image/jpeg'
        )
        
        return compressed_file
        
    except Exception as e:
        logger.error(f"Error comprimiendo imagen {file.filename}: {e}")
        # En caso de error, devolver el archivo original
        await file.seek(0)
        return file