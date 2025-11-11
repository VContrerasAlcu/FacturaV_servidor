# custom_processor.py - CAMBIAR A PREBUILT
import logging
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
from datetime import datetime
import io

logger = logging.getLogger(__name__)

class PrebuiltModelProcessor:
    def __init__(self):
        self.document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        # ✅ CAMBIADO: Usar modelo prebuilt-invoice en lugar de custom
        self.model_id = "prebuilt-invoice"
        logger.info(f"✅ Prebuilt Model Processor inicializado con modelo: {self.model_id}")
    
    async def process_document(self, file):
        """
        Procesa documentos usando el modelo prebuilt-invoice de Azure
        """
        try:
            logger.info(f"🔍 Procesando {file.filename} con modelo prebuilt-invoice...")
            
            file_data = await file.read()
            
            # ✅ CAMBIADO: Usar prebuilt-invoice en lugar de modelo personalizado
            poller = self.document_analysis_client.begin_analyze_document(
                model_id=self.model_id,  # ⬅️ MODELO PREBUILT
                document=io.BytesIO(file_data)
            )
            result = poller.result()
            
            processed_data = self._extract_invoice_data(result, file.filename)
            await file.seek(0)
            
            logger.info(f"✅ {file.filename} procesado: {len(processed_data)} facturas")
            return processed_data
            
        except Exception as e:
            logger.error(f"❌ Error procesando {file.filename}: {e}")
            await file.seek(0)
            return self._create_fallback_data(file.filename, str(e))
    
    def _extract_invoice_data(self, document, filename):
        """
        Extrae datos de facturas usando el modelo prebuilt-invoice
        """
        processed_data = []
        
        if not document.documents:
            logger.warning(f"⚠️ No se encontraron documentos en {filename}")
            return processed_data
        
        for doc_idx, analyzed_doc in enumerate(document.documents):
            try:
                invoice_data = {
                    # INFORMACIÓN VENDEDOR
                    'VendorName': self._get_field_value(analyzed_doc, 'VendorName', 'Empresa No Identificada'),
                    'VendorTaxId': self._get_field_value(analyzed_doc, 'VendorTaxId', 'No disponible'),
                    'VendorAddress': self._get_field_value(analyzed_doc, 'VendorAddress', 'No disponible'),
                    
                    # INFORMACIÓN FACTURA
                    'InvoiceId': self._get_field_value(analyzed_doc, 'InvoiceId', f"FACT_{datetime.now().strftime('%H%M%S')}"),
                    'InvoiceDate': self._get_field_value(analyzed_doc, 'InvoiceDate'),
                    'InvoiceTotal': self._get_field_value(analyzed_doc, 'InvoiceTotal', 0),
                    'DueDate': self._get_field_value(analyzed_doc, 'DueDate'),
                    
                    # CAMPOS ADICIONALES DE PREBUILT
                    'CustomerName': self._get_field_value(analyzed_doc, 'CustomerName'),
                    'CustomerAddress': self._get_field_value(analyzed_doc, 'CustomerAddress'),
                    'SubTotal': self._get_field_value(analyzed_doc, 'SubTotal', 0),
                    'TotalTax': self._get_field_value(analyzed_doc, 'TotalTax', 0),
                    'AmountDue': self._get_field_value(analyzed_doc, 'AmountDue', 0),
                    
                    # IMPUESTOS DESGLOSADOS
                    'TaxDetails': self._extract_tax_details(analyzed_doc),
                    
                    # ITEMS DE LA FACTURA
                    'Items': self._extract_items(analyzed_doc),
                    
                    # METADATA
                    'archivo_origen': filename,
                    'timestamp_procesamiento': datetime.now().isoformat(),
                    'procesamiento': 'azure_prebuilt_invoice',
                    'confidence_level': 'high',
                    'document_index': doc_idx + 1,
                    'campos_detectados': list(analyzed_doc.fields.keys()) if analyzed_doc.fields else []
                }
                
                processed_data.append(invoice_data)
                logger.info(f"📄 Factura {doc_idx + 1}: {invoice_data['VendorName']} - {invoice_data['InvoiceId']}")
                
            except Exception as e:
                logger.error(f"❌ Error procesando documento {doc_idx + 1}: {e}")
                continue
        
        return processed_data
    
    def _get_field_value(self, doc, field_name, default=None):
        """Obtiene valor de campo con manejo seguro"""
        if field_name in doc.fields:
            field = doc.fields[field_name]
            if field and hasattr(field, 'value') and field.value is not None:
                return field.value
        return default
    
    def _extract_tax_details(self, doc):
        """
        Extrae detalles de impuestos del modelo prebuilt
        """
        tax_details = []
        
        # Campo TaxDetails en prebuilt-invoice
        if 'TaxDetails' in doc.fields:
            tax_field = doc.fields['TaxDetails']
            if tax_field and hasattr(tax_field, 'value'):
                for tax in tax_field.value:
                    rate = self._get_nested_value(tax, 'Rate', '0%')
                    amount = self._get_nested_value(tax, 'Amount', 0)
                    
                    tax_details.append({
                        'Rate': rate,
                        'Amount': amount
                    })
        
        # Si no hay tax details, intentar con TotalTax
        if not tax_details:
            total_tax = self._get_field_value(doc, 'TotalTax', 0)
            if total_tax > 0:
                tax_details.append({
                    'Rate': 'IVA',
                    'Amount': total_tax
                })
        
        return tax_details
    
    def _extract_items(self, doc):
        """
        Extrae items de la factura del modelo prebuilt
        """
        items = []
        
        if 'Items' in doc.fields:
            items_field = doc.fields['Items']
            if items_field and hasattr(items_field, 'value'):
                for item in items_field.value:
                    description = self._get_nested_value(item, 'Description', 'Sin descripción')
                    quantity = self._get_nested_value(item, 'Quantity', 0)
                    unit_price = self._get_nested_value(item, 'UnitPrice', 0)
                    amount = self._get_nested_value(item, 'Amount', 0)
                    
                    # Calcular amount si no está presente
                    if amount == 0 and quantity != 0 and unit_price != 0:
                        amount = quantity * unit_price
                    
                    items.append({
                        'Description': description,
                        'Quantity': quantity,
                        'UnitPrice': unit_price,
                        'Amount': amount
                    })
        
        return items
    
    def _get_nested_value(self, parent, field_name, default=None):
        """Obtiene valor de campos anidados"""
        if hasattr(parent, 'get') and field_name in parent:
            value = parent[field_name]
            if value and hasattr(value, 'value'):
                return value.value
        return default
    
    def _create_fallback_data(self, filename, error_msg):
        """Crea datos de fallback mínimos"""
        return [{
            'VendorName': f"Error_Procesamiento_{filename}",
            'VendorTaxId': 'No disponible',
            'VendorAddress': 'No disponible',
            'InvoiceId': f"ERROR_{datetime.now().strftime('%H%M%S')}",
            'InvoiceDate': None,
            'InvoiceTotal': 0,
            'DueDate': None,
            'CustomerName': None,
            'CustomerAddress': None,
            'SubTotal': 0,
            'TotalTax': 0,
            'AmountDue': 0,
            'TaxDetails': [],
            'Items': [],
            'archivo_origen': filename,
            'timestamp_procesamiento': datetime.now().isoformat(),
            'procesamiento': 'fallback',
            'confidence_level': 'low',
            'error_original': error_msg,
            'campos_detectados': []
        }]