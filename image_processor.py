from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
import io
import logging
from datetime import datetime

# Configurar logging
logger = logging.getLogger(__name__)

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

def enhance_azure_extraction(invoice):
    """
    Mejora la extracción de datos con valores por defecto más inteligentes
    y búsqueda en campos alternativos
    """
    try:
        logger.info("🔄 Mejorando extracción de datos de Azure...")
        
        # INTENTAR EXTRAER VENDORNAME DE MÚLTIPLES FUENTES
        vendor_name = get_field_value(invoice.fields.get('VendorName'))
        if not vendor_name or vendor_name in ['No identificado', 'None', '']:
            logger.info("Buscando VendorName en campos alternativos...")
            # Intentar VendorAddress u otros campos
            vendor_address = invoice.fields.get('VendorAddress')
            if vendor_address and vendor_address.value:
                if hasattr(vendor_address.value, 'organization'):
                    vendor_name = vendor_address.value.organization
                elif hasattr(vendor_address.value, 'street_address'):
                    vendor_name = "Empresa en " + vendor_address.value.street_address
        
        if not vendor_name or vendor_name in ['No identificado', 'None', '']:
            vendor_name = "Empresa No Identificada"
            logger.warning("⚠️ No se pudo identificar la empresa")
        
        # MEJORAR EXTRACCIÓN DE INVOICE ID
        invoice_id = get_field_value(invoice.fields.get('InvoiceId'))
        if not invoice_id or invoice_id in ['Sin número', 'None', '']:
            # Buscar en campos alternativos
            invoice_number = get_field_value(invoice.fields.get('InvoiceNumber'))
            if invoice_number and invoice_number not in ['Sin número', 'None', '']:
                invoice_id = invoice_number
            else:
                # Usar timestamp como fallback único
                invoice_id = f"FACT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                logger.info(f"📝 Usando ID generado: {invoice_id}")
        
        # MEJORAR EXTRACCIÓN DE TOTAL
        invoice_total = get_field_value(invoice.fields.get('InvoiceTotal'), 0)
        if invoice_total == 0:
            # Intentar campos alternativos para el total
            total_amount = get_field_value(invoice.fields.get('TotalAmount'))
            if total_amount and total_amount != 0:
                invoice_total = total_amount
        
        return {
            'VendorName': vendor_name,
            'InvoiceId': invoice_id,
            'InvoiceTotal': invoice_total,
            'confidence_level': 'enhanced'
        }
        
    except Exception as e:
        logger.error(f"❌ Error en enhance_azure_extraction: {e}")
        return None

def validate_extracted_data(invoice_data):
    """
    Valida que los datos extraídos sean mínimamente útiles
    """
    if not invoice_data:
        return False
        
    # Verificar que tenemos al menos algunos datos válidos
    required_fields = ['VendorName', 'InvoiceId', 'InvoiceTotal']
    valid_fields = 0
    
    for field in required_fields:
        value = invoice_data.get(field)
        if value and value not in ['No identificado', 'Sin número', 'None', '', 0]:
            valid_fields += 1
    
    # Considerar válido si al menos 2 campos tienen datos reales
    is_valid = valid_fields >= 2
    logger.info(f"📊 Validación datos: {valid_fields}/3 campos válidos → {'✅ VÁLIDO' if is_valid else '❌ INSUFICIENTE'}")
    
    return is_valid

