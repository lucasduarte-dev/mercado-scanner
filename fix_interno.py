"""
Script para corregir filas INTERNO en Google Sheets y la base de datos.
Consulta la API de ML para cada shipment_id y actualiza los datos correctos.
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mercado_scanner.settings')
django.setup()

from scanner.ml_api import MercadoLibreAPI
from scanner.sheets_logger import GoogleSheetsLogger
from scanner.models import Scan

# IDs de envíos que quedaron como INTERNO
INTERNO_IDS = [
    '46562944485',
    '46569466425',
    '46566045833',
    '46566374835',
    '46568180517',
    '46566525846',
]
SENDER_ID = '481950707'

api = MercadoLibreAPI()
sheet = GoogleSheetsLogger._get_sheet()

if not sheet:
    print("ERROR: No se pudo acceder a Google Sheets")
    exit(1)

all_rows = sheet.get_all_values()
print(f"Total filas en Sheets: {len(all_rows)}")

for shipment_id in INTERNO_IDS:
    print(f"\n{'='*60}")
    print(f"Procesando: {shipment_id}")

    # 1. Buscar la fila en Sheets (contiene el JSON crudo como ID)
    row_num = None
    for i, row in enumerate(all_rows):
        # La columna G (índice 6) tiene el raw shipment_id
        if len(row) > 6 and shipment_id in str(row[6]):
            row_num = i + 1  # +1 porque Sheets es 1-indexed
            print(f"  Fila encontrada en Sheets: {row_num}")
            break
        # También buscar en columna B (índice 1) que tiene el JSON completo
        if len(row) > 1 and shipment_id in str(row[1]):
            row_num = i + 1
            print(f"  Fila encontrada en Sheets (col B): {row_num}")
            break

    if not row_num:
        print(f"  WARN: No se encontró en Sheets. Saltando.")
        continue

    # 2. Consultar API de ML
    result = api.get_full_shipment_info(shipment_id, SENDER_ID)
    shipment_data = result.get('shipment')
    order_data = result.get('order')

    if not shipment_data:
        print(f"  ERROR: API no devolvió datos: {result.get('errors')}")
        continue

    # 3. Calcular valores correctos
    order_id = shipment_data.get('order_id', '')
    logistic_type = shipment_data.get('logistic_type', '')
    tipo_envio = 'FLEX' if logistic_type == 'self_service' else 'MENSAJERIA'

    order_status = order_data.get('status') if order_data else None
    shipment_status = shipment_data.get('status')
    current_status_raw = order_status or shipment_status
    estado = GoogleSheetsLogger._format_status(
        current_status_raw,
        order_data=order_data,
        shipment_data=shipment_data
    )
    if estado == 'DEVOLUCION':
        estado = 'VIGENTE'

    # Dirección
    addr = shipment_data.get('receiver_address', {})
    street = f"{addr.get('street_name', '')} {addr.get('street_number', '')}".strip()
    city = addr.get('city', {}).get('name', '') if isinstance(addr.get('city'), dict) else ''
    direccion = f"{street} - {city}".strip(' -')

    # Link
    url_link = f'=HYPERLINK("https://www.mercadolibre.com.ar/venta/{order_id}", "Ver venta")' if order_id else ''
    order_id_col = f"'{order_id}" if order_id else 'N/A'

    print(f"  order_id={order_id} | estado={estado} | tipo={tipo_envio}")
    print(f"  direccion={direccion}")

    # 4. Actualizar Sheets (columnas B a I)
    try:
        sheet.update(
            range_name=f'B{row_num}',
            values=[[order_id_col, estado, estado, all_rows[row_num-1][4],
                     str(shipment_id), direccion, tipo_envio, url_link]],
            value_input_option='USER_ENTERED'
        )
        print(f"  OK: Sheets actualizada")
    except Exception as e:
        print(f"  ERROR Sheets: {e}")

    # 5. Actualizar base de datos
    try:
        scan = Scan.objects.filter(shipment_id=shipment_id).latest('scanned_at')
        scan.is_logistics = False
        scan.logistics_type = None
        scan.order_id = str(order_id) if order_id else scan.order_id
        scan.shipment_status = shipment_status
        scan.current_status = current_status_raw
        scan.initial_status = current_status_raw
        scan.shipping_mode = 'flex' if logistic_type == 'self_service' else 'me2'
        scan.api_response = result
        scan.is_cancelled = (estado == 'CANCELADO')
        scan.save()
        print(f"  OK: BD actualizada")
    except Scan.DoesNotExist:
        print(f"  WARN: No se encontró en BD")
    except Exception as e:
        print(f"  ERROR BD: {e}")

print(f"\n{'='*60}")
print("Proceso completado.")
