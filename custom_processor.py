# custom_processor.py
import logging
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from config import settings
from datetime import datetime
import io

logger = logging.getLogger(__name__)

class CustomModelProcessor:
    def __init__(self):
        self.document_analysis_client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY)
        )
        self.custom_model_id = settings.AZURE_CUSTOM_MODEL_ID
        logger.info(f"✅ Custom Model Processor inicializado con modelo: {self.custom_model_id}")
    
    async def process_document(self, file):
        """
        Procesa documentos usando SOLO tu modelo personalizado
        """
        try:
            logger.info(f"🔍 Procesando {file.filename} con modelo personalizado...")
            
            file_data = await file.read()
            
            poller = self.document_analysis_client.begin_analyze_document(
                model_id=self.custom_model_id,  # ⬅️ USANDO TU MODELO
                document=io.BytesIO(file_data)
            )
            result = poller.result()
            
            processed_data = self._extract_simplified_fields(result, file.filename)
            await file.seek(0)
            
            logger.info(f"✅ {file.filename} procesado: {len(processed_data)} facturas")
            return processed_data
            
        except Exception as e:
            logger.error(f"❌ Error procesando {file.filename}: {e}")
            await file.seek(0)
            return self._create_fallback_data(file.filename, str(e))
    
    def _extract_simplified_fields(self, document, filename):
        """
        Extrae SOLO los campos que necesitas
        """
        processed_data = []
        
        if not document.documents:
            logger.warning(f"⚠️ No se encontraron documentos en {filename}")
            return processed_data
        
        for doc_idx, doc in enumerate(document.documents):
            invoice_data = {
                # INFORMACIÓN VENDEDOR (SOLO estos campos)
                'VendorName': self._get_field_value(doc, 'VendorName', 'Empresa No Identificada'),
                'VendorTaxId': self._get_field_value(doc, 'VendorTaxId', 'No disponible'),
                'VendorAddress': self._get_field_value(doc, 'VendorAddress', 'No disponible'),
                
                # INFORMACIÓN FACTURA (SOLO estos campos)
                'InvoiceId': self._get_field_value(doc, 'InvoiceId', f"FACT_{datetime.now().strftime('%H%M%S')}"),
                'InvoiceDate': self._get_field_value(doc, 'InvoiceDate'),
                'InvoiceTotal': self._get_field_value(doc, 'InvoiceTotal', 0),
                
                # IMPUESTOS DESGLOSADOS
                'TaxDetails': self._extract_tax_details(doc),
                
                # METADATA
                'archivo_origen': filename,
                'timestamp_procesamiento': datetime.now().isoformat(),
                'procesamiento': 'custom_model',
                'confidence_level': 'high',
                'document_index': doc_idx + 1
            }
            
            processed_data.append(invoice_data)
            logger.info(f"📄 Factura {doc_idx + 1}: {invoice_data['VendorName']} - {invoice_data['InvoiceId']}")
        
        return processed_data
    
    def _get_field_value(self, doc, field_name, default=None):
        """Obtiene valor de campo con manejo seguro"""
        if field_name in doc.fields:
            field = doc.fields[field_name]
            if field and hasattr(field, 'value') and field.value:
                return field.value
        return default
    
    def _extract_tax_details(self, doc):
        """
        Extrae detalles de impuestos desglosados
        """
        tax_details = []
        
        # Campo TaxDetails (array de impuestos)
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
        
        return tax_details
    
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
            'TaxDetails': [],
            'archivo_origen': filename,
            'timestamp_procesamiento': datetime.now().isoformat(),
            'procesamiento': 'fallback',
            'confidence_level': 'low',
            'error': error_msg
        }]