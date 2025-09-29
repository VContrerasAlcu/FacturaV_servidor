from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
import io
import logging
from typing import List, Dict, Any

# Configurar logging
logger = logging.getLogger(__name__)

def get_azure_client():
    """Obtener cliente de Azure Document Intelligence"""
    try:
        endpoint = settings.document_intelligence_endpoint
        api_key = settings.document_intelligence_key
        
        if not endpoint or not api_key:
            logger.error("❌ Configuración de Azure Document Intelligence no encontrada")
            return None
        
        credential = AzureKeyCredential(api_key)
        document_analysis_client = DocumentAnalysisClient(endpoint, credential)
        return document_analysis_client
    except Exception as e:
        logger.error(f"❌ Error creando cliente de Azure: {e}")
        return None

def extract_invoice_data(document):
    """Extraer datos de la factura del documento analizado"""
    try:
        invoice_data = {
            'VendorName': None,
            'VendorTaxId': None,
            'VendorAddress': None,
            'CustomerName': None,
            'CustomerTaxId': None,
            'CustomerAddress': None,
            'InvoiceId': None,
            'InvoiceDate': None,
            'InvoiceTotal': 0.0,
            'Items': [],
            'TaxDetails': [],
            'SubTotal': 0.0,
            'TotalTax': 0.0
        }
        
        # Extraer campos básicos
        if document.fields.get("VendorName"):
            invoice_data['VendorName'] = get_field_value(document.fields.get("VendorName"))
        
        if document.fields.get("VendorTaxId"):
            invoice_data['VendorTaxId'] = get_field_value(document.fields.get("VendorTaxId"))
        
        if document.fields.get("VendorAddress"):
            invoice_data['VendorAddress'] = get_field_value(document.fields.get("VendorAddress"))
        
        if document.fields.get("CustomerName"):
            invoice_data['CustomerName'] = get_field_value(document.fields.get("CustomerName"))
        
        if document.fields.get("CustomerTaxId"):
            invoice_data['CustomerTaxId'] = get_field_value(document.fields.get("CustomerTaxId"))
        
        if document.fields.get("CustomerAddress"):
            invoice_data['CustomerAddress'] = get_field_value(document.fields.get("CustomerAddress"))
        
        if document.fields.get("InvoiceId"):
            invoice_data['InvoiceId'] = get_field_value(document.fields.get("InvoiceId"))
        
        if document.fields.get("InvoiceDate"):
            invoice_data['InvoiceDate'] = get_field_value(document.fields.get("InvoiceDate"))
        
        if document.fields.get("InvoiceTotal"):
            invoice_data['InvoiceTotal'] = get_field_value(document.fields.get("InvoiceTotal"))
        
        if document.fields.get("SubTotal"):
            invoice_data['SubTotal'] = get_field_value(document.fields.get("SubTotal"))
        
        if document.fields.get("TotalTax"):
            invoice_data['TotalTax'] = get_field_value(document.fields.get("TotalTax"))
        
        # Extraer items
        if document.fields.get("Items"):
            items = document.fields.get("Items").value
            for item in items:
                item_data = {
                    'Description': get_field_value(item.value.get("Description")),
                    'Quantity': get_field_value(item.value.get("Quantity")),
                    'UnitPrice': get_field_value(item.value.get("UnitPrice")),
                    'Amount': get_field_value(item.value.get("Amount"))
                }
                invoice_data['Items'].append(item_data)
        
        # Procesar impuestos
        tax_details = document.fields.get("TaxDetails")
        if tax_details and tax_details.value:
            for tax in tax_details.value:
                tax_data = {
                    'Rate': get_tax_rate_value(tax.value.get("Rate")),
                    'Amount': get_field_value(tax.value.get("Amount"))
                }
                invoice_data['TaxDetails'].append(tax_data)
        
        return invoice_data
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo datos de factura: {e}")
        return {}

