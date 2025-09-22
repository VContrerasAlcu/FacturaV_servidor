import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_excel(processed_data):
    try:
        # Procesar los datos de Azure Form Recognizer
        invoice_data = processed_data[0] if processed_data else {}
        
        # Crear un archivo Excel en memoria
        output = BytesIO()
        
        # Crear workbook y worksheet
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Factura"
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        total_font = Font(bold=True, size=14)
        money_format = '#,##0.00€'
        date_format = 'DD/MM/YYYY'
        
        current_row = 1
        
        # 1. Información de la empresa
        worksheet.append(['INFORMACIÓN DE LA EMPRESA'])
        current_row += 1
        worksheet.append(['Campo', 'Valor'])
        current_row += 1
        
        company_info = [
            ['Nombre de la Empresa', invoice_data.get('VendorName', 'No especificado')],
            ['CIF/NIF', invoice_data.get('VendorTaxId', 'No especificado')],
            ['Dirección', invoice_data.get('VendorAddress', 'No especificado')]
        ]
        
        for info in company_info:
            worksheet.append(info)
            current_row += 1
        
        # Aplicar formato a los encabezados de empresa
        for row in worksheet[2:3]:  # Filas 2-3 (encabezados)
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 2. Información de la factura (dejar 2 filas de espacio)
        current_row += 2
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['INFORMACIÓN DE LA FACTURA'])
        current_row += 3
        worksheet.append(['Campo', 'Valor'])
        current_row += 1
        
        # CORREGIDO: Formatear fechas correctamente
        invoice_date = invoice_data.get('InvoiceDate', 'No especificado')
        due_date = invoice_data.get('DueDate', 'No especificado')
        
        # Intentar formatear fechas si son strings en formato ISO
        try:
            if invoice_date and invoice_date != 'No especificado':
                if isinstance(invoice_date, str):
                    # Convertir de formato ISO a datetime
                    invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                    invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
        except (ValueError, AttributeError):
            pass  # Mantener el valor original si hay error
        
        try:
            if due_date and due_date != 'No especificado':
                if isinstance(due_date, str):
                    due_date_obj = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                    due_date = due_date_obj.strftime('%d/%m/%Y')
        except (ValueError, AttributeError):
            pass
        
        invoice_info = [
            ['Número de Factura', invoice_data.get('InvoiceId', 'No especificado')],
            ['Fecha de Factura', invoice_date],
            ['Fecha de Vencimiento', due_date]
        ]
        
        for info in invoice_info:
            worksheet.append(info)
            current_row += 1
        
        # Aplicar formato a los encabezados de factura
        header_start_row = current_row - len(invoice_info) - 1
        for row in worksheet[header_start_row:header_start_row + 1]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 3. Artículos de la factura (dejar 2 filas de espacio)
        current_row += 2
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['ARTÍCULOS FACTURADOS'])
        current_row += 3
        worksheet.append(['Artículo', 'Unidades', 'Precio Unitario', 'Precio Total'])
        current_row += 1
        
        items = invoice_data.get('Items', [])
        items_data = []
        
        for item in items:
            items_data.append([
                item.get('Description', ''),
                item.get('Quantity', 0),
                item.get('UnitPrice', 0),
                item.get('Amount', 0)
            ])
        
        for item in items_data:
            worksheet.append(item)
            current_row += 1
        
        # Aplicar formato a los encabezados de artículos
        items_header_row = current_row - len(items) - 1
        for row in worksheet[items_header_row:items_header_row + 1]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 4. Totales de IVA (dejar 2 filas de espacio)
        current_row += 2
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['DETALLE DE IMPUESTOS'])
        current_row += 3
        worksheet.append(['Tipo de IVA', 'Importe'])
        current_row += 1
        
        tax_details = invoice_data.get('TaxDetails', [])
        tax_data = []
        
        for tax in tax_details:
            # CORREGIDO: Ya no hay % duplicado porque se corrigió en image_processor
            tax_data.append([
                tax.get('Rate', '0%'),
                tax.get('Amount', 0)
            ])
        
        for tax in tax_data:
            worksheet.append(tax)
            current_row += 1
        
        # Aplicar formato a los encabezados de impuestos
        tax_header_row = current_row - len(tax_details) - 1
        for row in worksheet[tax_header_row:tax_header_row + 1]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 5. Total general (dejar 2 filas de espacio)
        current_row += 2
        worksheet.append([])
        worksheet.append([])
        total_amount = invoice_data.get('InvoiceTotal', 0)
        worksheet.append(['TOTAL A PAGAR', total_amount])
        current_row += 1
        
        # Aplicar formato al total
        total_cell = worksheet.cell(row=current_row, column=1)
        total_value_cell = worksheet.cell(row=current_row, column=2)
        
        total_cell.font = total_font
        total_value_cell.font = total_font
        total_value_cell.number_format = money_format
        
        # Ajustar anchos de columnas
        column_widths = [40, 20, 15, 15]
        for i, width in enumerate(column_widths, 1):
            worksheet.column_dimensions[chr(64 + i)].width = width
        
        # Guardar el workbook
        workbook.save(output)
        
        # Obtener bytes del archivo
        excel_data = output.getvalue()
        return excel_data
        
    except Exception as e:
        logger.error(f"Error generando Excel: {e}")
        raise