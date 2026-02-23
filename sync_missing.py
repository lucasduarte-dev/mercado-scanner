#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mercado_scanner.settings")
django.setup()

from scanner.sheets_logger import GoogleSheetsLogger
from scanner.models import Scan
from django.utils import timezone

today = timezone.now().date()
missing_ids = ['163293', '46489291548']

print(f'Sincronizando {len(missing_ids)} registros faltantes a Sheets...\n')

for shipment_id in missing_ids:
    # Obtener Scan del BD
    scans = Scan.objects.filter(shipment_id=shipment_id, scanned_at__date=today).order_by('-scanned_at')
    
    if not scans:
        print(f'❌ {shipment_id}: No encontrado en BD')
        continue
    
    scan = scans[0]
    print(f'📝 {shipment_id}: Sincronizando...')
    print(f'   - Status: {scan.status}')
    print(f'   - Tipo: {scan.logistics_type}')
    
    # Verificar si debe ir a Pendientes
    if scan.current_status and 'DEVOLUCION' in scan.current_status:
        print(f'   → Ir a "Pendientes de devolución" hoja')
        try:
            GoogleSheetsLogger.log_to_pending_returns(scan)
            print(f'   ✅ Guardado en Pendientes')
        except Exception as e:
            print(f'   ❌ Error: {e}')
    else:
        print(f'   → Ir a hoja principal')
        try:
            GoogleSheetsLogger.log_scan(scan)
            print(f'   ✅ Guardado en Sheets')
        except Exception as e:
            print(f'   ❌ Error: {e}')
    print()

print('✅ Sincronización completada')
