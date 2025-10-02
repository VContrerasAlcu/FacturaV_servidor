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

# excel_generator.py - Función generate_excel corregida
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

        # 1. AGRUPAR POR EMPRESA con manejo de valores None
        empresas = {}
        elementos_sin_empresa = []
        
        for data in processed_data_list:
            # ✅ MANEJAR VALORES None EN VendorName
            empresa_nombre = data.get('VendorName')
            archivo_origen = data.get('archivo_origen', 'Desconocido')
            
            # ✅ SI NO HAY NOMBRE DE EMPRESA, USAR UN VALOR POR DEFECTO
            if not empresa_nombre:
                empresa_nombre = f"Empresa_No_Identificada_{hash(archivo_origen) % 10000:04d}"
                logger.warning(f"⚠️ Factura sin nombre de empresa: {archivo_origen}. Usando: {empresa_nombre}")
                elementos_sin_empresa.append(archivo_origen)
            
            if empresa_nombre not in empresas:
                empresas[empresa_nombre] = []
            
            # Agregar el archivo de origen a los datos para referencia
            data['archivo_origen'] = archivo_origen
            empresas[empresa_nombre].append(data)
        
        logger.info(f"🏢 Empresas detectadas: {len(empresas)}")
        if elementos_sin_empresa:
            logger.info(f"   ⚠️ Facturas sin empresa identificada: {len(elementos_sin_empresa)}")
        
        for empresa, datos in empresas.items():
            logger.info(f"   📋 {empresa}: {len(datos)} facturas")

        # 2. GENERAR UN EXCEL POR EMPRESA
        archivos_empresas = []
        
        for empresa_nombre, facturas_empresa in empresas.items():
            logger.info(f"📊 Generando Excel para: {empresa_nombre}")
            
            # ✅ VALIDAR QUE HAY DATOS VÁLIDOS
            if not facturas_empresa or len(facturas_empresa) == 0:
                logger.warning(f"⚠️ Saltando empresa {empresa_nombre}: sin facturas válidas")
                continue
            
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
                logger.info(f"✅ Excel generado para {empresa_nombre}")
            else:
                logger.error(f"❌ Error generando Excel para {empresa_nombre}")
        
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
            
            # ✅ AGREGAR INFORMACIÓN DE DEBUG
            if processed_data_list:
                error_sheet.append([''])
                error_sheet.append(['Datos recibidos:'])
                for i, data in enumerate(processed_data_list):
                    vendor_name = data.get('VendorName', 'No identificado')
                    archivo = data.get('archivo_origen', 'Desconocido')
                    error_sheet.append([f'Elemento {i+1}: {vendor_name} - {archivo}'])
            
            error_output = BytesIO()
            error_workbook.save(error_output)
            error_output.seek(0)
            
            return [{
                'empresa': 'Error_Procesamiento',
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
        
        # ✅ VALIDAR EMPRESA_NAME
        if not empresa_nombre or empresa_nombre == 'None':
            empresa_nombre = "Empresa No Identificada"
            logger.warning(f"⚠️ Usando nombre por defecto para empresa: {empresa_nombre}")
        
        # Crear una hoja por cada factura de esta empresa
        for i, factura_data in enumerate(facturas_empresa):
            archivo_origen = factura_data.get('archivo_origen', f'Factura_{i+1}')
            
            # ✅ NOMBRE DE HOJA SEGURO (evitar caracteres inválidos)
            sheet_name = f"Factura_{i+1}"
            try:
                # Intentar usar nombre del archivo si es válido
                safe_name = "".join(c for c in archivo_origen if c.isalnum() or c in (' ', '-', '_'))
                if safe_name and len(safe_name) <= 31:
                    sheet_name = safe_name
            except:
                pass  # Usar nombre por defecto si hay error
            
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1
            
            # 1. Información de la empresa
            worksheet.append(['INFORMACIÓN DE LA EMPRESA'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet[f'A{current_row}'].font = header_font
            worksheet[f'A{current_row}'].fill = header_fill
            current_row += 1
            
            # ✅ DATOS CON VALORES POR DEFECTO
            vendor_name = factura_data.get('VendorName', 'No identificado')
            vendor_tax_id = factura_data.get('VendorTaxId', 'No disponible')
            vendor_address = factura_data.get('VendorAddress', 'No disponible')
            
            worksheet.append(['Empresa:', vendor_name])
            worksheet.append(['CIF/NIF:', vendor_tax_id])
            worksheet.append(['Dirección:', vendor_address])
            current_row += 3
            
            # 2. Información específica de esta factura
            worksheet.append(['INFORMACIÓN DE LA FACTURA'])
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            worksheet[f'A{current_row}'].font = header_font
            worksheet[f'A{current_row}'].fill = header_fill
            current_row += 1
            
            worksheet.append(['Archivo origen:', archivo_origen])
            
            # ✅ INFORMACIÓN DE FACTURA CON VALORES POR DEFECTO
            invoice_id = factura_data.get('InvoiceId', 'Sin número')
            invoice_date = factura_data.get('InvoiceDate', 'No especificada')
            invoice_total = factura_data.get('InvoiceTotal', 0)
            
            worksheet.append(['Número Factura:', invoice_id])
            
            # Formatear fecha
            try:
                if invoice_date and invoice_date != 'No especificada' and isinstance(invoice_date, str):
                    if 'T' in invoice_date:  # Formato ISO
                        invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                        invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
            except (ValueError, AttributeError):
                pass  # Mantener fecha original si hay error
            
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
            if items:
                for item in items:
                    # ✅ VALORES POR DEFECTO PARA ITEMS
                    description = item.get('Description', 'Sin descripción')
                    quantity = item.get('Quantity', 0)
                    unit_price = item.get('UnitPrice', 0)
                    amount = item.get('Amount', 0)
                    
                    worksheet.append([
                        description,
                        quantity,
                        unit_price,
                        amount
                    ])
                    current_row += 1
            else:
                worksheet.append(['No se encontraron artículos en esta factura', '', '', ''])
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
            if tax_details:
                for tax in tax_details:
                    # ✅ VALORES POR DEFECTO PARA IMPUESTOS
                    rate = tax.get('Rate', '0%')
                    amount = tax.get('Amount', 0)
                    
                    worksheet.append([
                        rate,
                        amount,
                        '', ''
                    ])
                    current_row += 1
            else:
                worksheet.append(['No se encontraron impuestos', '', '', ''])
                current_row += 1
            
            # 5. Total de esta factura
            worksheet.append(['TOTAL FACTURA:', invoice_total, '', ''])
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
        
        # Lista de facturas procesadas
        resumen_sheet.append(['FACTURAS PROCESADAS:'])
        resumen_sheet.merge_cells('A4:B4')
        resumen_sheet['A4'].font = header_font
        resumen_sheet['A4'].fill = header_fill
        
        resumen_sheet.append(['Número Factura', 'Fecha', 'Total'])
        for col in range(1, 4):
            resumen_sheet.cell(row=5, column=col).font = header_font
            resumen_sheet.cell(row=5, column=col).fill = header_fill
        
        row_num = 6
        for factura in facturas_empresa:
            invoice_id = factura.get('InvoiceId', 'Sin número')
            invoice_date = factura.get('InvoiceDate', 'No especificada')
            invoice_total = factura.get('InvoiceTotal', 0)
            
            # Formatear fecha para resumen
            try:
                if invoice_date and invoice_date != 'No especificada' and isinstance(invoice_date, str):
                    if 'T' in invoice_date:
                        invoice_date_obj = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
                        invoice_date = invoice_date_obj.strftime('%d/%m/%Y')
            except:
                pass
            
            resumen_sheet.append([invoice_id, invoice_date, invoice_total])
            row_num += 1
        
        row_num += 1
        
        # Detalle de IVA
        resumen_sheet.append(['DETALLE DE IVA POR TIPO'])
        resumen_sheet.merge_cells(f'A{row_num}:B{row_num}')
        resumen_sheet[f'A{row_num}'].font = header_font
        resumen_sheet[f'A{row_num}'].fill = header_fill
        row_num += 1
        
        resumen_sheet.append(['Tipo de IVA', 'Total Importe'])
        for col in range(1, 3):
            resumen_sheet.cell(row=row_num, column=col).font = header_font
            resumen_sheet.cell(row=row_num, column=col).fill = header_fill
        row_num += 1
        
        total_general = 0
        if resumen_iva:
            for tipo_iva, importe in resumen_iva.items():
                resumen_sheet.append([tipo_iva, importe])
                total_general += importe
                row_num += 1
        else:
            resumen_sheet.append(['No se encontraron datos de IVA', 0])
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
        resumen_sheet.column_dimensions['C'].width = 15
        
        # Guardar en memoria
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        logger.info(f"✅ Excel generado para {empresa_nombre} con {len(facturas_empresa)} facturas")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel para {empresa_nombre}: {e}")
        
        # ✅ FALLBACK: Crear Excel simple con información básica
        try:
            fallback_workbook = Workbook()
            fallback_sheet = fallback_workbook.active
            fallback_sheet.title = "Resumen"
            
            fallback_sheet.append(['RESUMEN DE FACTURAS - ' + empresa_nombre])
            fallback_sheet.append([f'Error durante generación: {str(e)}'])
            fallback_sheet.append([''])
            fallback_sheet.append(['Facturas procesadas:', len(facturas_empresa)])
            fallback_sheet.append([''])
            
            # Información básica de cada factura
            for i, factura in enumerate(facturas_empresa):
                fallback_sheet.append([
                    f'Factura {i+1}:',
                    factura.get('InvoiceId', 'Sin número'),
                    factura.get('VendorName', 'No identificado'),
                    factura.get('InvoiceTotal', 0)
                ])
            
            fallback_output = BytesIO()
            fallback_workbook.save(fallback_output)
            fallback_output.seek(0)
            
            logger.info(f"✅ Fallback Excel generado para {empresa_nombre}")
            return fallback_output.getvalue()
            
        except Exception as fallback_error:
            logger.error(f"❌ Error incluso en fallback: {fallback_error}")
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