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
        
        # Procesar resultados
        processed_data = []
        for idx, invoice in enumerate(invoices.documents):
            invoice_data = {}
            for name, field in invoice.fields.items():
                invoice_data[name] = field.value if field else None
            processed_data.append(invoice_data)
        
        return processed_data
        
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        raise