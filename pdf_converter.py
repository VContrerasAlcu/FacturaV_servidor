# src/services/pdf_converter.py
import img2pdf
from PIL import Image
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

async def convert_images_to_pdf(images: list) -> bytes:
    """
    Convierte una lista de imágenes (UploadFile) a un PDF multipágina
    """
    try:
        logger.info(f"🔄 Convirtiendo {len(images)} imágenes a PDF...")
        
        # Lista para almacenar los datos de imagen en bytes
        image_bytes_list = []
        
        for i, image_file in enumerate(images):
            try:
                # Leer el contenido de la imagen
                image_content = await image_file.read()
                
                # Verificar que es una imagen válida
                image = Image.open(io.BytesIO(image_content))
                image.verify()  # Verificar integridad
                
                # Resetear el archivo para futuras lecturas
                await image_file.seek(0)
                
                image_bytes_list.append(image_content)
                logger.info(f"✅ Imagen {i+1} preparada para conversión: {image_file.filename}")
                
            except Exception as e:
                logger.error(f"❌ Error procesando imagen {image_file.filename}: {e}")
                continue
        
        if not image_bytes_list:
            raise Exception("No hay imágenes válidas para convertir a PDF")
        
        # Convertir imágenes a PDF
        pdf_bytes = img2pdf.convert(image_bytes_list)
        logger.info(f"✅ PDF generado: {len(pdf_bytes)} bytes, {len(image_bytes_list)} páginas")
        
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imágenes a PDF: {e}")
        raise

async def convert_single_image_to_pdf(image_file: UploadFile) -> bytes:
    """
    Convierte una sola imagen a PDF
    """
    try:
        logger.info(f"🔄 Convirtiendo imagen única a PDF: {image_file.filename}")
        
        # Leer el contenido de la imagen
        image_content = await image_file.read()
        
        # Convertir a PDF
        pdf_bytes = img2pdf.convert(image_content)
        
        # Resetear el archivo
        await image_file.seek(0)
        
        logger.info(f"✅ PDF único generado: {len(pdf_bytes)} bytes")
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imagen única a PDF: {e}")
        raise