def get_field_value(field):
    """Extraer valor de un campo de Azure Form Recognizer de manera segura"""
    if not field:
        return None
    
    try:
        value = field.value
        if value is None:
            return None
        
        # Manejar tipos especiales
        if hasattr(value, 'strftime'):  # Fechas
            return value.strftime('%Y-%m-%d')
        
        elif hasattr(value, 'street_address'):  # Direcciones
            address = value
            if address.street_address:
                return address.street_address
            
            # Construir dirección manualmente
            address_parts = []
            if address.house_number:
                address_parts.append(str(address.house_number))
            if address.road:
                address_parts.append(address.road)
            if address.city:
                address_parts.append(address.city)
            if address.postal_code:
                address_parts.append(str(address.postal_code))
            
            return ", ".join(address_parts) if address_parts else None
        
        # Para currency values
        elif hasattr(value, 'amount'):
            return value.amount
        
        # Para otros tipos, devolver el valor directamente
        return value
        
    except Exception as e:
        logger.warning(f"Error procesando campo: {e}")
        try:
            return str(field.value) if field.value else None
        except:
            return None

def get_tax_rate_value(rate_field):
    """Función específica para manejar tasas de impuestos"""
    if not rate_field or not rate_field.value:
        return None
    
    rate_value = rate_field.value
    
    try:
        # Si el valor es un string que ya contiene %, limpiarlo
        if isinstance(rate_value, str):
            cleaned_rate = rate_value.replace('%', '').strip()
            try:
                rate_num = float(cleaned_rate)
                return f"{rate_num}%"
            except ValueError:
                return rate_value
        
        # Si es un número, formatearlo con %
        elif isinstance(rate_value, (int, float)):
            return f"{rate_value}%"
        
        # Para otros tipos
        else:
            rate_str = str(rate_value).replace('%', '').strip()
            try:
                rate_num = float(rate_str)
                return f"{rate_num}%"
            except ValueError:
                return rate_str
    
    except Exception as e:
        logger.warning(f"Error procesando tasa de impuesto: {e}")
        return str(rate_value) if rate_value else None

def process_image_multipagina(archivos_paginas: List) -> List[Dict[str, Any]]:
    """
    Procesa múltiples páginas como un solo documento usando Azure Document Intelligence
    """
    try:
        document_analysis_client = get_azure_client()
        if not document_analysis_client:
            logger.error("❌ No se pudo inicializar el cliente de Azure")
            return []
        
        # Leer todas las páginas y convertirlas a bytes
        documentos_bytes = []
        for pagina in archivos_paginas:
            if hasattr(pagina, 'file'):
                contenido = pagina.file.read()
                documentos_bytes.append(contenido)
                pagina.file.seek(0)  # Resetear para posibles re-lecturas
            else:
                documentos_bytes.append(pagina)
        
        logger.info(f"📄 Procesando documento multipágina con {len(documentos_bytes)} páginas")
        
        # Procesar como documento multipágina
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            documents=documentos_bytes
        )
        result = poller.result()
        
        processed_data = []
        
        for idx, document in enumerate(result.documents):
            doc_data = extract_invoice_data(document)
            doc_data['numero_paginas'] = len(documentos_bytes)
            doc_data['documento_multipagina'] = True
            doc_data['total_paginas_procesadas'] = len(documentos_bytes)
            processed_data.append(doc_data)
        
        logger.info(f"✅ Documento multipágina procesado: {len(processed_data)} facturas extraídas")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando documento multipágina: {e}")
        return []

def process_image(file) -> List[Dict[str, Any]]:
    """
    Función principal para procesar imágenes de facturas
    Soporta tanto archivos individuales como listas multipágina
    """
    try:
        # Si recibimos una lista, usar el procesamiento multipágina
        if isinstance(file, list):
            return process_image_multipagina(file)
        
        document_analysis_client = get_azure_client()
        if not document_analysis_client:
            logger.error("❌ No se pudo inicializar el cliente de Azure")
            return []
        
        # Procesamiento normal de una sola página
        if hasattr(file, 'file'):
            contenido = file.file.read()
            file.file.seek(0)
        else:
            contenido = file
        
        logger.info(f"📄 Procesando imagen individual")
        
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=contenido
        )
        result = poller.result()
        
        processed_data = []
        for idx, document in enumerate(result.documents):
            doc_data = extract_invoice_data(document)
            doc_data['numero_paginas'] = 1
            doc_data['documento_multipagina'] = False
            doc_data['total_paginas_procesadas'] = 1
            processed_data.append(doc_data)
        
        logger.info(f"✅ Imagen individual procesada: {len(processed_data)} facturas extraídas")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando imagen: {e}")
        return []