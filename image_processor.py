from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
import io
import logging
from datetime import datetime

# Configurar logging
logger = logging.getLogger(__name__)


# En image_processor.py - MEJORAR EXTRACCIÓN DE IMPUESTOS

def extract_tax_details_improved(invoice):
    """
    Extrae detalles de impuestos de forma más robusta
    """
    tax_details = []
    
    try:
       
        # EXTRACCIÓN MEJORADA DE IVA - USANDO LA NUEVA FUNCIÓN
        tax_details = extract_tax_details_improved(invoice)
        # 2. SI NO HAY TAXDETAILS, BUSCAR EN CAMPOS ALTERNATIVOS
        if not tax_details:
            logger.info("🔍 Buscando impuestos en campos alternativos...")
            
            # Buscar TotalTax
            total_tax = get_field_value(invoice.fields.get('TotalTax'), 0)
            if total_tax > 0:
                logger.info(f"  📊 TotalTax encontrado: {total_tax}€")
                # Intentar inferir la tasa si hay SubTotal
                subtotal = get_field_value(invoice.fields.get('SubTotal'), 0)
                if subtotal > 0:
                    tax_rate = (total_tax / subtotal) * 100
                    tax_details.append({
                        'Rate': f"IVA {tax_rate:.1f}%",
                        'Amount': total_tax
                    })
                    logger.info(f"  ✅ Impuesto inferido: {tax_rate:.1f}% - {total_tax}€")
                else:
                    tax_details.append({
                        'Rate': 'IVA',
                        'Amount': total_tax
                    })
            
            # Buscar VAT (impuesto específico)
            vat_amount = get_field_value(invoice.fields.get('VAT'), 0)
            if vat_amount > 0 and vat_amount != total_tax:
                tax_details.append({
                    'Rate': 'IVA',
                    'Amount': vat_amount
                })
                logger.info(f"  ✅ VAT encontrado: {vat_amount}€")
        
        # 3. SI NO HAY IMPUESTOS EXPLÍCITOS, CALCULAR DESDE TOTAL Y SUBTOTAL
        if not tax_details:
            invoice_total = get_field_value(invoice.fields.get('InvoiceTotal'), 0)
            subtotal = get_field_value(invoice.fields.get('SubTotal'), 0)
            
            if invoice_total > 0 and subtotal > 0 and invoice_total != subtotal:
                calculated_tax = invoice_total - subtotal
                if calculated_tax > 0:
                    tax_rate = (calculated_tax / subtotal) * 100
                    tax_details.append({
                        'Rate': f"IVA Calculado {tax_rate:.1f}%",
                        'Amount': calculated_tax
                    })
                    logger.info(f"  🧮 Impuesto calculado: {tax_rate:.1f}% - {calculated_tax}€")
    
    except Exception as e:
        logger.error(f"❌ Error en extract_tax_details_improved: {e}")
    
    return tax_details



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

# En image_processor.py - mejora la función process_image

def extract_field_robust(invoice, field_names, default_value=None):
    """
    Busca un campo en múltiples nombres posibles y ubicaciones
    """
    for field_name in field_names:
        if field_name in invoice.fields:
            field = invoice.fields[field_name]
            if field and field.value:
                return get_field_value(field)
    
    # Búsqueda en campos de dirección
    if 'VendorAddress' in invoice.fields:
        address_field = invoice.fields['VendorAddress']
        if address_field and address_field.value:
            address_value = address_field.value
            # Extraer CIF/NIF de la dirección si está disponible
            if hasattr(address_value, 'street_address') and address_value.street_address:
                address_text = address_value.street_address.lower()
                # Buscar patrones de CIF/NIF en el texto de dirección
                import re
                cif_patterns = [
                    r'[A-Z][0-9]{8}',  # CIF español
                    r'[0-9]{8}[A-Z]',  # NIF español
                    r'[A-Z][0-9]{7}[A-Z]',  # CIF antiguo
                ]
                for pattern in cif_patterns:
                    matches = re.findall(pattern, address_text.upper())
                    if matches:
                        return matches[0]
    
    return default_value

