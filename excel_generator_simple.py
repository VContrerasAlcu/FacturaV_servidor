# excel_generator_simple.py - VERSIÓN MEJORADA CON ARTÍCULOS Y RESUMEN
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# FUNCIÓN AUXILIAR PARA CONVERSIÓN SEGURA DE NÚMEROS
def safe_float_convert(value, default=0):
    """
    Convierte seguro un valor a float, manejando strings con símbolos de moneda
    """
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        # Limpiar string: remover €, $, espacios y convertir , a .
        cleaned = value.replace('€', '').replace('$', '').replace(' ', '').replace(',', '.').strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return default
    
    return default

def calcular_resumen_iva_completo(facturas_empresa):
    """Calcula resumen completo de IVA por tipo CON MANEJO DE TIPOS SEGURO"""
    resumen_iva = {}
    
    for factura in facturas_empresa:
        tax_details = factura.get('TaxDetails', [])
        for tax in tax_details:
            tipo_iva = tax.get('Rate', '0%')
            importe = tax.get('Amount', 0)
            
            # ✅ CONVERTIR importe a float de forma segura
            importe_float = safe_float_convert(importe, 0)
            
            if tipo_iva not in resumen_iva:
                resumen_iva[tipo_iva] = 0
            resumen_iva[tipo_iva] += importe_float
    
    return resumen_iva

