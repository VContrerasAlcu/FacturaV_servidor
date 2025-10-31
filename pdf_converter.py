# pdf_converter.py - VERSIÓN MEJORADA DE COMPRESIÓN
import img2pdf
from PIL import Image
import io
import logging
from image_compressor import compress_image_for_pdf

logger = logging.getLogger(__name__)

async def convert_images_to_pdf_optimized(images: list, max_size_per_page_kb: int = 300) -> bytes:
    """
    Convierte imágenes a PDF con compresión optimizada
    """
    try:
        logger.info(f"🔄 Convirtiendo {len(images)} imágenes a PDF optimizado")
        
        valid_images = []
        total_original_size = 0
        total_compressed_size = 0
        
        for i, image_file in enumerate(images):
            try:
                logger.info(f"📄 Procesando archivo {i+1}: {image_file.filename}")
                
                # Leer contenido original
                original_content = await image_file.read()
                original_size_kb = len(original_content) / 1024
                total_original_size += original_size_kb
                
                # ✅ COMPRIMIR IMAGEN ANTES DE PDF
                await image_file.seek(0)  # Resetear para compresión
                compressed_file = await compress_image_for_pdf(image_file, max_size_per_page_kb)
                
                compressed_content = await compressed_file.read()
                compressed_size_kb = len(compressed_content) / 1024
                total_compressed_size += compressed_size_kb
                
                if compressed_content and len(compressed_content) > 0:
                    valid_images.append(compressed_content)
                    logger.info(f"✅ Imagen {i+1} lista: {compressed_size_kb:.1f}KB (reducción: {(original_size_kb - compressed_size_kb)/original_size_kb*100:.1f}%)")
                else:
                    logger.warning(f"⚠️ Contenido inválido para {image_file.filename}")
                
            except Exception as e:
                logger.error(f"❌ Error procesando archivo {image_file.filename}: {e}")
                continue
            finally:
                await image_file.seek(0)
        
        if not valid_images:
            raise Exception("No hay archivos válidos para convertir a PDF")
        
        logger.info(f"📊 Resumen compresión: {total_original_size:.1f}KB -> {total_compressed_size:.1f}KB (reducción: {(total_original_size - total_compressed_size)/total_original_size*100:.1f}%)")
        
        # ✅ CONVERTIR A PDF CON OPCIONES OPTIMIZADAS
        try:
            # Opciones de compresión para img2pdf
            pdf_bytes = img2pdf.convert(
                valid_images,
                rotation=0,
                layout_fun=img2pdf.get_fixed_dpi_layout_fun(150)  # ✅ REDUCIR DPI
            )
            
            pdf_size_kb = len(pdf_bytes) / 1024
            logger.info(f"✅ PDF generado: {pdf_size_kb:.1f}KB con {len(valid_images)} páginas")
            
            return pdf_bytes
            
        except Exception as pdf_error:
            logger.warning(f"⚠️ Error con img2pdf: {pdf_error}. Usando método alternativo...")
            return await create_lightweight_pdf_fallback(valid_images)
        
    except Exception as e:
        logger.error(f"❌ Error crítico convirtiendo a PDF: {e}")
        # Fallback mínimo
        return create_minimal_pdf()

async def create_lightweight_pdf_fallback(images_content: list) -> bytes:
    """
    Fallback para crear PDF liviano cuando img2pdf falla
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        
        for i, img_content in enumerate(images_content):
            if i > 0:
                c.showPage()
            
            try:
                img_reader = ImageReader(io.BytesIO(img_content))
                img_width, img_height = img_reader.getSize()
                
                # Escalar para que quepa en A4 manteniendo proporciones
                page_width, page_height = A4
                margin = 40  # Margen reducido
                available_width = page_width - (2 * margin)
                available_height = page_height - (2 * margin)
                
                scale_x = available_width / img_width
                scale_y = available_height / img_height
                scale = min(scale_x, scale_y, 1.0)
                
                new_width = img_width * scale
                new_height = img_height * scale
                
                # Centrar en página
                x = (page_width - new_width) / 2
                y = (page_height - new_height) / 2
                
                c.drawImage(img_reader, x, y, new_width, new_height)
                
            except Exception as img_error:
                logger.error(f"❌ Error procesando imagen {i+1} en fallback: {img_error}")
                c.drawString(50, page_height - 50, f"Error procesando imagen {i+1}")
        
        c.save()
        pdf_fallback = buffer.getvalue()
        
        logger.info(f"✅ PDF fallback generado: {len(pdf_fallback)/1024:.1f}KB")
        return pdf_fallback
        
    except Exception as e:
        logger.error(f"❌ Error incluso en fallback: {e}")
        return create_minimal_pdf()

def create_minimal_pdf() -> bytes:
    """Crea PDF mínimo como último recurso"""
    minimal_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n0\n%%EOF"
    return minimal_pdf

async def convert_single_image_to_pdf_optimized(image_file, max_size_kb: int = 300):
    """
    Convierte una sola imagen a PDF optimizado
    """
    try:
        logger.info(f"🔄 Convirtiendo imagen única a PDF optimizado: {image_file.filename}")
        
        pdf_bytes = await convert_images_to_pdf_optimized([image_file], max_size_kb)
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error convirtiendo imagen única a PDF: {e}")
        raise