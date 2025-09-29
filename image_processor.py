# image_processor.py
import os
import logging
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from config import settings

logger = logging.getLogger(__name__)

# 🆕 CORRECCIÓN: Usar las propiedades de tu config actual
def get_azure_client():
    """
    Configura y retorna el cliente de Azure Document Intelligence
    """
    try:
        # 🆕 Usar las propiedades con fallback de tu config
        endpoint = settings.document_intelligence_endpoint
        key = settings.document_intelligence_key
        
        if not endpoint or not key:
            logger.error("❌ Faltan credenciales de Azure Document Intelligence")
            raise ValueError("Azure Document Intelligence credentials not configured")
        
        # 🆕 Asegurar que el endpoint tenga el formato correcto
        if not endpoint.startswith('https://'):
            endpoint = f'https://{endpoint}'
        
        # 🆕 Asegurar que no termine con /
        endpoint = endpoint.rstrip('/')
        
        logger.info(f"🔧 Configurando Azure DI con endpoint: {endpoint[:50]}...")  # Log parcial por seguridad
        
        credential = AzureKeyCredential(key)
        client = DocumentAnalysisClient(
            endpoint=endpoint, 
            credential=credential
        )
        
        # 🆕 Test de conexión básico
        logger.info("✅ Cliente Azure Document Intelligence configurado correctamente")
        return client
        
    except Exception as e:
        logger.error(f"❌ Error configurando cliente Azure: {e}")
        raise

# 🆕 Obtener cliente una sola vez
try:
    document_analysis_client = get_azure_client()
    logger.info("✅ Azure Document Intelligence inicializado correctamente")
except Exception as e:
    logger.error(f"❌ Error inicializando Azure Document Intelligence: {e}")
    document_analysis_client = None

def process_image(upload_files):
    """
    Procesa una o múltiples imágenes usando Azure Document Intelligence
    """
    try:
        # Verificar que el cliente esté disponible
        if document_analysis_client is None:
            logger.error("❌ Cliente Azure no disponible")
            return []
        
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
        
        logger.info(f"📊 Analizando documento individual: {len(file_content)} bytes - {upload_file.filename}")
        
        # Usar el cliente global
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice",  # Modelo para facturas
            document=file_content
        )
        
        result = poller.result()
        
        logger.info(f"📄 Resultado de Azure para {upload_file.filename}:")
        logger.info(f"   📑 Número de documentos: {len(result.documents)}")
        logger.info(f"   🔍 Páginas analizadas: {len(result.pages)}")
        
        processed_data = []
        for idx, document in enumerate(result.documents):
            logger.info(f"   📋 Procesando documento {idx + 1}:")
            logger.info(f"      🏷️  Tipo: {document.doc_type}")
            logger.info(f"      ✅ Confianza: {document.confidence}")
            
            doc_data = extract_document_data(document, upload_file.filename)
            if doc_data:
                processed_data.append(doc_data)
                logger.info(f"   ✅ Documento {idx + 1} procesado exitosamente")
            else:
                logger.warning(f"   ⚠️ Documento {idx + 1} no pudo ser procesado")
        
        logger.info(f"📈 Total de documentos extraídos de {upload_file.filename}: {len(processed_data)}")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando documento individual {upload_file.filename}: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return []

