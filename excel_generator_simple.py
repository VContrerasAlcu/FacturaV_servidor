# excel_generator_simple.py - VERSIÓN CORREGIDA
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_simplified_excel(processed_data_list):
    """
    Genera Excel simplificado SOLO con campos esenciales - VERSIÓN CORREGIDA
    """
    try:
        logger.info(f"📊 Generando Excel simplificado para {len(processed_data_list)} elementos")
        
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
            logger.info(f"📋 Generando Excel para: {empresa_nombre} ({len(facturas_empresa)} facturas)")
            
            excel_data = generar_excel_empresa_simplificado(empresa_nombre, facturas_empresa)
            
            if excel_data:
                # Calcular resumen
                total_facturas = len(facturas_empresa)
                total_importe = sum(convertir_a_float(f.get('InvoiceTotal', 0)) for f in facturas_empresa)
                resumen_iva = calcular_resumen_iva_completo(facturas_empresa)
                
                archivos_empresas.append({
                    'empresa': empresa_nombre,
                    'archivo': excel_data,
                    'cantidad_facturas': total_facturas,
                    'total_importe': total_importe,
                    'resumen_iva': resumen_iva
                })
        
        logger.info(f"✅ Generados {len(archivos_empresas)} archivos Excel simplificados")
        return archivos_empresas
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel simplificado: {e}")
        return []

def convertir_a_float(valor):
    """Convierte cualquier valor a float de forma segura"""
    try:
        if valor is None:
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        if isinstance(valor, str):
            # Limpiar string: quitar puntos de miles, comas decimales, símbolos de moneda
            valor_limpio = valor.replace('.', '').replace(',', '.').replace('€', '').replace('$', '').strip()
            return float(valor_limpio) if valor_limpio else 0.0
        return float(valor)
    except (ValueError, TypeError):
        return 0.0

# En excel_generator_simple.py - MEJORAR ESCRITURA DE IMPUESTOS

