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
        logger.info(f"📊 INICIANDO GENERACIÓN DE EXCEL")
        logger.info(f"📦 Total de elementos recibidos: {len(processed_data_list)}")
        
        # Verificar que tenemos datos
        if not processed_data_list:
            logger.error("❌ No hay datos para generar Excel")
            return None
        
        # DEBUG: Mostrar estructura de los datos recibidos
        archivos_unicos = set()
        for i, data in enumerate(processed_data_list):
            archivo_origen = data.get('archivo_origen', 'Desconocido')
            archivos_unicos.add(archivo_origen)
            if i < 3:  # Mostrar solo primeros 3 para no saturar logs
                logger.info(f"📄 Elemento {i+1}: Archivo='{archivo_origen}', Keys={list(data.keys())}")
        
        logger.info(f"📁 Archivos únicos detectados: {len(archivos_unicos)}")
        logger.info(f"📂 Lista de archivos: {list(archivos_unicos)}")
        
        # Agrupar datos por archivo de origen (cada factura)
        facturas = {}
        for data in processed_data_list:
            archivo_origen = data.get('archivo_origen', 'Desconocido')
            if archivo_origen not in facturas:
                facturas[archivo_origen] = []
            facturas[archivo_origen].append(data)
        
        logger.info(f"📑 Facturas a procesar: {len(facturas)}")
        for archivo, datos in facturas.items():
            logger.info(f"   📋 {archivo}: {len(datos)} elementos")
        
        # Crear un archivo Excel en memoria
        output = BytesIO()
        workbook = Workbook()
        
        # Eliminar la hoja por defecto si vamos a crear múltiples hojas
        if workbook.sheetnames:
            workbook.remove(workbook.active)
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        total_font = Font(bold=True, size=14)
        money_format = '#,##0.00€'
        
        # Crear una hoja para cada factura
        for archivo, datos_factura in facturas.items():
            logger.info(f"📄 Creando hoja para: {archivo}")
            
            # Usar el primer elemento de cada factura para la información principal
            invoice_data = datos_factura[0] if datos_factura else {}
            
            # Crear hoja para esta factura (limitar nombre a 31 caracteres)
            sheet_name = archivo[:31] if len(archivo) > 31 else archivo
            if not sheet_name or sheet_name.isspace():
                sheet_name = f"Factura_{len(workbook.worksheets) + 1}"
            
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1
            
            # 1. Información del archivo origen
            worksheet.append(['INFORMACIÓN DEL ARCHIVO'])
            worksheet.append(['Archivo de origen:', archivo])
            worksheet.append(['Número de elementos procesados:', len(datos_factura)])
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
            for row in worksheet[6:7]:
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
        if len(facturas) > 1:
            logger.info("📑 Creando hoja de resumen general")
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
            for row in summary_sheet[1:2]:
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
        logger.info(f"✅ Excel generado exitosamente")
        logger.info(f"📊 Tamaño del archivo: {len(excel_data)} bytes")
        logger.info(f"📑 Hojas creadas: {[sheet.title for sheet in workbook.worksheets]}")
        logger.info(f"📁 Facturas procesadas: {len(facturas)}")
        
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
            error_sheet.append([f'Archivos únicos: {len(set(d.get("archivo_origen", "") for d in processed_data_list))}'])
            
            error_output = BytesIO()
            error_workbook.save(error_output)
            error_output.seek(0)
            return error_output.getvalue()
        except Exception as fallback_error:
            logger.error(f"❌ Error incluso en fallback: {fallback_error}")
            return None