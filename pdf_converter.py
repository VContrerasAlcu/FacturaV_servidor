# pdf_converter.py - VERSIÓN ROBUSTA CON MANEJO DE ERRORES MEJORADO
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
            
            # Guardar como JPEG optimizado
            repaired_buffer = io.BytesIO()
            image.save(repaired_buffer, format='JPEG', quality=85, optimize=True)
            repaired_content = repaired_buffer.getvalue()
            
            logger.info(f"✅ Imagen reparada: {filename}")
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
        
        # Convertir a PDF con opciones específicas
        try:
            pdf_bytes = img2pdf.convert(
                valid_images,
                layout_fun=img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))),  # A4
                viewer_panes=img2pdf.ViewerPanes.NONE
            )
            
            logger.info(f"✅ PDF generado exitosamente: {len(pdf_bytes)/1024:.1f}KB")
            return pdf_bytes
            
        except Exception as pdf_error:
            logger.error(f"❌ Error en img2pdf: {pdf_error}")
            # Fallback: crear un PDF simple con mensaje de error
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            c.drawString(100, 750, "Error generando PDF desde imágenes")
            c.drawString(100, 730, f"Detalle: {str(pdf_error)}")
            c.save()
            return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error crítico convirtiendo archivos a PDF: {e}")
        raise

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