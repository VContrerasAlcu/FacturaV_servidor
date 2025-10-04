# pdf_optimizer.py
import img2pdf
from PIL import Image, ImageOps
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

class CompressionManager:
    @staticmethod
    def get_compression_settings(file_type: str, original_size: int):
        """
        Devuelve configuración de compresión según tipo y tamaño
        """
        base_settings = {
            'max_dpi': 150,
            'quality': 60,
            'max_width': 800
        }
        
        if original_size > 2 * 1024 * 1024:  # > 2MB
            return {
                'max_dpi': 120,
                'quality': 50,
                'max_width': 600
            }
        elif original_size > 1 * 1024 * 1024:  # > 1MB
            return {
                'max_dpi': 130,
                'quality': 55,
                'max_width': 700
            }
        else:
            return base_settings

class PDFOptimizer:
    def __init__(self):
        # Configuración por defecto
        self.settings = {
            'max_dpi': 150,
            'quality': 60,
            'max_width': 800
        }
    
    async def optimize_image_for_pdf(self, image_file: UploadFile) -> bytes:
        """
        Optimiza imagen para PDF con compresión inteligente
        """
        try:
            # Leer imagen original
            image_content = await image_file.read()
            original_size = len(image_content)
            
            # Obtener configuración de compresión inteligente
            compression_settings = CompressionManager.get_compression_settings(
                image_file.content_type, 
                original_size
            )
            
            image = Image.open(io.BytesIO(image_content))
            
            # Convertir a RGB si es necesario
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar según configuración
            if image.size[0] > compression_settings['max_width']:
                ratio = compression_settings['max_width'] / image.size[0]
                new_height = int(image.size[1] * ratio)
                image = image.resize(
                    (compression_settings['max_width'], new_height), 
                    Image.Resampling.LANCZOS
                )
            
            # Comprimir con configuración inteligente
            optimized_buffer = io.BytesIO()
            image.save(
                optimized_buffer,
                format='JPEG',
                quality=compression_settings['quality'],
                optimize=True,
                progressive=True,
                dpi=(compression_settings['max_dpi'], compression_settings['max_dpi'])
            )
            
            await image_file.seek(0)
            optimized_size = len(optimized_buffer.getvalue())
            
            logger.info(f"📊 Compresión inteligente: {original_size/1024:.1f}KB → {optimized_size/1024:.1f}KB")
            logger.info(f"⚙️ Configuración: DPI{compression_settings['max_dpi']}, Calidad{compression_settings['quality']}%")
            
            return optimized_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"❌ Error optimizando imagen: {e}")
            await image_file.seek(0)
            return await image_file.read()
    
    async def create_optimized_pdf(self, images: list) -> bytes:
        """
        Crea PDF altamente optimizado con compresión inteligente
        """
        try:
            logger.info(f"🔄 Creando PDF optimizado para {len(images)} imágenes...")
            
            optimized_images = []
            total_original = 0
            total_optimized = 0
            
            for i, image_file in enumerate(images):
                original_content = await image_file.read()
                total_original += len(original_content)
                
                optimized_content = await self.optimize_image_for_pdf(image_file)
                total_optimized += len(optimized_content)
                
                optimized_images.append(optimized_content)
                
                logger.info(f"✅ Imagen {i+1} optimizada: "
                           f"{len(original_content)/1024:.1f}KB → {len(optimized_content)/1024:.1f}KB")
                
                await image_file.seek(0)
            
            # Generar PDF optimizado
            pdf_bytes = img2pdf.convert(
                optimized_images,
                layout_fun=img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))),
                viewer_panes=img2pdf.ViewerPanes.NONE,
                fit=img2pdf.Fit.into
            )
            
            final_size_kb = len(pdf_bytes) / 1024
            total_original_kb = total_original / 1024
            compression_ratio = (total_original - len(pdf_bytes)) / total_original * 100
            
            logger.info(f"✅ PDF optimizado creado: {final_size_kb:.1f}KB")
            logger.info(f"📊 Resumen compresión: {total_original_kb:.1f}KB → {final_size_kb:.1f}KB")
            logger.info(f"📈 Reducción: {compression_ratio:.1f}%")
            
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"❌ Error creando PDF optimizado: {e}")
            raise

    async def optimize_existing_pdf(self, pdf_bytes: bytes) -> bytes:
        """
        Optimiza un PDF existente (placeholder para futura implementación)
        """
        try:
            logger.info(f"📄 Optimizando PDF existente: {len(pdf_bytes)/1024:.1f}KB")
            
            # Aquí podrías integrar PyPDF2 para compresión avanzada
            # Por ahora retornamos el mismo PDF
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"❌ Error optimizando PDF: {e}")
            return pdf_bytes