def process_multipage_document(upload_files):
    """
    Procesa múltiples archivos como un documento multipágina
    """
    try:
        # 🆕 ENFOQUE CORREGIDO: Procesar cada página individualmente
        all_processed_data = []
        
        for i, upload_file in enumerate(upload_files):
            try:
                logger.info(f"🔍 Procesando página {i + 1} de {len(upload_files)}: {upload_file.filename}")
                
                # Leer contenido del archivo
                file_content = upload_file.file.read()
                
                if not file_content:
                    logger.warning(f"⚠️ Página {i + 1} vacía, saltando...")
                    continue
                
                # 🆕 Usar el cliente global
                poller = document_analysis_client.begin_analyze_document(
                    "prebuilt-invoice",
                    document=file_content
                )
                
                result = poller.result()
                
                for idx, document in enumerate(result.documents):
                    doc_data = extract_document_data(document, upload_file.filename)
                    if doc_data:
                        doc_data['pagina_numero'] = i + 1
                        doc_data['total_paginas'] = len(upload_files)
                        doc_data['es_multipagina'] = len(upload_files) > 1
                        all_processed_data.append(doc_data)
                        logger.info(f"✅ Página {i + 1} - Documento {idx + 1} procesado")
                        
                # 🆕 Resetear el archivo para posible reuso
                upload_file.file.seek(0)
                        
            except Exception as page_error:
                logger.error(f"❌ Error procesando página {i + 1}: {page_error}")
                continue
        
        logger.info(f"📈 Total de documentos extraídos de {len(upload_files)} páginas: {len(all_processed_data)}")
        return all_processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando documento multipágina: {e}")
        return []