def generar_excel_completo_con_articulos(empresa_nombre, facturas_empresa):
    """
    Genera Excel COMPLETO con: 
    - Una hoja por factura (con artículos detallados)
    - Hoja de resumen general
    - Hoja de resumen de artículos
    """
    try:
        workbook = Workbook()
        
        # Eliminar hoja por defecto
        if workbook.sheetnames:
            workbook.remove(workbook.active)
        
        # Estilos mejorados
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        section_font = Font(bold=True, size=11, color="2E74B5")
        normal_font = Font(size=10) 
        total_font = Font(bold=True, size=12, color="2E74B5")
        warning_font = Font(color="FF0000", italic=True)
        success_font = Font(color="00B050", italic=True)
        
        thin_border = Border(
            left=Side(style='thin'), 
            right=Side(style='thin'), 
            top=Side(style='thin'), 
            bottom=Side(style='thin')
        )
        
        money_format = '#,##0.00€'
        date_format = 'dd/mm/yyyy'
        
        # ✅ VALIDAR Y LIMPIAR NOMBRE DE EMPRESA
        if not empresa_nombre or empresa_nombre == 'None':
            empresa_nombre = "Empresa No Identificada"
        
        # CONTADORES PARA ESTADÍSTICAS
        total_facturas = len(facturas_empresa)
        facturas_con_articulos = 0
        total_articulos = 0
        
        # ✅ 1. HOJAS INDIVIDUALES POR FACTURA (CON ARTÍCULOS)
        for factura_idx, factura in enumerate(facturas_empresa):
            archivo_origen = factura.get('archivo_origen', f'Factura_{factura_idx + 1}')
            
            # Nombre seguro para la hoja
            sheet_name = f"Factura_{factura_idx + 1}"
            try:
                safe_name = "".join(c for c in archivo_origen if c.isalnum() or c in (' ', '-', '_'))
                if safe_name and len(safe_name) <= 28:
                    sheet_name = f"{safe_name}_{factura_idx + 1}"
            except:
                sheet_name = f"Factura_{factura_idx + 1}"
            
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1

            # TITULO DE LA FACTURA
            title_cell = worksheet.cell(row=current_row, column=1, 
                                      value=f'FACTURA {factura_idx + 1} - {empresa_nombre}')
            worksheet.merge_cells(f'A{current_row}:G{current_row}')
            title_cell.font = Font(bold=True, size=14, color="2E74B5")
            title_cell.alignment = Alignment(horizontal='center')
            current_row += 2

            # INFORMACION DEL VENDEDOR
            vendor_header = worksheet.cell(row=current_row, column=1, value='INFORMACIÓN DEL VENDEDOR')
            worksheet.merge_cells(f'A{current_row}:G{current_row}')
            vendor_header.font = header_font
            vendor_header.fill = header_fill
            vendor_header.alignment = Alignment(horizontal='center')
            current_row += 1

            worksheet.append(['Empresa:', factura.get('VendorName', 'No identificado'), '', '', '', '', ''])
            worksheet.append(['CIF/NIF:', factura.get('VendorTaxId', 'No disponible'), '', '', '', '', ''])
            worksheet.append(['Dirección:', factura.get('VendorAddress', 'No disponible'), '', '', '', '', ''])
            current_row += 4

            # INFORMACION DE LA FACTURA
            invoice_header = worksheet.cell(row=current_row, column=1, value='INFORMACIÓN DE LA FACTURA')
            worksheet.merge_cells(f'A{current_row}:G{current_row}')
            invoice_header.font = header_font
            invoice_header.fill = header_fill
            invoice_header.alignment = Alignment(horizontal='center')
            current_row += 1

            worksheet.append(['Número Factura:', factura.get('InvoiceId', 'Sin número'), '', '', '', '', ''])
            worksheet.append(['Fecha Factura:', formatear_fecha(factura.get('InvoiceDate')), '', '', '', '', ''])
            worksheet.append(['Archivo Origen:', archivo_origen, '', '', '', '', ''])
            current_row += 3
            
            # ✅ NUEVO: TABLA DE ARTÍCULOS DETALLADOS
            items = factura.get('Items', [])
            if items:
                facturas_con_articulos += 1
                total_articulos += len(items)
                
                items_header = worksheet.cell(row=current_row, column=1, value='ARTÍCULOS DETALLADOS')
                worksheet.merge_cells(f'A{current_row}:G{current_row}')
                items_header.font = header_font
                items_header.fill = header_fill
                items_header.alignment = Alignment(horizontal='center')
                current_row += 1

                # Encabezados tabla artículos
                headers = ['Descripción', 'Cantidad', 'Precio Unitario', 'Importe', 'IVA', 'Total con IVA']
                worksheet.append(headers)
                
                # Estilo encabezados
                for col in range(1, 7):
                    cell = worksheet.cell(row=current_row, column=col)
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center')
                current_row += 1

                subtotal_articulos = 0
                iva_total_articulos = 0
                
                for item in items:
                    description = item.get('Description', 'Sin descripción')
                    quantity = safe_float_convert(item.get('Quantity', 0))
                    unit_price = safe_float_convert(item.get('UnitPrice', 0))
                    amount = safe_float_convert(item.get('Amount', 0))
                    
                    # Calcular amount si no está presente
                    if amount == 0 and quantity != 0 and unit_price != 0:
                        amount = quantity * unit_price
                    
                    # Calcular IVA para este artículo (asumir 21% si no hay info)
                    iva_rate = 0.21  # IVA por defecto
                    iva_amount = amount * iva_rate
                    total_con_iva = amount + iva_amount
                    
                    subtotal_articulos += amount
                    iva_total_articulos += iva_amount
                    
                    worksheet.append([
                        description,
                        quantity,
                        unit_price,
                        amount,
                        iva_amount,
                        total_con_iva
                    ])
                    
                    # Aplicar bordes y formato
                    for col in range(1, 7):
                        cell = worksheet.cell(row=current_row, column=col)
                        cell.border = thin_border
                        cell.font = normal_font
                        
                        # Formato numérico
                        if col in [2]:  # Cantidad
                            cell.number_format = '0.##'
                        elif col in [3, 4, 5, 6]:  # Columnas de precios
                            cell.number_format = money_format
                    
                    current_row += 1
                
                # SUBTOTAL ARTÍCULOS
                current_row += 1
                worksheet.append(['SUBTOTAL ARTÍCULOS:', '', '', subtotal_articulos, '', ''])
                worksheet.merge_cells(f'A{current_row}:C{current_row}')
                subtotal_cell = worksheet.cell(row=current_row, column=4)
                subtotal_cell.font = Font(bold=True)
                subtotal_cell.number_format = money_format
                
                # IVA ARTÍCULOS
                current_row += 1
                worksheet.append(['IVA ARTÍCULOS (21%):', '', '', iva_total_articulos, '', ''])
                worksheet.merge_cells(f'A{current_row}:C{current_row}')
                iva_cell = worksheet.cell(row=current_row, column=4)
                iva_cell.font = Font(bold=True)
                iva_cell.number_format = money_format
                
                # TOTAL ARTÍCULOS
                current_row += 1
                total_articulos_calculado = subtotal_articulos + iva_total_articulos
                worksheet.append(['TOTAL ARTÍCULOS:', '', '', total_articulos_calculado, '', ''])
                worksheet.merge_cells(f'A{current_row}:C{current_row}')
                total_cell = worksheet.cell(row=current_row, column=4)
                total_cell.font = total_font
                total_cell.number_format = money_format
                
                current_row += 2
            else:
                # NO HAY ARTÍCULOS
                current_row += 1
                worksheet.append(['No se encontraron artículos en esta factura', '', '', '', '', ''])
                worksheet.merge_cells(f'A{current_row}:F{current_row}')
                for col in range(1, 7):
                    worksheet.cell(row=current_row, column=col).border = thin_border
                current_row += 2

            # DETALLE DE IMPUESTOS
            taxes_header = worksheet.cell(row=current_row, column=1, value='DETALLE DE IMPUESTOS')
            worksheet.merge_cells(f'A{current_row}:G{current_row}')
            taxes_header.font = header_font
            taxes_header.fill = header_fill
            taxes_header.alignment = Alignment(horizontal='center')
            current_row += 1

            worksheet.append(['Tipo de IVA', 'Importe', '', '', '', '', ''])
            for col in range(1, 3):
                cell = worksheet.cell(row=current_row, column=col)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center')
            current_row += 1

            tax_details = factura.get('TaxDetails', [])
            total_impuestos = 0
            
            if tax_details:
                for tax in tax_details:
                    rate = tax.get('Rate', '0%')
                    amount = safe_float_convert(tax.get('Amount', 0))
                    
                    total_impuestos += amount
                    
                    worksheet.append([
                        rate,
                        amount,
                        '', '', '', '', ''
                    ])
                    
                    # Aplicar bordes y formato
                    for col in range(1, 3):
                        cell = worksheet.cell(row=current_row, column=col)
                        cell.border = thin_border
                        cell.font = normal_font
                        if col == 2:  # Columna de importe
                            cell.number_format = money_format
                    
                    current_row += 1
            else:
                worksheet.append(['No se encontraron impuestos', '', '', '', '', '', ''])
                for col in range(1, 3):
                    worksheet.cell(row=current_row, column=col).border = thin_border
                current_row += 1

            # TOTAL FINAL DE LA FACTURA
            current_row += 1
            invoice_total = safe_float_convert(factura.get('InvoiceTotal', 0))
            
            worksheet.append(['TOTAL FACTURA:', '', '', invoice_total, '', '', ''])
            worksheet.merge_cells(f'A{current_row}:C{current_row}')
            total_label_cell = worksheet.cell(row=current_row, column=1)
            total_value_cell = worksheet.cell(row=current_row, column=4)
            
            total_label_cell.font = total_font
            total_value_cell.font = total_font
            total_value_cell.number_format = money_format
            
            # Resaltar celda de total
            for col in range(1, 8):
                cell = worksheet.cell(row=current_row, column=col)
                cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                cell.border = thin_border

            # AJUSTAR ANCHOS DE COLUMNAS
            column_widths = [45, 12, 15, 15, 15, 15, 15]
            for col_idx, width in enumerate(column_widths, 1):
                column_letter = chr(64 + col_idx)
                worksheet.column_dimensions[column_letter].width = width
            
            # CONGELAR PANELES
            worksheet.freeze_panes = 'A2'
        
        # ✅ 2. HOJA DE RESUMEN GENERAL MEJORADA
        resumen_sheet = workbook.create_sheet(title="📊 RESUMEN GENERAL")
        current_row = 1
        
        # TÍTULO PRINCIPAL
        title_cell = resumen_sheet.cell(row=current_row, column=1, 
                                      value=f'RESUMEN GENERAL - {empresa_nombre.upper()}')
        resumen_sheet.merge_cells(f'A{current_row}:H{current_row}')
        title_cell.font = Font(bold=True, size=16, color="2E74B5")
        title_cell.alignment = Alignment(horizontal='center')
        current_row += 2
        
        # ESTADÍSTICAS RÁPIDAS
        resumen_sheet.append(['ESTADÍSTICAS DE PROCESAMIENTO:', '', '', '', '', '', '', ''])
        resumen_sheet.merge_cells(f'A{current_row}:H{current_row}')
        resumen_sheet.cell(row=current_row, column=1).font = header_font
        resumen_sheet.cell(row=current_row, column=1).fill = header_fill
        current_row += 1
        
        total_importe = sum(safe_float_convert(f.get('InvoiceTotal', 0)) for f in facturas_empresa)
        total_articulos_general = sum(len(f.get('Items', [])) for f in facturas_empresa)
        
        resumen_sheet.append(['Total de facturas procesadas:', total_facturas, '', '', '', '', '', ''])
        resumen_sheet.append(['Facturas con artículos:', facturas_con_articulos, '', '', '', '', '', ''])
        resumen_sheet.append(['Total de artículos:', total_articulos_general, '', '', '', '', '', ''])
        resumen_sheet.append(['Importe total:', total_importe, '', '', '', '', '', ''])
        
        current_row += 5
        
        # LISTA DETALLADA DE FACTURAS
        resumen_sheet.append(['LISTA DETALLADA DE FACTURAS:', '', '', '', '', '', '', ''])
        resumen_sheet.merge_cells(f'A{current_row}:H{current_row}')
        resumen_sheet.cell(row=current_row, column=1).font = header_font
        resumen_sheet.cell(row=current_row, column=1).fill = header_fill
        current_row += 1
        
        resumen_sheet.append(['Número Factura', 'Fecha', 'Artículos', 'Subtotal', 'Total IVA', 'TOTAL', 'Archivo', 'Estado'])
        for col in range(1, 9):
            resumen_sheet.cell(row=current_row, column=col).font = Font(bold=True)
            resumen_sheet.cell(row=current_row, column=col).fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        current_row += 1
        
        for factura in facturas_empresa:
            invoice_id = factura.get('InvoiceId', 'Sin número')
            invoice_date = formatear_fecha(factura.get('InvoiceDate'))
            items_count = len(factura.get('Items', []))
            invoice_total = safe_float_convert(factura.get('InvoiceTotal', 0))
            archivo_origen = factura.get('archivo_origen', 'Desconocido')
            
            # Calcular subtotal e IVA
            tax_details = factura.get('TaxDetails', [])
            total_iva = sum(safe_float_convert(tax.get('Amount', 0)) for tax in tax_details)
            subtotal = invoice_total - total_iva
            
            # Estado basado en artículos
            estado = '✅ Con artículos' if items_count > 0 else '⚠️ Sin artículos'
            
            resumen_sheet.append([
                invoice_id,
                invoice_date,
                items_count,
                subtotal,
                total_iva,
                invoice_total,
                archivo_origen,
                estado
            ])
            
            # Formato de la fila
            for col in range(1, 9):
                cell = resumen_sheet.cell(row=current_row, column=col)
                cell.border = thin_border
                
                # Formato numerico
                if col in [4, 5, 6]:
                    cell.number_format = money_format
                    cell.alignment = Alignment(horizontal='right')
                elif col == 3:  # Cantidad artículos
                    cell.alignment = Alignment(horizontal='center')
            
            current_row += 1
        
        # ✅ 3. NUEVA HOJA: RESUMEN DE ARTÍCULOS
        articulos_sheet = workbook.create_sheet(title="📦 RESUMEN ARTÍCULOS")
        current_row = 1
        
        # TÍTULO
        title_cell = articulos_sheet.cell(row=current_row, column=1, 
                                        value=f'RESUMEN DE ARTÍCULOS - {empresa_nombre.upper()}')
        articulos_sheet.merge_cells(f'A{current_row}:G{current_row}')
        title_cell.font = Font(bold=True, size=16, color="2E74B5")
        title_cell.alignment = Alignment(horizontal='center')
        current_row += 2
        
        # RECOPILAR TODOS LOS ARTÍCULOS
        todos_articulos = []
        for factura in facturas_empresa:
            items = factura.get('Items', [])
            for item in items:
                item['factura_origen'] = factura.get('InvoiceId', 'Sin número')
                item['fecha_factura'] = factura.get('InvoiceDate')
                todos_articulos.append(item)
        
        if todos_articulos:
            articulos_sheet.append(['LISTA COMPLETA DE ARTÍCULOS:', '', '', '', '', '', ''])
            articulos_sheet.merge_cells(f'A{current_row}:G{current_row}')
            articulos_sheet.cell(row=current_row, column=1).font = header_font
            articulos_sheet.cell(row=current_row, column=1).fill = header_fill
            current_row += 1
            
            headers = ['Factura', 'Fecha', 'Descripción', 'Cantidad', 'Precio Unitario', 'Importe', 'IVA Aplicado']
            articulos_sheet.append(headers)
            
            for col in range(1, 8):
                cell = articulos_sheet.cell(row=current_row, column=col)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="5B9BD5", end_color="5B9BD5", fill_type="solid")
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center')
            current_row += 1
            
            total_general_articulos = 0
            for articulo in todos_articulos:
                descripcion = articulo.get('Description', 'Sin descripción')
                cantidad = safe_float_convert(articulo.get('Quantity', 0))
                precio_unitario = safe_float_convert(articulo.get('UnitPrice', 0))
                importe = safe_float_convert(articulo.get('Amount', 0))
                factura_origen = articulo.get('factura_origen', 'Sin número')
                fecha = formatear_fecha(articulo.get('fecha_factura'))
                
                # Calcular IVA (21% por defecto)
                iva_aplicado = importe * 0.21
                
                total_general_articulos += importe
                
                articulos_sheet.append([
                    factura_origen,
                    fecha,
                    descripcion,
                    cantidad,
                    precio_unitario,
                    importe,
                    iva_aplicado
                ])
                
                # Formato
                for col in range(1, 8):
                    cell = articulos_sheet.cell(row=current_row, column=col)
                    cell.border = thin_border
                    if col in [4, 5, 6, 7]:  # Columnas numéricas
                        if col == 4:  # Cantidad
                            cell.number_format = '0.##'
                        else:  # Precios
                            cell.number_format = money_format
                
                current_row += 1
            
            # TOTAL GENERAL ARTÍCULOS
            current_row += 1
            articulos_sheet.append(['TOTAL GENERAL ARTÍCULOS:', '', '', '', '', total_general_articulos, ''])
            articulos_sheet.merge_cells(f'A{current_row}:E{current_row}')
            for col in range(1, 8):
                cell = articulos_sheet.cell(row=current_row, column=col)
                cell.font = total_font
                cell.border = thin_border
                if col == 6:
                    cell.number_format = money_format
        else:
            articulos_sheet.append(['No se encontraron artículos en las facturas procesadas', '', '', '', '', '', ''])
            articulos_sheet.merge_cells(f'A{current_row}:G{current_row}')
        
        # AJUSTAR ANCHOS EN HOJAS DE RESUMEN
        resumen_widths = [20, 12, 12, 15, 15, 15, 25, 15]
        for col_idx, width in enumerate(resumen_widths, 1):
            col_letter = chr(64 + col_idx)
            resumen_sheet.column_dimensions[col_letter].width = width
            articulos_sheet.column_dimensions[col_letter].width = width
        
        # CONGELAR PANELES
        resumen_sheet.freeze_panes = 'A3'
        articulos_sheet.freeze_panes = 'A3'
        
        # Guardar en memoria
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        logger.info(f"✅ Excel COMPLETO generado para {empresa_nombre}: {total_facturas} facturas, {total_articulos_general} artículos")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel completo para {empresa_nombre}: {e}")
        return None

