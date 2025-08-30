import pandas as pd
from io import BytesIO

def generate_excel(processed_data):
    try:
        # Crear DataFrame con los datos procesados
        df = pd.DataFrame(processed_data)
        
        # Crear archivo Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Facturas', index=False)
        
        # Obtener bytes del archivo
        excel_data = output.getvalue()
        return excel_data
        
    except Exception as e:
        print(f"Error generando Excel: {e}")
        raise