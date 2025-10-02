from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
import io
import logging

# Configurar logging
logger = logging.getLogger(__name__)

def process_image(file):
    try:
        # Configurar cliente de Azure Document Intelligence
        document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        
        # Leer archivo (PDF o imagen)
        file_data = file.file.read()
        
        # Analizar documento
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=io.BytesIO(file_data)
        )
        invoices = poller.result()
        
        # Procesar resultados con mejor manejo de errores
        processed_data = []
        for idx, invoice in enumerate(invoices.documents):
            invoice_data = {
                # Información del vendedor con valores por defecto
                'VendorName': get_field_value(invoice.fields.get('VendorName'), 'No identificado'),
                'VendorTaxId': get_field_value(invoice.fields.get('VendorTaxId'), 'No disponible'),
                'VendorAddress': get_field_value(invoice.fields.get('VendorAddress'), 'No disponible'),
                
                # Información de la factura
                'InvoiceId': get_field_value(invoice.fields.get('InvoiceId'), 'Sin número'),
                'InvoiceDate': get_field_value(invoice.fields.get('InvoiceDate')),
                'InvoiceTotal': get_field_value(invoice.fields.get('InvoiceTotal'), 0),
                'DueDate': get_field_value(invoice.fields.get('DueDate')),
                
                # Artículos
                'Items': [],
                'TaxDetails': []
            }
            
            # ✅ LOG PARA DEBUG
            logger.info(f"📄 Factura procesada - Empresa: {invoice_data['VendorName']}, Número: {invoice_data['InvoiceId']}")
            
            # Procesar items
            items = invoice.fields.get('Items')
            if items and items.value:
                for item in items.value:
                    item_data = {
                        'Description': get_field_value(item.value.get('Description'), 'Sin descripción'),
                        'Quantity': get_field_value(item.value.get('Quantity'), 0),
                        'UnitPrice': get_field_value(item.value.get('UnitPrice'), 0),
                        'Amount': get_field_value(item.value.get('Amount'), 0)
                    }
                    invoice_data['Items'].append(item_data)
            
            # Procesar impuestos
            tax_details = invoice.fields.get('TaxDetails')
            if tax_details and tax_details.value:
                for tax in tax_details.value:
                    tax_data = {
                        'Rate': get_tax_rate_value(tax.value.get('Rate')),
                        'Amount': get_field_value(tax.value.get('Amount'), 0)
                    }
                    invoice_data['TaxDetails'].append(tax_data)
            
            processed_data.append(invoice_data)
        
        return processed_data
        
    except Exception as e:
        logger.error(f"Error procesando archivo {file.filename}: {e}")
        raise

# ✅ MEJORAR get_field_value PARA MANEJAR VALORES POR DEFECTO
def get_field_value(field, default_value=None):
    """Extraer valor de un campo de Azure Form Recognizer con valor por defecto"""
    if not field or not field.value:
        return default_value
    
    value = field.value
    
    try:
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
            
            return ", ".join(address_parts) if address_parts else default_value
        
        # Para currency values
        elif hasattr(value, 'amount'):
            return value.amount
        
        # Para otros tipos, devolver el valor directamente
        return value
        
    except Exception as e:
        logger.warning(f"Error procesando campo: {e}")
        # Fallback: convertir a string
        try:
            return str(value)
        except:
            return default_value
        
def get_field_value(field):
    """Extraer valor de un campo de Azure Form Recognizer de manera segura"""
    if not field or not field.value:
        return None
    
    value = field.value
    
    try:
        # Manejar tipos especiales
        if hasattr(value, 'strftime'):  # Fechas
            return value.strftime('%Y-%m-%d')
        
        elif hasattr(value, 'street_address'):  # Direcciones
            address = value
            # Intentar obtener la dirección formateada
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
        # Fallback: convertir a string
        try:
            return str(value)
        except:
            return None

def get_tax_rate_value(rate_field):
    """Función específica para manejar tasas de impuestos y quitar el % duplicado"""
    if not rate_field or not rate_field.value:
        return None
    
    rate_value = rate_field.value
    
    try:
        # Si el valor es un string que ya contiene %, limpiarlo
        if isinstance(rate_value, str):
            # Remover cualquier % existente y espacios
            cleaned_rate = rate_value.replace('%', '').strip()
            # Convertir a número y formatear con un solo %
            try:
                rate_num = float(cleaned_rate)
                return f"{rate_num}%"
            except ValueError:
                return rate_value  # Devolver original si no se puede convertir
        
        # Si es un número, formatearlo con un solo %
        elif isinstance(rate_value, (int, float)):
            return f"{rate_value}%"
        
        # Para otros tipos, convertir a string y limpiar
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