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

def generate_excel(processed_data_list):
    """
    Genera un archivo Excel con TODAS las facturas procesadas
    processed_data_list: Lista de diccionarios con datos de múltiples facturas
    """
    try:
        logger.info(f"📊 Generando Excel con {len(processed_data_list)} elementos de facturas")
        
        # Verificar que tenemos datos
        if not processed_data_list:
            logger.error("❌ No hay datos para generar Excel")
            return None
        
        # Crear un archivo Excel en memoria
        output = BytesIO()
        workbook = Workbook()
        
        # Eliminar la hoja por defecto si vamos a crear múltiples hojas
        workbook.remove(workbook.active)
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        total_font = Font(bold=True, size=14)
        money_format = '#,##0.00€'
        
        # Agrupar datos por archivo de origen (cada factura)
        facturas = {}
        for data in processed_data_list:
            archivo_origen = data.get('archivo_origen', 'Desconocido')
            if archivo_origen not in facturas:
                facturas[archivo_origen] = []
            facturas[archivo_origen].append(data)
        
        logger.info(f"📁 Facturas a procesar: {list(facturas.keys())}")
        
        # Crear una hoja para cada factura
        for archivo, datos_factura in facturas.items():
            logger.info(f"📄 Procesando factura: {archivo} con {len(datos_factura)} elementos")
            
            # Usar el primer elemento de cada factura para la información principal
            invoice_data = datos_factura[0] if datos_factura else {}
            
            # Crear hoja para esta factura (limitar nombre a 31 caracteres)
            sheet_name = archivo[:31] if len(archivo) > 31 else archivo
            if not sheet_name:
                sheet_name = f"Factura_{len(workbook.worksheets) + 1}"
            
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1
            
            # 1. Información del archivo origen
            worksheet.append(['INFORMACIÓN DEL ARCHIVO'])
            worksheet.append(['Archivo de origen:', archivo])
            worksheet.append(['Número de elementos:', len(datos_factura)])
            worksheet.append(['Fecha de procesamiento:', datetime.now().strftime('%d/%m/%Y %H:%M')])
            current_row += 4
            
            # 2. Información de la empresa
            worksheet.append([])
            worksheet.append(['INFORMACIÓN DE LA EMPRESA'])
            current_row += 2
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
            for row in worksheet[6:7]:  # Encabezados de empresa
                for cell in row:
                    cell.font = header_font
                    cell.fill = header_fill
            
            # 3. Información de la factura
            current_row += 2
            worksheet.append([])
            worksheet.append(['INFORMACIÓN DE LA FACTURA'])
            current_row += 2
            worksheet.append(['Campo', 'Valor'])
            current_row += 1
            
            # Formatear fechas
            invoice_date = invoice_data.get('InvoiceDate', 'No especificado')
            due_date = invoice_data.get('DueDate', 'No especificado')
            
            try:
                if invoice_date and invoice_date != 'No especificado' and isinstance(invoice_date, str):
                    invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                    invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
            except (ValueError, AttributeError):
                pass
            
            try:
                if due_date and due_date != 'No especificado' and isinstance(due_date, str):
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
            for row in worksheet[current_row - len(invoice_info) - 1:current_row - len(invoice_info)]:
                for cell in row:
                    cell.font = header_font
                    cell.fill = header_fill
            
            # 4. Artículos de la factura
            current_row += 2
            worksheet.append([])
            worksheet.append(['ARTÍCULOS FACTURADOS'])
            current_row += 2
            worksheet.append(['Artículo', 'Unidades', 'Precio Unitario', 'Precio Total'])
            current_row += 1
            
            items = invoice_data.get('Items', [])
            for item in items:
                worksheet.append([
                    item.get('Description', ''),
                    item.get('Quantity', 0),
                    item.get('UnitPrice', 0),
                    item.get('Amount', 0)
                ])
                current_row += 1
            
            # Aplicar formato a los encabezados de artículos
            for row in worksheet[current_row - len(items) - 1:current_row - len(items)]:
                for cell in row:
                    cell.font = header_font
                    cell.fill = header_fill
            
            # 5. Totales de IVA
            current_row += 2
            worksheet.append([])
            worksheet.append(['DETALLE DE IMPUESTOS'])
            current_row += 2
            worksheet.append(['Tipo de IVA', 'Importe'])
            current_row += 1
            
            tax_details = invoice_data.get('TaxDetails', [])
            for tax in tax_details:
                worksheet.append([
                    tax.get('Rate', '0%'),
                    tax.get('Amount', 0)
                ])
                current_row += 1
            
            # Aplicar formato a los encabezados de impuestos
            for row in worksheet[current_row - len(tax_details) - 1:current_row - len(tax_details)]:
                for cell in row:
                    cell.font = header_font
                    cell.fill = header_fill
            
            # 6. Total general
            current_row += 2
            worksheet.append([])
            total_amount = invoice_data.get('InvoiceTotal', 0)
            worksheet.append(['TOTAL A PAGAR', total_amount])
            
            # Aplicar formato al total
            total_cell = worksheet.cell(row=current_row + 2, column=1)
            total_value_cell = worksheet.cell(row=current_row + 2, column=2)
            
            total_cell.font = total_font
            total_value_cell.font = total_font
            total_value_cell.number_format = money_format
            
            # Ajustar anchos de columnas
            column_widths = [40, 20, 15, 15]
            for i, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[chr(64 + i)].width = width
        
        # Crear hoja de resumen con todas las facturas
        summary_sheet = workbook.create_sheet(title="Resumen General")
        summary_sheet.append(['RESUMEN DE TODAS LAS FACTURAS'])
        summary_sheet.append(['Archivo', 'Número Factura', 'Proveedor', 'Fecha', 'Total', 'Número de Items'])
        
        for archivo, datos_factura in facturas.items():
            if datos_factura:
                invoice_data = datos_factura[0]
                items_count = len(invoice_data.get('Items', []))
                
                # Formatear fecha
                invoice_date = invoice_data.get('InvoiceDate', 'No especificado')
                try:
                    if invoice_date and invoice_date != 'No especificado' and isinstance(invoice_date, str):
                        invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                        invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
                except (ValueError, AttributeError):
                    pass
                
                summary_sheet.append([
                    archivo,
                    invoice_data.get('InvoiceId', 'N/A'),
                    invoice_data.get('VendorName', 'N/A'),
                    invoice_date,
                    invoice_data.get('InvoiceTotal', 0),
                    items_count
                ])
        
        # Aplicar formato a la hoja de resumen
        for row in summary_sheet[1:2]:  # Encabezados del resumen
            for cell in row:
                cell.font = header_font
                cell.fill = header_fill
        
        # Ajustar anchos en la hoja de resumen
        summary_widths = [30, 20, 30, 15, 15, 15]
        for i, width in enumerate(summary_widths, 1):
            summary_sheet.column_dimensions[chr(64 + i)].width = width
        
        # Guardar el workbook
        workbook.save(output)
        output.seek(0)
        
        excel_data = output.getvalue()
        logger.info(f"✅ Excel generado exitosamente - Tamaño: {len(excel_data)} bytes")
        logger.info(f"📑 Hojas creadas: {[sheet.title for sheet in workbook.worksheets]}")
        
        return excel_data
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel: {e}")
        
        # Crear un Excel de error como fallback
        try:
            error_workbook = Workbook()
            error_sheet = error_workbook.active
            error_sheet.title = "Error"
            error_sheet.append(['Error al generar el reporte'])
            error_sheet.append([f'Detalle: {str(e)}'])
            error_sheet.append([f'Datos recibidos: {len(processed_data_list)} elementos'])
            
            error_output = BytesIO()
            error_workbook.save(error_output)
            error_output.seek(0)
            return error_output.getvalue()
        except:
            return None