def generate_simplified_excel(processed_data_list):
    """
    Genera Excel simplificado CON ARTÍCULOS Y RESUMEN
    """
    try:
        logger.info(f"📊 Generando Excel COMPLETO para {len(processed_data_list)} elementos")
        
        if not processed_data_list:
            logger.error("❌ No hay datos para generar Excel")
            return []

        # Agrupar por empresa
        empresas = {}
        
        for data in processed_data_list:
            empresa_nombre = data.get('VendorName', 'Empresa No Identificada')
            
            if not empresa_nombre or empresa_nombre == 'None':
                empresa_nombre = "Empresa No Identificada"
            
            if empresa_nombre not in empresas:
                empresas[empresa_nombre] = []
            
            empresas[empresa_nombre].append(data)
        
        logger.info(f"🏢 Empresas detectadas: {len(empresas)}")
        
        # Generar Excel por empresa
        archivos_empresas = []
        
        for empresa_nombre, facturas_empresa in empresas.items():
            logger.info(f"📋 Generando Excel COMPLETO para: {empresa_nombre} ({len(facturas_empresa)} facturas)")
            
            excel_data = generar_excel_completo_con_articulos(empresa_nombre, facturas_empresa)
            
            if excel_data:
                # Calcular estadísticas
                total_facturas = len(facturas_empresa)
                total_importe = sum(safe_float_convert(f.get('InvoiceTotal', 0)) for f in facturas_empresa)
                total_articulos = sum(len(f.get('Items', [])) for f in facturas_empresa)
                resumen_iva = calcular_resumen_iva_completo(facturas_empresa)
                
                archivos_empresas.append({
                    'empresa': empresa_nombre,
                    'archivo': excel_data,
                    'cantidad_facturas': total_facturas,
                    'total_importe': total_importe,
                    'total_articulos': total_articulos,
                    'resumen_iva': resumen_iva
                })
        
        logger.info(f"✅ Generados {len(archivos_empresas)} archivos Excel COMPLETOS")
        return archivos_empresas
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel completo: {e}")
        return []

def formatear_fecha(fecha):
    """Formatea fecha para Excel"""
    if not fecha:
        return 'No especificada'
    
    try:
        if isinstance(fecha, str):
            if 'T' in fecha:
                fecha_obj = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                return fecha_obj.strftime('%d/%m/%Y')
            elif '-' in fecha:
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
                return fecha_obj.strftime('%d/%m/%Y')
        return str(fecha)
    except:
        return str(fecha)