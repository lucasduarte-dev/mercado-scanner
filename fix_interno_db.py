"""
Script para corregir solo la base de datos local (sin tocar Sheets).
Correr en el servidor (otra PC) donde están los registros de BD.
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mercado_scanner.settings')
django.setup()

from scanner.ml_api import MercadoLibreAPI
from scanner.models import Scan

# IDs de envios que quedaron como INTERNO
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

for shipment_id in INTERNO_IDS:
    print(f"\n{'='*50}")
    print(f"Procesando: {shipment_id}")

    result = api.get_full_shipment_info(shipment_id, SENDER_ID)
    shipment_data = result.get('shipment')
    order_data = result.get('order')

    if not shipment_data:
        print(f"  ERROR API: {result.get('errors')}")
        continue

    order_id = shipment_data.get('order_id', '')
    logistic_type = shipment_data.get('logistic_type', '')
    shipment_status = shipment_data.get('status')
    order_status = order_data.get('status') if order_data else None
    current_status_raw = order_status or shipment_status

    print(f"  order_id={order_id} | status={current_status_raw} | logistic_type={logistic_type}")

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
        scan.is_cancelled = (current_status_raw == 'cancelled')
        scan.save()
        print(f"  OK: BD actualizada")
    except Scan.DoesNotExist:
        print(f"  WARN: No se encontro en BD")
    except Exception as e:
        print(f"  ERROR BD: {e}")

print(f"\n{'='*50}")
print("Proceso completado.")
