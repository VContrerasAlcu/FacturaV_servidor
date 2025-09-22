from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
import io

def process_image(image_file):
    try:
        # Configurar cliente de Azure Document Intelligence
        document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        
        # Leer imagen
        image_data = image_file.file.read()
        
        # Analizar documento
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-invoice", 
            document=io.BytesIO(image_data)
        )
        invoices = poller.result()
        
        # Procesar resultados de manera más detallada
        processed_data = []
        for idx, invoice in enumerate(invoices.documents):
            invoice_data = {
                # Información del vendedor
                'VendorName': get_field_value(invoice.fields.get('VendorName')),
                'VendorTaxId': get_field_value(invoice.fields.get('VendorTaxId')),
                'VendorAddress': get_field_value(invoice.fields.get('VendorAddress')),
                
                # Información de la factura
                'InvoiceId': get_field_value(invoice.fields.get('InvoiceId')),
                'InvoiceDate': get_field_value(invoice.fields.get('InvoiceDate')),
                'InvoiceTotal': get_field_value(invoice.fields.get('InvoiceTotal')),
                
                # Artículos
                'Items': [],
                'TaxDetails': []
            }
            
            # Procesar items
            items = invoice.fields.get('Items')
            if items and items.value:
                for item in items.value:
                    item_data = {
                        'Description': get_field_value(item.value.get('Description')),
                        'Quantity': get_field_value(item.value.get('Quantity')),
                        'UnitPrice': get_field_value(item.value.get('UnitPrice')),
                        'Amount': get_field_value(item.value.get('Amount'))
                    }
                    invoice_data['Items'].append(item_data)
            
            # Procesar impuestos
            tax_details = invoice.fields.get('TaxDetails')
            if tax_details and tax_details.value:
                for tax in tax_details.value:
                    tax_data = {
                        'Rate': get_field_value(tax.value.get('Rate')),
                        'Amount': get_field_value(tax.value.get('Amount'))
                    }
                    invoice_data['TaxDetails'].append(tax_data)
            
            processed_data.append(invoice_data)
        
        return processed_data
        
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        raise

def get_field_value(field):
    """Extraer valor de un campo de Azure Form Recognizer"""
    if field and field.value:
        if hasattr(field.value, 'strftime'):  # Para campos de fecha
            return field.value.strftime('%Y-%m-%d')
        return field.value
    return None