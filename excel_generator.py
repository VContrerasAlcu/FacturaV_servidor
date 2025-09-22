import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
import logging

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
        
        # 1. Información de la empresa
        worksheet.append(['INFORMACIÓN DE LA EMPRESA'])
        worksheet.append(['Campo', 'Valor'])
        
        company_info = [
            ['Nombre de la Empresa', invoice_data.get('VendorName', 'No especificado')],
            ['CIF/NIF', invoice_data.get('VendorTaxId', 'No especificado')],
            ['Dirección', invoice_data.get('VendorAddress', 'No especificado')]
        ]
        
        for info in company_info:
            worksheet.append(info)
        
        # Aplicar formato a los encabezados de empresa
        for row in worksheet[1:2]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 2. Información de la factura (dejar 2 filas de espacio)
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['INFORMACIÓN DE LA FACTURA'])
        worksheet.append(['Campo', 'Valor'])
        
        invoice_info = [
            ['Número de Factura', invoice_data.get('InvoiceId', 'No especificado')],
            ['Fecha de Factura', invoice_data.get('InvoiceDate', 'No especificado')],
            ['Fecha de Vencimiento', invoice_data.get('DueDate', 'No especificado')]
        ]
        
        for info in invoice_info:
            worksheet.append(info)
        
        # Aplicar formato a los encabezados de factura
        for row in worksheet[8:9]:  # Ajustar según la posición real
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 3. Artículos de la factura (dejar 2 filas de espacio)
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['ARTÍCULOS FACTURADOS'])
        worksheet.append(['Artículo', 'Unidades', 'Precio Unitario', 'Precio Total'])
        
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
        
        # Aplicar formato a los encabezados de artículos
        last_item_row = 13 + len(items)  # Ajustar según la posición real
        for row in worksheet[last_item_row - len(items) - 2:last_item_row - len(items) - 1]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 4. Totales de IVA (dejar 2 filas de espacio)
        worksheet.append([])
        worksheet.append([])
        worksheet.append(['DETALLE DE IMPUESTOS'])
        worksheet.append(['Tipo de IVA', 'Importe'])
        
        tax_details = invoice_data.get('TaxDetails', [])
        tax_data = []
        
        for tax in tax_details:
            tax_data.append([
                f"{tax.get('Rate', 0)}%",
                tax.get('Amount', 0)
            ])
        
        for tax in tax_data:
            worksheet.append(tax)
        
        # Aplicar formato a los encabezados de impuestos
        last_tax_row = last_item_row + 4 + len(tax_details)
        for row in worksheet[last_tax_row - len(tax_details) - 2:last_tax_row - len(tax_details) - 1]:
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # 5. Total general (dejar 2 filas de espacio)
        worksheet.append([])
        worksheet.append([])
        total_amount = invoice_data.get('InvoiceTotal', 0)
        worksheet.append(['TOTAL A PAGAR', total_amount])
        
        # Aplicar formato al total
        total_row = last_tax_row + 4
        total_cell = worksheet.cell(row=total_row, column=1)
        total_value_cell = worksheet.cell(row=total_row, column=2)
        
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