def process_image(file):
    try:
        logger.info(f"🔍 Iniciando procesamiento MEJORADO de: {file.filename}")
        
        # Configurar cliente de Azure
        document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        
        file_data = file.file.read()
        logger.info(f"📄 Archivo leído: {len(file_data)} bytes")
        
        # Analizar documento
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=io.BytesIO(file_data)
        )
        invoices = poller.result()
        
        logger.info(f"📊 Azure devolvió {len(invoices.documents)} documentos")
        
        processed_data = []
        for idx, invoice in enumerate(invoices.documents):
            logger.info(f"📋 Procesando documento {idx + 1} con extracción mejorada...")
            
            # EXTRACCIÓN MEJORADA DE CAMPOS CLAVE
            vendor_name = extract_field_robust(
                invoice, 
                ['VendorName', 'VendorOrganization', 'Vendor'],
                'Empresa No Identificada'
            )
            
            vendor_tax_id = extract_field_robust(
                invoice,
                ['VendorTaxId', 'VendorId', 'VendorNumber', 'TaxId'],
                'No disponible'
            )
            
            # MEJORAR EXTRACCIÓN DE TOTALES
            invoice_total = extract_field_robust(
                invoice,
                ['InvoiceTotal', 'AmountDue', 'Total', 'GrandTotal', 'TotalAmount'],
                0
            )
            
            # Si no encuentra el total, calcularlo
            if not invoice_total or invoice_total == 0:
                subtotal = get_field_value(invoice.fields.get('SubTotal'), 0)
                total_tax = get_field_value(invoice.fields.get('TotalTax'), 0)
                invoice_total = subtotal + total_tax
                logger.info(f"🔄 Total calculado: {subtotal} + {total_tax} = {invoice_total}")
            
            # EXTRACCIÓN MEJORADA DE IVA
            tax_details = []
            tax_fields = invoice.fields.get('TaxDetails')
            if tax_fields and tax_fields.value:
                for tax in tax_fields.value:
                    rate = get_tax_rate_value(tax.value.get('Rate'))
                    amount = get_field_value(tax.value.get('Amount'), 0)
                    tax_details.append({
                        'Rate': rate if rate else '21%',  # Valor por defecto común
                        'Amount': amount
                    })
            
            # Si no hay impuestos detectados, intentar inferirlos
            if not tax_details and invoice_total > 0:
                subtotal = get_field_value(invoice.fields.get('SubTotal'), 0)
                if subtotal > 0:
                    tax_amount = invoice_total - subtotal
                    if tax_amount > 0:
                        tax_rate = (tax_amount / subtotal) * 100
                        tax_details.append({
                            'Rate': f"{tax_rate:.1f}%",
                            'Amount': tax_amount
                        })
                        logger.info(f"🔄 IVA inferido: {tax_amount} ({tax_rate:.1f}%)")
            
            invoice_data = {
                # Información del vendedor
                'VendorName': vendor_name,
                'VendorTaxId': vendor_tax_id,
                'VendorAddress': extract_field_robust(
                    invoice, 
                    ['VendorAddress', 'VendorStreet', 'VendorLocation'],
                    'No disponible'
                ),
                
                # Información de la factura
                'InvoiceId': extract_field_robust(
                    invoice,
                    ['InvoiceId', 'InvoiceNumber', 'DocumentNumber'],
                    f"FACT_{datetime.now().strftime('%H%M%S')}_{idx}"
                ),
                'InvoiceDate': get_field_value(invoice.fields.get('InvoiceDate')),
                'InvoiceTotal': invoice_total,
                'DueDate': get_field_value(invoice.fields.get('DueDate')),
                
                # Campos calculados/mejorados
                'SubTotal': get_field_value(invoice.fields.get('SubTotal'), 0),
                'TotalTax': get_field_value(invoice.fields.get('TotalTax'), 0),
                'AmountDue': get_field_value(invoice.fields.get('AmountDue'), 0),
                
                # Artículos e impuestos
                'Items': [],
                'TaxDetails': tax_details,
                
                # Metadata mejorada
                'procesamiento': 'azure_enhanced_plus',
                'confidence_level': 'enhanced',
                'campos_detectados': list(invoice.fields.keys()) if invoice.fields else []
            }
            
            # Procesar items (mantener lógica existente pero mejorada)
            items = invoice.fields.get('Items')
            if items and items.value:
                for item in items.value:
                    description = get_field_value(item.value.get('Description'), 'Sin descripción')
                    quantity = get_field_value(item.value.get('Quantity'), 0)
                    unit_price = get_field_value(item.value.get('UnitPrice'), 0)
                    amount = get_field_value(item.value.get('Amount'), 0)
                    
                    # Calcular amount si no está presente
                    if amount == 0 and quantity != 0 and unit_price != 0:
                        amount = quantity * unit_price
                    
                    invoice_data['Items'].append({
                        'Description': description,
                        'Quantity': quantity,
                        'UnitPrice': unit_price,
                        'Amount': amount
                    })
            
            # VALIDACIÓN MEJORADA
            required_fields_valid = validate_extracted_data(invoice_data)
            
            if required_fields_valid:
                processed_data.append(invoice_data)
                logger.info(f"✅ Documento {idx + 1} procesado: {vendor_name} - {invoice_data['InvoiceId']} - {invoice_total}€")
            else:
                logger.warning(f"⚠️ Documento {idx + 1} tiene datos limitados, pero se incluirá")
                processed_data.append(invoice_data)
        
        logger.info(f"✅ Archivo {file.filename} procesado: {len(processed_data)} facturas extraídas")
        return processed_data
        
    except Exception as e:
        logger.error(f"❌ Error procesando archivo {file.filename}: {e}")
        # Fallback mejorado
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
            'error_original': str(e),
            'campos_detectados': []
        }
        return [basic_data]