def process_image(file):
    try:
        logger.info(f"🔍 Iniciando procesamiento de: {file.filename}")
        
        # Configurar cliente de Azure Document Intelligence
        document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        
        # Leer archivo (PDF o imagen)
        file_data = file.file.read()
        logger.info(f"📄 Archivo leído: {len(file_data)} bytes")
        
        # Analizar documento
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=io.BytesIO(file_data)
        )
        invoices = poller.result()
        
        logger.info(f"📊 Azure devolvió {len(invoices.documents)} documentos")
        
        # Procesar resultados con mejor manejo de errores
        processed_data = []
        for idx, invoice in enumerate(invoices.documents):
            logger.info(f"📋 Procesando documento {idx + 1}...")
            
            # MEJORAR EXTRACCIÓN CON ENHANCE
            enhanced_data = enhance_azure_extraction(invoice)
            
            # Extraer valores usando get_field_value (método original)
            vendor_name = get_field_value(invoice.fields.get('VendorName'))
            vendor_tax_id = get_field_value(invoice.fields.get('VendorTaxId'))
            vendor_address = get_field_value(invoice.fields.get('VendorAddress'))
            invoice_id = get_field_value(invoice.fields.get('InvoiceId'))
            invoice_date = get_field_value(invoice.fields.get('InvoiceDate'))
            invoice_total = get_field_value(invoice.fields.get('InvoiceTotal'))
            due_date = get_field_value(invoice.fields.get('DueDate'))
            
            # USAR DATOS MEJORADOS SI LOS TENEMOS
            if enhanced_data:
                vendor_name = enhanced_data['VendorName']
                invoice_id = enhanced_data['InvoiceId']
                invoice_total = enhanced_data['InvoiceTotal']
            
            # Aplicar valores por defecto después de get_field_value
            invoice_data = {
                # Información del vendedor con valores por defecto
                'VendorName': vendor_name if vendor_name and vendor_name != 'No identificado' else 'Empresa No Identificada',
                'VendorTaxId': vendor_tax_id if vendor_tax_id and vendor_tax_id != 'No disponible' else 'No disponible',
                'VendorAddress': vendor_address if vendor_address and vendor_address != 'No disponible' else 'No disponible',
                
                # Información de la factura
                'InvoiceId': invoice_id if invoice_id and invoice_id != 'Sin número' else f"FACT_{datetime.now().strftime('%H%M%S')}_{idx}",
                'InvoiceDate': invoice_date,
                'InvoiceTotal': invoice_total if invoice_total else 0,
                'DueDate': due_date,
                
                # Artículos
                'Items': [],
                'TaxDetails': [],
                
                # Metadata de procesamiento
                'procesamiento': 'azure_enhanced',
                'confidence_level': enhanced_data.get('confidence_level', 'basic') if enhanced_data else 'basic'
            }
            
            # LOG para debug
            logger.info(f"📄 Factura procesada - Empresa: {invoice_data['VendorName']}, Número: {invoice_data['InvoiceId']}, Total: {invoice_data['InvoiceTotal']}")
            
            # Procesar items
            items = invoice.fields.get('Items')
            if items and items.value:
                logger.info(f"🛒 Procesando {len(items.value)} items...")
                for item in items.value:
                    # Extraer valores de items
                    description = get_field_value(item.value.get('Description'))
                    quantity = get_field_value(item.value.get('Quantity'))
                    unit_price = get_field_value(item.value.get('UnitPrice'))
                    amount = get_field_value(item.value.get('Amount'))
                    
                    item_data = {
                        'Description': description if description else 'Sin descripción',
                        'Quantity': quantity if quantity else 0,
                        'UnitPrice': unit_price if unit_price else 0,
                        'Amount': amount if amount else 0
                    }
                    invoice_data['Items'].append(item_data)
            else:
                logger.info("📭 No se encontraron items en la factura")
            
            # Procesar impuestos
            tax_details = invoice.fields.get('TaxDetails')
            if tax_details and tax_details.value:
                logger.info(f"💰 Procesando {len(tax_details.value)} impuestos...")
                for tax in tax_details.value:
                    # Extraer valores de impuestos
                    rate = get_tax_rate_value(tax.value.get('Rate'))
                    amount = get_field_value(tax.value.get('Amount'))
                    
                    tax_data = {
                        'Rate': rate if rate else '0%',
                        'Amount': amount if amount else 0
                    }
                    invoice_data['TaxDetails'].append(tax_data)
            else:
                logger.info("📭 No se encontraron impuestos en la factura")
            
            # VALIDAR DATOS EXTRAÍDOS
            is_valid = validate_extracted_data(invoice_data)
            if is_valid:
                processed_data.append(invoice_data)
                logger.info(f"✅ Documento {idx + 1} procesado y validado")
            else:
                logger.warning(f"⚠️ Documento {idx + 1} tiene datos insuficientes, pero se incluirá igual")
                processed_data.append(invoice_data)
        
        logger.info(f"✅ Archivo {file.filename} procesado: {len(processed_data)} facturas extraídas")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando archivo {file.filename}: {e}")
        # CREAR DATOS BÁSICOS COMO FALLBACK
        logger.info("🔄 Creando datos básicos como fallback...")
        basic_data = {
            'VendorName': f"Empresa_Desde_{file.filename}",
            'InvoiceId': f"FALLBACK_{datetime.now().strftime('%H%M%S')}",
            'InvoiceTotal': 0,
            'VendorTaxId': 'No disponible',
            'VendorAddress': 'No disponible',
            'InvoiceDate': None,
            'DueDate': None,
            'Items': [],
            'TaxDetails': [],
            'procesamiento': 'fallback_basico',
            'confidence_level': 'low',
            'error_original': str(e)
        }
        return [basic_data]