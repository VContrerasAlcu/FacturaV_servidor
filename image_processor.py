# image_processor.py
import os
import logging
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from config import settings

logger = logging.getLogger(__name__)

# Configurar cliente de Azure Document Intelligence
credential = AzureKeyCredential(settings.AZURE_DOCUMENT_INTELLIGENCE_KEY)
document_analysis_client = DocumentAnalysisClient(
    endpoint=settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT, 
    credential=credential
)

def process_image(upload_files):
    """
    Procesa una o múltiples imágenes usando Azure Document Intelligence
    """
    try:
        # Si es una lista de archivos (multipágina)
        if isinstance(upload_files, list):
            logger.info(f"📄 Procesando documento multipágina con {len(upload_files)} páginas")
            return process_multipage_document(upload_files)
        else:
            # Procesamiento de archivo individual
            logger.info(f"📄 Procesando documento individual: {upload_files.filename}")
            return process_single_document(upload_files)
            
    except Exception as e:
        logger.error(f"❌ Error procesando documento: {e}")
        return []

def process_single_document(upload_file):
    """
    Procesa un solo documento
    """
    try:
        # Leer el contenido del archivo
        file_content = upload_file.file.read()
        
        if not file_content:
            logger.error("❌ Archivo vacío")
            return []
        
        logger.info(f"📊 Analizando documento individual: {len(file_content)} bytes")
        
        # Analizar el documento con Azure Document Intelligence
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice",  # Modelo para facturas
            document=file_content
        )
        
        result = poller.result()
        
        processed_data = []
        for idx, document in enumerate(result.documents):
            doc_data = extract_document_data(document, upload_file.filename)
            if doc_data:
                processed_data.append(doc_data)
                logger.info(f"✅ Documento {idx + 1} procesado exitosamente")
        
        logger.info(f"📈 Total de documentos extraídos: {len(processed_data)}")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando documento individual: {e}")
        return []

def process_multipage_document(upload_files):
    """
    Procesa múltiples archivos como un documento multipágina
    """
    try:
        # Leer todos los archivos y combinarlos
        document_pages = []
        
        for upload_file in upload_files:
            file_content = upload_file.file.read()
            if file_content:
                document_pages.append(file_content)
                # Resetear el archivo para lectura posterior
                upload_file.file.seek(0)
        
        if not document_pages:
            logger.error("❌ No hay contenido en los archivos multipágina")
            return []
        
        logger.info(f"📊 Analizando documento multipágina con {len(document_pages)} páginas")
        
        # Para documentos multipágina, necesitamos usar un enfoque diferente
        # Azure DI puede procesar PDFs multipágina, pero para imágenes separadas
        # necesitamos combinarlas o procesarlas individualmente
        
        # 🆕 ENFOQUE CORREGIDO: Procesar cada página individualmente pero mantener la relación
        all_processed_data = []
        
        for i, page_content in enumerate(document_pages):
            try:
                logger.info(f"🔍 Procesando página {i + 1} de {len(document_pages)}")
                
                poller = document_analysis_client.begin_analyze_document(
                    "prebuilt-invoice",
                    document=page_content
                )
                
                result = poller.result()
                
                for idx, document in enumerate(result.documents):
                    doc_data = extract_document_data(document, f"page_{i + 1}")
                    if doc_data:
                        doc_data['pagina_numero'] = i + 1
                        doc_data['total_paginas'] = len(document_pages)
                        all_processed_data.append(doc_data)
                        logger.info(f"✅ Página {i + 1} - Documento {idx + 1} procesado")
                        
            except Exception as page_error:
                logger.error(f"❌ Error procesando página {i + 1}: {page_error}")
                continue
        
        logger.info(f"📈 Total de documentos extraídos de {len(document_pages)} páginas: {len(all_processed_data)}")
        return all_processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando documento multipágina: {e}")
        return []

def extract_document_data(document, filename):
    """
    Extrae los datos relevantes de un documento analizado
    """
    try:
        doc_data = {
            'archivo_origen': filename,
            'proveedor': '',
            'fecha': '',
            'numero_factura': '',
            'base_imponible': 0,
            'iva': 0,
            'total': 0,
            'confianza': document.confidence if hasattr(document, 'confidence') else 0.0
        }
        
        # Extraer campos de la factura
        fields = document.fields
        
        # Proveedor/Vendedor
        if 'VendorName' in fields and fields['VendorName']:
            doc_data['proveedor'] = fields['VendorName'].value
        elif 'CustomerName' in fields and fields['CustomerName']:
            doc_data['proveedor'] = fields['CustomerName'].value
        
        # Fecha
        if 'InvoiceDate' in fields and fields['InvoiceDate']:
            doc_data['fecha'] = fields['InvoiceDate'].value.strftime('%Y-%m-%d') if hasattr(fields['InvoiceDate'].value, 'strftime') else str(fields['InvoiceDate'].value)
        
        # Número de factura
        if 'InvoiceId' in fields and fields['InvoiceId']:
            doc_data['numero_factura'] = fields['InvoiceId'].value
        
        # Total
        if 'InvoiceTotal' in fields and fields['InvoiceTotal']:
            doc_data['total'] = float(fields['InvoiceTotal'].value) if fields['InvoiceTotal'].value else 0.0
        
        # Campos de impuestos (IVA)
        if 'TaxDetails' in fields and fields['TaxDetails']:
            tax_items = fields['TaxDetails'].value
            if tax_items and len(tax_items) > 0:
                doc_data['iva'] = float(tax_items[0].value) if tax_items[0].value else 0.0
        
        # Calcular base imponible si no está disponible
        if doc_data['total'] > 0 and doc_data['iva'] > 0:
            doc_data['base_imponible'] = doc_data['total'] - doc_data['iva']
        elif doc_data['total'] > 0:
            doc_data['base_imponible'] = doc_data['total']
        
        # Si no se pudo extraer información básica, considerar el documento como inválido
        if not doc_data['proveedor'] and not doc_data['numero_factura'] and doc_data['total'] == 0:
            logger.warning(f"⚠️ Documento sin datos extraíbles: {filename}")
            return None
            
        logger.info(f"📋 Datos extraídos - Proveedor: {doc_data['proveedor']}, Total: {doc_data['total']}")
        return doc_data
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo datos del documento: {e}")
        return None