def generar_excel_empresa_simplificado(empresa_nombre, facturas_empresa):
    """
    Genera Excel con UNA HOJA POR FACTURA + HOJA RESUMEN - MEJORADO
    """
    try:
        workbook = Workbook()
        
        # Eliminar hoja por defecto
        if workbook.sheetnames:
            workbook.remove(workbook.active)
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        section_font = Font(bold=True, size=11, color="2E74B5")
        normal_font = Font(size=10) 
        total_font = Font(bold=True, size=12, color="2E74B5")
        warning_font = Font(color="FF0000", italic=True)
        
        thin_border = Border(
            left=Side(style='thin'), 
            right=Side(style='thin'), 
            top=Side(style='thin'), 
            bottom=Side(style='thin')
        )
        
        # CREAR UNA HOJA POR CADA FACTURA
        for factura_idx, factura in enumerate(facturas_empresa):
            sheet_name = f"Factura_{factura_idx + 1}"
            if len(sheet_name) > 31:  # Limite Excel
                sheet_name = f"F_{factura_idx + 1}"
            
            worksheet = workbook.create_sheet(title=sheet_name)
            current_row = 1
            
            # TITULO DE LA FACTURA
            title_cell = worksheet.cell(row=current_row, column=1, 
                                      value=f'FACTURA {factura_idx + 1} - {empresa_nombre}')
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            title_cell.font = Font(bold=True, size=14, color="2E74B5")
            title_cell.alignment = Alignment(horizontal='center')
            current_row += 2
            
            # INFORMACION DEL VENDEDOR
            vendor_header = worksheet.cell(row=current_row, column=1, value='INFORMACION DEL VENDEDOR')
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            vendor_header.font = header_font
            vendor_header.fill = header_fill
            vendor_header.alignment = Alignment(horizontal='center')
            current_row += 1
            
            worksheet.append(['Empresa:', factura.get('VendorName', 'No identificado'), '', ''])
            worksheet.append(['CIF/NIF:', factura.get('VendorTaxId', 'No disponible'), '', ''])
            worksheet.append(['Direccion:', factura.get('VendorAddress', 'No disponible'), '', ''])
            current_row += 4
            
            # INFORMACION DE LA FACTURA
            invoice_header = worksheet.cell(row=current_row, column=1, value='INFORMACION DE LA FACTURA')
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            invoice_header.font = header_font
            invoice_header.fill = header_fill
            invoice_header.alignment = Alignment(horizontal='center')
            current_row += 1
            
            worksheet.append(['Numero Factura:', factura.get('InvoiceId', 'Sin numero'), '', ''])
            worksheet.append(['Fecha Factura:', formatear_fecha(factura.get('InvoiceDate')), '', ''])
            worksheet.append(['Archivo Origen:', factura.get('archivo_origen', 'Desconocido'), '', ''])
            current_row += 3
            
            # DETALLE DE IMPUESTOS - SECCIÓN MEJORADA
            taxes_header = worksheet.cell(row=current_row, column=1, value='DETALLE DE IMPUESTOS')
            worksheet.merge_cells(f'A{current_row}:D{current_row}')
            taxes_header.font = header_font
            taxes_header.fill = header_fill
            taxes_header.alignment = Alignment(horizontal='center')
            current_row += 1
            
            # Encabezados tabla impuestos
            worksheet.append(['Tipo de IVA', 'Tasa', 'Importe', 'Notas'])
            for col in range(1, 5):
                cell = worksheet.cell(row=current_row, column=col)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                cell.border = thin_border
            current_row += 1
            
            tax_details = factura.get('TaxDetails', [])
            total_impuestos = 0.0
            
            if tax_details:
                for tax in tax_details:
                    rate = tax.get('Rate', 'No especificado')
                    amount = convertir_a_float(tax.get('Amount', 0))
                    total_impuestos += amount
                    
                    # Determinar notas según el tipo de tasa
                    notas = ""
                    if 'calculado' in str(rate).lower() or 'inferido' in str(rate).lower():
                        notas = "Calculado automáticamente"
                    elif rate == 'IVA':
                        notas = "Detectado como IVA"
                    
                    worksheet.append([
                        rate,
                        rate if '%' in str(rate) else 'IVA',
                        amount,
                        notas
                    ])
                    
                    # Aplicar bordes y formato a la fila
                    for col in range(1, 5):
                        cell = worksheet.cell(row=current_row, column=col)
                        cell.border = thin_border
                        cell.font = normal_font
                        if col == 3:  # Columna importe
                            cell.number_format = '#,##0.00€'
                        if col == 4 and notas:  # Columna notas
                            cell.font = warning_font
                    
                    current_row += 1
            else:
                # SI NO HAY IMPUESTOS DETECTADOS, MOSTRAR MENSAJE
                worksheet.append(['No se detectaron impuestos', '', '', 'Verificar factura original'])
                for col in range(1, 5):
                    cell = worksheet.cell(row=current_row, column=col)
                    cell.border = thin_border
                    cell.font = warning_font
                current_row += 1
                
                # INTENTAR CALCULAR IMPUESTOS SI ES POSIBLE
                invoice_total = convertir_a_float(factura.get('InvoiceTotal', 0))
                subtotal = convertir_a_float(factura.get('SubTotal', 0))
                
                if invoice_total > 0 and subtotal > 0 and invoice_total != subtotal:
                    calculated_tax = invoice_total - subtotal
                    if calculated_tax > 0:
                        tax_rate = (calculated_tax / subtotal) * 100
                        worksheet.append([
                            f"IVA Calculado {tax_rate:.1f}%",
                            f"{tax_rate:.1f}%",
                            calculated_tax,
                            "Calculado a partir de Total - SubTotal"
                        ])
                        total_impuestos = calculated_tax
                        for col in range(1, 5):
                            cell = worksheet.cell(row=current_row, column=col)
                            cell.border = thin_border
                            cell.font = warning_font
                            if col == 3:
                                cell.number_format = '#,##0.00€'
                        current_row += 1
            
            # TOTALES
            current_row += 1
            invoice_total = convertir_a_float(factura.get('InvoiceTotal', 0))
            subtotal = invoice_total - total_impuestos
            
            worksheet.append(['SUBTOTAL (sin impuestos):', '', subtotal, ''])
            worksheet.append(['TOTAL IMPUESTOS:', '', total_impuestos, ''])
            worksheet.append(['TOTAL FACTURA:', '', invoice_total, ''])
            
            # Formato totales
            for row_offset in range(3):
                for col in range(1, 4):
                    cell = worksheet.cell(row=current_row + row_offset, column=col)
                    cell.border = thin_border
                    if col == 3:  # Columna importe
                        cell.number_format = '#,##0.00€'
                        if row_offset == 2:  # Fila de total
                            cell.font = total_font
            
            current_row += 4
            
            # INFORMACIÓN ADICIONAL DE PROCESAMIENTO
            if factura.get('confidence_level') == 'low' or factura.get('procesamiento') == 'fallback_basico':
                info_cell = worksheet.cell(row=current_row, column=1, 
                                         value='ℹ️ INFORMACIÓN: Esta factura fue procesada con datos limitados. Verificar con el documento original.')
                worksheet.merge_cells(f'A{current_row}:D{current_row}')
                info_cell.font = warning_font
                info_cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            
            # Ajustar anchos de columnas
            worksheet.column_dimensions['A'].width = 25
            worksheet.column_dimensions['B'].width = 20
            worksheet.column_dimensions['C'].width = 15
            worksheet.column_dimensions['D'].width = 25
            
            # Congelar paneles
            worksheet.freeze_panes = 'A2'
        
     
        
        # Guardar en memoria
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        logger.info(f"✅ Excel simplificado generado para {empresa_nombre}")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error generando Excel para {empresa_nombre}: {e}")
        return None

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

def calcular_resumen_iva_completo(facturas_empresa):
    """Calcula resumen completo de IVA por tipo"""
    resumen_iva = {}
    
    for factura in facturas_empresa:
        tax_details = factura.get('TaxDetails', [])
        for tax in tax_details:
            tipo_iva = tax.get('Rate', '0%')
            importe = convertir_a_float(tax.get('Amount', 0))
            
            if tipo_iva not in resumen_iva:
                resumen_iva[tipo_iva] = 0
            resumen_iva[tipo_iva] += importe
    
    return resumen_iva