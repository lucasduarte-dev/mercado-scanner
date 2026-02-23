"""
Script para recalcular scan_count de escaneos existentes

Este script actualiza el campo scan_count de todos los escaneos existentes
basándose en el orden cronológico de los escaneos del mismo shipment_id.
"""

import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mercado_scanner.settings')
django.setup()

from scanner.models import Scan
from django.db.models import Count

def recalculate_scan_counts():
    """Recalcula el scan_count para todos los shipments con múltiples escaneos"""
    print("Recalculando scan_count para escaneos existentes...\n")
    
    # Obtener todos los shipment_ids con múltiples escaneos
    shipments_with_multiple = Scan.objects.values('shipment_id').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    total_updated = 0
    
    for item in shipments_with_multiple:
        shipment_id = item['shipment_id']
        
        # Obtener todos los escaneos de este shipment ordenados cronológicamente
        scans = Scan.objects.filter(shipment_id=shipment_id).order_by('scanned_at')
        
        # Actualizar scan_count según el orden
        for index, scan in enumerate(scans, start=1):
            if scan.scan_count != index:
                scan.scan_count = index
                scan.save(update_fields=['scan_count'])
                total_updated += 1
                print(f"  ✓ {shipment_id} - Scan ID {scan.id} -> scan_count = {index}")
    
    print(f"\n✓ Total de registros actualizados: {total_updated}")
    
    # Mostrar resumen
    print("\n=== Resumen ===")
    count_by_scan = {}
    for i in range(1, 6):
        count = Scan.objects.filter(scan_count=i).count()
        if count > 0:
            count_by_scan[i] = count
            print(f"Escaneo #{i}: {count} registros")

if __name__ == '__main__':
    print("=" * 60)
    print("Recálculo de scan_count")
    print("=" * 60 + "\n")
    
    recalculate_scan_counts()
    
    print("\n" + "=" * 60)
    print("✓ Proceso completado")
    print("=" * 60)
