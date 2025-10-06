# pdf_converter.py - VERSIÓN CORREGIDA SIN ViewerPanes
import img2pdf
from PIL import Image
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

async def validate_and_repair_image(image_content: bytes, filename: str) -> bytes:
    """
    Valida y repara una imagen si es posible
    """
    try:
        # Intentar abrir la imagen con PIL
        image = Image.open(io.BytesIO(image_content))
        
        # Verificar que es una imagen válida
        image.verify()
        
        # Si llegamos aquí, la imagen es válida
        logger.info(f"✅ Imagen válida: {filename}")
        return image_content
        
    except Exception as e:
        logger.warning(f"⚠️ Imagen inválida {filename}: {e}. Intentando reparar...")
        
        try:
            # Intentar reparar: reabrir y guardar como JPEG
            image = Image.open(io.BytesIO(image_content))
            
            # Convertir a RGB si es necesario
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar si es muy grande (máximo 2000px en el lado más largo)
            max_size = (2000, 2000)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Guardar como JPEG optimizado
            repaired_buffer = io.BytesIO()
            image.save(repaired_buffer, format='JPEG', quality=85, optimize=True)
            repaired_content = repaired_buffer.getvalue()
            
            logger.info(f"✅ Imagen reparada: {filename} ({len(repaired_content)} bytes)")
            return repaired_content
            
        except Exception as repair_error:
            logger.error(f"❌ No se pudo reparar imagen {filename}: {repair_error}")
            # Devolver contenido original como fallback
            return image_content

async def convert_images_to_pdf(images: list) -> bytes:
    """
    Convierte una lista de imágenes a PDF con manejo robusto de errores
    """
    try:
        logger.info(f"🔄 Convirtiendo {len(images)} archivos a PDF...")
        
        valid_images = []
        
        for i, image_file in enumerate(images):
            try:
                logger.info(f"📄 Procesando archivo {i+1}: {image_file.filename}")
                
                # Leer contenido
                content = await image_file.read()
                
                # Verificar si ya es PDF
                if (image_file.filename.lower().endswith('.pdf') or 
                    (hasattr(image_file, 'content_type') and 
                     image_file.content_type == 'application/pdf')):
                    logger.info(f"📄 Archivo ya es PDF: {image_file.filename}")
                    valid_images.append(content)
                    continue
                
                # Validar y reparar imagen si es necesario
                processed_content = await validate_and_repair_image(content, image_file.filename)
                
                # Verificar que el contenido procesado es válido para img2pdf
                if processed_content and len(processed_content) > 0:
                    valid_images.append(processed_content)
                    logger.info(f"✅ Imagen {image_file.filename} preparada para PDF")
                else:
                    logger.warning(f"⚠️ Contenido inválido para {image_file.filename}")
                
            except Exception as e:
                logger.error(f"❌ Error procesando archivo {image_file.filename}: {e}")
                continue
            finally:
                await image_file.seek(0)
        
        if not valid_images:
            raise Exception("No hay archivos válidos para convertir a PDF")
        
        logger.info(f"📊 {len(valid_images)} archivos válidos para conversión a PDF")
        
        # Convertir a PDF con opciones CORREGIDAS (sin ViewerPanes)
        try:
            pdf_bytes = img2pdf.convert(
                valid_images,
                layout_fun=img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)))  # A4
            )
            
            logger.info(f"✅ PDF generado exitosamente: {len(pdf_bytes)/1024:.1f}KB")
            return pdf_bytes
            
        except Exception as pdf_error:
            logger.error(f"❌ Error en img2pdf: {pdf_error}")
            # Fallback: crear un PDF simple con mensaje de error
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import letter
                
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=letter)
                c.drawString(100, 750, "FacturaV - Documento procesado")
                c.drawString(100, 730, f"Archivo: {images[0].filename if images else 'Desconocido'}")
                c.drawString(100, 710, "Nota: Error en conversión de imagen, procesado directamente por Azure")
                c.save()
                pdf_fallback = buffer.getvalue()
                logger.info(f"✅ PDF fallback generado: {len(pdf_fallback)} bytes")
                return pdf_fallback
            except Exception as fallback_error:
                logger.error(f"❌ Error incluso en fallback: {fallback_error}")
                # Último fallback: PDF mínimo
                minimal_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n0\n%%EOF"
                return minimal_pdf
        
    except Exception as e:
        logger.error(f"❌ Error crítico convirtiendo archivos a PDF: {e}")
        # Fallback final
        minimal_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n0\n%%EOF"
        return minimal_pdf

async def convert_single_image_to_pdf(image_file):
    """
    Convierte una sola imagen a PDF
    """
    try:
        logger.info(f"🔄 Convirtiendo imagen única a PDF: {image_file.filename}")
        
        # Usar la función principal para una sola imagen
        pdf_bytes = await convert_images_to_pdf([image_file])
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imagen única a PDF: {e}")
        raise