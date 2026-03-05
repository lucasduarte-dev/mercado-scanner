import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mercado_scanner.settings')
django.setup()

from scanner.ml_api import MercadoLibreAPI
api = MercadoLibreAPI()

test_ids = ['46569466425', '46566045833', '46566374835', '46568180517']
for sid in test_ids:
    result = api.get_full_shipment_info(sid, '481950707')
    shipment = result.get('shipment')
    order = result.get('order')
    if shipment:
        print(f"OK {sid}: shipment={shipment.get('status')} | order={order.get('status') if order else 'N/A'}")
    else:
        print(f"FALLO {sid}: {result.get('errors')}")
