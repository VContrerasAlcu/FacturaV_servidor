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
    Genera MÚLTIPLES archivos Excel agrupados por empresa
    Devuelve una lista de diccionarios con {empresa: nombre, archivo: excel_data, resumen: datos}
    """
    try:
        logger.info(f"📊 INICIANDO GENERACIÓN DE EXCEL POR EMPRESA")
        logger.info(f"📦 Total de elementos recibidos: {len(processed_data_list)}")
        
        if not processed_data_list:
            logger.error("❌ No hay datos para generar Excel")
            return []

        # 1. AGRUPAR POR EMPRESA en lugar de por archivo
        empresas = {}
        for data in processed_data_list:
            empresa_nombre = data.get('VendorName', 'Empresa Desconocida')
            archivo_origen = data.get('archivo_origen', 'Desconocido')
            
            if empresa_nombre not in empresas:
                empresas[empresa_nombre] = []
            
            # Agregar el archivo de origen a los datos para referencia
            data['archivo_origen'] = archivo_origen
            empresas[empresa_nombre].append(data)
        
        logger.info(f"🏢 Empresas detectadas: {len(empresas)}")
        for empresa, datos in empresas.items():
            logger.info(f"   📋 {empresa}: {len(datos)} facturas")

        # 2. GENERAR UN EXCEL POR EMPRESA
        archivos_empresas = []
        
        for empresa_nombre, facturas_empresa in empresas.items():
            logger.info(f"📊 Generando Excel para: {empresa_nombre}")
            
            # Crear Excel para esta empresa
            excel_data = generar_excel_empresa(empresa_nombre, facturas_empresa)
            
            if excel_data:
                # Calcular resumen de IVA para esta empresa
                resumen_iva = calcular_resumen_iva_empresa(facturas_empresa)
                
                archivos_empresas.append({
                    'empresa': empresa_nombre,
                    'archivo': excel_data,
                    'cantidad_facturas': len(facturas_empresa),
                    'resumen_iva': resumen_iva
                })
        
        logger.info(f"✅ Generados {len(archivos_empresas)} archivos Excel")
        return archivos_empresas
        
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
            
            return [{
                'empresa': 'Error',
                'archivo': error_output.getvalue(),
                'cantidad_facturas': 0,
                'resumen_iva': {}
            }]
        except Exception as fallback_error:
            logger.error(f"❌ Error incluso en fallback: {fallback_error}")
            return []

def generar_excel_empresa(empresa_nombre, facturas_empresa):
    """
    Genera un archivo Excel para una empresa específica
    """
    try:
        workbook = Workbook()
        
        # Eliminar hoja por defecto
        if workbook.sheetnames:
            workbook.remove(workbook.active)
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        total_font = Font(bold=True, size=14)
        money_format = '#,##0.00€'
        
        # Crear una hoja por cada factura de esta empresa
        for i, factura_data in enumerate(facturas_empresa):
            archivo_origen = factura_data.get('archivo_origen', f'Factura_{i+1}')
            
            # Nombre de la hoja (limitar a 31 caracteres)
            sheet_name = f"Factura_{i+1}" if len(archivo_origen) > 31 else archivo_origen[:31]
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1
            
            # 1. Información de la empresa
            worksheet.append(['INFORMACIÓN DE LA EMPRESA'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet['A1'].font = header_font
            worksheet['A1'].fill = header_fill
            current_row += 1
            
            worksheet.append(['Empresa:', empresa_nombre])
            worksheet.append(['CIF/NIF:', factura_data.get('VendorTaxId', 'No especificado')])
            worksheet.append(['Dirección:', factura_data.get('VendorAddress', 'No especificado')])
            current_row += 3
            
            # 2. Información específica de esta factura
            worksheet.append(['INFORMACIÓN DE LA FACTURA'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet[f'A{current_row}'].font = header_font
            worksheet[f'A{current_row}'].fill = header_fill
            current_row += 1
            
            worksheet.append(['Archivo origen:', archivo_origen])
            worksheet.append(['Número Factura:', factura_data.get('InvoiceId', 'No especificado')])
            
            # Formatear fecha
            invoice_date = factura_data.get('InvoiceDate', 'No especificado')
            try:
                if invoice_date and invoice_date != 'No especificado' and isinstance(invoice_date, str):
                    invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                    invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
            except (ValueError, AttributeError):
                pass
            
            worksheet.append(['Fecha Factura:', invoice_date])
            current_row += 3
            
            # 3. Artículos de la factura
            worksheet.append(['ARTÍCULOS FACTURADOS'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet[f'A{current_row}'].font = header_font
            worksheet[f'A{current_row}'].fill = header_fill
            current_row += 1
            
            worksheet.append(['Artículo', 'Unidades', 'Precio Unitario', 'Precio Total'])
            for col in range(1, 5):
                worksheet.cell(row=current_row, column=col).font = header_font
                worksheet.cell(row=current_row, column=col).fill = header_fill
            current_row += 1
            
            items = factura_data.get('Items', [])
            for item in items:
                worksheet.append([
                    item.get('Description', ''),
                    item.get('Quantity', 0),
                    item.get('UnitPrice', 0),
                    item.get('Amount', 0)
                ])
                current_row += 1
            
            # 4. Totales de IVA de esta factura
            worksheet.append(['DETALLE DE IMPUESTOS'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet[f'A{current_row}'].font = header_font
            worksheet[f'A{current_row}'].fill = header_fill
            current_row += 1
            
            worksheet.append(['Tipo de IVA', 'Importe', '', ''])
            for col in range(1, 3):
                worksheet.cell(row=current_row, column=col).font = header_font
                worksheet.cell(row=current_row, column=col).fill = header_fill
            current_row += 1
            
            tax_details = factura_data.get('TaxDetails', [])
            for tax in tax_details:
                worksheet.append([
                    tax.get('Rate', '0%'),
                    tax.get('Amount', 0),
                    '', ''
                ])
                current_row += 1
            
            # 5. Total de esta factura
            worksheet.append(['TOTAL FACTURA:', factura_data.get('InvoiceTotal', 0), '', ''])
            total_cell = worksheet.cell(row=current_row, column=1)
            total_value_cell = worksheet.cell(row=current_row, column=2)
            total_cell.font = total_font
            total_value_cell.font = total_font
            total_value_cell.number_format = money_format
            
            # Ajustar anchos de columnas
            column_widths = [40, 15, 15, 15]
            for col_idx, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[chr(64 + col_idx)].width = width
            
            current_row += 2
        
        # 6. HOJA DE RESUMEN GENERAL DE LA EMPRESA
        resumen_sheet = workbook.create_sheet(title="RESUMEN EMPRESA")
        resumen_iva = calcular_resumen_iva_empresa(facturas_empresa)
        
        # Título
        resumen_sheet.append(['RESUMEN GENERAL - ' + empresa_nombre])
        resumen_sheet.merge_cells('A1:B1')
        resumen_sheet['A1'].font = Font(bold=True, size=16)
        resumen_sheet.append(['Total de facturas procesadas:', len(facturas_empresa)])
        resumen_sheet.append([])
        
        # Detalle de IVA
        resumen_sheet.append(['DETALLE DE IVA POR TIPO'])
        resumen_sheet.merge_cells('A4:B4')
        resumen_sheet['A4'].font = header_font
        resumen_sheet['A4'].fill = header_fill
        
        resumen_sheet.append(['Tipo de IVA', 'Total Importe'])
        for col in range(1, 3):
            resumen_sheet.cell(row=5, column=col).font = header_font
            resumen_sheet.cell(row=5, column=col).fill = header_fill
        
        row_num = 6
        total_general = 0
        for tipo_iva, importe in resumen_iva.items():
            resumen_sheet.append([tipo_iva, importe])
            total_general += importe
            row_num += 1
        
        # Total general
        resumen_sheet.append([])
        resumen_sheet.append(['TOTAL GENERAL EMPRESA:', total_general])
        resumen_sheet.cell(row=row_num + 2, column=1).font = total_font
        resumen_sheet.cell(row=row_num + 2, column=2).font = total_font
        resumen_sheet.cell(row=row_num + 2, column=2).number_format = money_format
        
        # Ajustar anchos
        resumen_sheet.column_dimensions['A'].width = 25
        resumen_sheet.column_dimensions['B'].width = 20
        
        # Guardar en memoria
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        logger.info(f"✅ Excel generado para {empresa_nombre} con {len(facturas_empresa)} facturas")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel para {empresa_nombre}: {e}")
        return None

def calcular_resumen_iva_empresa(facturas_empresa):
    """
    Calcula el total de IVA por tipo para todas las facturas de una empresa
    """
    resumen_iva = {}
    
    for factura in facturas_empresa:
        tax_details = factura.get('TaxDetails', [])
        for tax in tax_details:
            tipo_iva = tax.get('Rate', '0%')
            importe = tax.get('Amount', 0)
            
            if tipo_iva not in resumen_iva:
                resumen_iva[tipo_iva] = 0
            resumen_iva[tipo_iva] += importe
    
    logger.info(f"📊 Resumen IVA para empresa: {resumen_iva}")
    return resumen_iva

# Función de compatibilidad (por si otros partes del código esperan la función antigua)
def generate_single_excel(processed_data_list):
    """
    Función de compatibilidad - genera un solo Excel como antes
    """
    logger.warning("⚠️ Usando función de compatibilidad - genera un solo Excel")
    
    # Usar la lógica original simplificada
    try:
        workbook = Workbook()
        if workbook.sheetnames:
            workbook.remove(workbook.active)
        
        # Crear una hoja simple
        worksheet = workbook.create_sheet(title="Facturas Consolidadas")
        worksheet.append(['ADVERTENCIA: Este es un Excel de compatibilidad'])
        worksheet.append(['Se recomienda usar la nueva función generate_excel()'])
        worksheet.append(['Número de facturas procesadas:', len(processed_data_list)])
        
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        return output.getvalue()
    except Exception as e:
        logger.error(f"❌ Error en función de compatibilidad: {e}")
        return None