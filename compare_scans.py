#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mercado_scanner.settings")
django.setup()

from scanner.sheets_logger import GoogleSheetsLogger
from scanner.models import Scan
from django.utils import timezone

today = timezone.now().date()
today_str = today.strftime('%Y-%m-%d')
print(f'Comparando registros de: {today_str}')

# BD
bd_scans = Scan.objects.filter(status='success', scanned_at__date=today)
bd_ids = set(s.shipment_id for s in bd_scans)
print(f'\nBD: {len(bd_ids)} shipment_ids únicos')

# Sheets (filtrar por fecha, usando el prefijo %Y-%m-%d)
all_rows = GoogleSheetsLogger.get_all_shipments()
today_rows = [r for r in all_rows if r.get('fecha', '').startswith(today_str)]
sheets_ids = set(r.get('shipment_id') for r in today_rows if r.get('shipment_id'))
print(f'Sheets: {len(sheets_ids)} shipment_ids únicos en {today_str}')

# Diferencia
missing_in_sheets = bd_ids - sheets_ids
extra_in_sheets = sheets_ids - bd_ids

if missing_in_sheets:
    print(f'\n❌ Faltantes en Sheets: {len(missing_in_sheets)}')
    for sid in sorted(missing_in_sheets):
        print(f'  - {sid}')
else:
    print('\n✅ Todos los BD están en Sheets')

if extra_in_sheets:
    print(f'\n⚠️  Extra en Sheets (no en BD): {len(extra_in_sheets)}')
    for sid in sorted(extra_in_sheets):
        print(f'  - {sid}')