# image_processor.py - FUNCIÓN extract_document_data CORREGIDA
def extract_document_data(document, filename):
    """
    Extrae los datos relevantes de un documento analizado - VERSIÓN CORREGIDA
    """
    try:
        doc_data = {
            'archivo_origen': filename,
            'proveedor': '',
            'fecha': '',
            'numero_factura': '',
            'base_imponible': 0.0,
            'iva': 0.0,
            'total': 0.0,
            'confianza': document.confidence if hasattr(document, 'confidence') else 0.0
        }
        
        # Extraer campos de la factura
        fields = document.fields
        
        logger.info(f"🔍 Campos detectados en {filename}: {list(fields.keys())}")
        
        # Proveedor/Vendedor - CORREGIDO
        if 'VendorName' in fields and fields['VendorName'] and fields['VendorName'].value:
            doc_data['proveedor'] = fields['VendorName'].value
            logger.info(f"🏢 Proveedor detectado: {doc_data['proveedor']}")
        elif 'CustomerName' in fields and fields['CustomerName'] and fields['CustomerName'].value:
            doc_data['proveedor'] = fields['CustomerName'].value
            logger.info(f"🏢 Cliente detectado: {doc_data['proveedor']}")
        
        # Fecha - CORREGIDO
        if 'InvoiceDate' in fields and fields['InvoiceDate'] and fields['InvoiceDate'].value:
            try:
                if hasattr(fields['InvoiceDate'].value, 'strftime'):
                    doc_data['fecha'] = fields['InvoiceDate'].value.strftime('%Y-%m-%d')
                else:
                    doc_data['fecha'] = str(fields['InvoiceDate'].value)
                logger.info(f"📅 Fecha detectada: {doc_data['fecha']}")
            except Exception as date_error:
                logger.warning(f"⚠️ Error procesando fecha: {date_error}")
        
        # Número de factura - CORREGIDO
        if 'InvoiceId' in fields and fields['InvoiceId'] and fields['InvoiceId'].value:
            doc_data['numero_factura'] = str(fields['InvoiceId'].value)
            logger.info(f"🔢 Número factura: {doc_data['numero_factura']}")
        
        # 🆕 CORRECCIÓN CRÍTICA: Extraer TOTAL correctamente
        if 'InvoiceTotal' in fields and fields['InvoiceTotal'] and fields['InvoiceTotal'].value:
            try:
                total_value = fields['InvoiceTotal'].value
                logger.info(f"💰 InvoiceTotal raw: {total_value} (type: {type(total_value)})")
                
                # Manejar CurrencyValue object
                if hasattr(total_value, 'amount'):
                    doc_data['total'] = float(total_value.amount)
                    logger.info(f"💰 Total extraído (CurrencyValue): {doc_data['total']}")
                else:
                    # Intentar convertir directamente
                    doc_data['total'] = float(total_value)
                    logger.info(f"💰 Total extraído (directo): {doc_data['total']}")
                    
            except Exception as total_error:
                logger.error(f"❌ Error extrayendo total: {total_error}")
                doc_data['total'] = 0.0
        
        # 🆕 CORRECCIÓN: Extraer IVA correctamente
        iva_detectado = 0.0
        if 'TaxDetails' in fields and fields['TaxDetails'] and fields['TaxDetails'].value:
            try:
                tax_items = fields['TaxDetails'].value
                if tax_items and len(tax_items) > 0:
                    tax_value = tax_items[0].value
                    logger.info(f"🧾 TaxDetails raw: {tax_value} (type: {type(tax_value)})")
                    
                    if hasattr(tax_value, 'amount'):
                        iva_detectado = float(tax_value.amount)
                    else:
                        iva_detectado = float(tax_value) if tax_value else 0.0
                        
                    doc_data['iva'] = iva_detectado
                    logger.info(f"🧾 IVA detectado: {doc_data['iva']}")
            except Exception as iva_error:
                logger.error(f"❌ Error extrayendo IVA: {iva_error}")
        
        # 🆕 CORRECCIÓN: Calcular base imponible
        if doc_data['total'] > 0:
            if iva_detectado > 0:
                doc_data['base_imponible'] = doc_data['total'] - iva_detectado
            else:
                doc_data['base_imponible'] = doc_data['total']
            
            logger.info(f"📊 Base imponible calculada: {doc_data['base_imponible']}")
        
        # 🆕 CORRECCIÓN: Intentar extraer campos adicionales si el total es 0
        if doc_data['total'] == 0:
            logger.warning(f"⚠️ Total es 0, buscando campos alternativos...")
            
            # Intentar con campos alternativos para el total
            alternative_total_fields = ['Total', 'AmountDue', 'SubTotal', 'TotalTax']
            for field_name in alternative_total_fields:
                if field_name in fields and fields[field_name] and fields[field_name].value:
                    try:
                        alt_value = fields[field_name].value
                        if hasattr(alt_value, 'amount'):
                            doc_data['total'] = float(alt_value.amount)
                        else:
                            doc_data['total'] = float(alt_value)
                        logger.info(f"💰 Total alternativo ({field_name}): {doc_data['total']}")
                        break
                    except Exception as alt_error:
                        logger.warning(f"⚠️ Error con campo alternativo {field_name}: {alt_error}")
                        continue
        
        # 🆕 CORRECCIÓN: Verificar si tenemos datos mínimos
        has_minimal_data = (
            doc_data['proveedor'] or 
            doc_data['numero_factura'] or 
            doc_data['total'] > 0 or
            doc_data['fecha']
        )
        
        if not has_minimal_data:
            logger.warning(f"⚠️ Documento sin datos extraíbles mínimos: {filename}")
            logger.warning(f"   Proveedor: '{doc_data['proveedor']}'")
            logger.warning(f"   Número: '{doc_data['numero_factura']}'")
            logger.warning(f"   Total: {doc_data['total']}")
            logger.warning(f"   Fecha: '{doc_data['fecha']}'")
            return None
        
        logger.info(f"✅ Datos extraídos exitosamente:")
        logger.info(f"   🏢 Proveedor: {doc_data['proveedor']}")
        logger.info(f"   🔢 Número: {doc_data['numero_factura']}")
        logger.info(f"   📅 Fecha: {doc_data['fecha']}")
        logger.info(f"   💰 Total: {doc_data['total']}")
        logger.info(f"   🧾 IVA: {doc_data['iva']}")
        logger.info(f"   📊 Base: {doc_data['base_imponible']}")
        
        return doc_data
        
    except Exception as e:
        logger.error(f"❌ Error crítico extrayendo datos del documento {filename}: {e}")
        logger.error(f"   Tipo de error: {type(e).__name__}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return None