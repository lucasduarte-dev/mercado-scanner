"""
Management command para sincronizar escaneos de BD a Google Sheets.
Útil cuando los escaneos se guardaron en BD pero no en Sheets
(por ejemplo, si faltaban dependencias de Google en esa PC).

Automáticamente detecta cuáles ya están en Sheets y solo sube los faltantes.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from scanner.models import Scan
import time


class Command(BaseCommand):
    help = 'Sincroniza escaneos faltantes de BD a Google Sheets (solo los que no están)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Fecha en formato YYYY-MM-DD (default: hoy)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se sincronizaría, sin escribir',
        )

    def handle(self, *args, **options):
        from scanner.sheets_logger import GoogleSheetsLogger

        # Determinar fecha
        if options.get('date'):
            from datetime import datetime
            target_date = datetime.strptime(options['date'], '%Y-%m-%d')
            target_date = timezone.make_aware(target_date)
        else:
            target_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        next_day = target_date + timedelta(days=1)
        date_str = target_date.strftime('%d/%m/%Y')

        # Buscar escaneos exitosos del día en BD
        scans = Scan.objects.filter(
            scanned_at__gte=target_date,
            scanned_at__lt=next_day,
            status='success'
        ).order_by('scanned_at')

        total = scans.count()
        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(f'Sincronizando escaneos del {date_str}')
        self.stdout.write(f'Total en BD: {total}')

        if total == 0:
            self.stdout.write(self.style.WARNING('No hay escaneos para sincronizar'))
            return

        # Obtener los shipment_ids que ya están en Sheets
        self.stdout.write('Leyendo Sheets para detectar duplicados...')
        try:
            existing_rows = GoogleSheetsLogger.get_all_shipments()
            existing_ids = set()
            for row in existing_rows:
                sid = row.get('shipment_id', '').strip()
                if sid:
                    existing_ids.add(sid)
            self.stdout.write(f'Total filas en Sheets: {len(existing_rows)}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error leyendo Sheets: {e}'))
            self.stdout.write(self.style.WARNING('Cancelando para evitar duplicados'))
            return

        # Filtrar los que faltan
        missing_scans = []
        already_count = 0
        for scan in scans:
            if scan.shipment_id in existing_ids:
                already_count += 1
            else:
                missing_scans.append(scan)

        self.stdout.write(f'Ya en Sheets: {already_count}')
        self.stdout.write(self.style.WARNING(f'Faltan sincronizar: {len(missing_scans)}'))
        self.stdout.write(f'{"="*50}\n')

        if not missing_scans:
            self.stdout.write(self.style.SUCCESS('✓ Todo sincronizado, no falta nada!'))
            return

        if options.get('dry_run'):
            self.stdout.write(self.style.WARNING('--- DRY RUN (no se escribe nada) ---\n'))
            for scan in missing_scans:
                tipo = scan.logistics_type if scan.is_logistics else scan.shipping_mode or 'ML'
                self.stdout.write(f'  [DRY] ID={scan.shipment_id} | {tipo} | {scan.scanner_user or "?"}')
            self.stdout.write(f'\nTotal que se sincronizarían: {len(missing_scans)}')
            return

        # Sincronizar los faltantes
        synced = 0
        errors = 0

        for scan in missing_scans:
            tipo = scan.logistics_type if scan.is_logistics else scan.shipping_mode or 'ML'
            label = f'ID={scan.shipment_id} | {tipo} | {scan.scanner_user or "?"}'

            try:
                if scan.is_logistics and scan.logistics_type == 'CAMBIO':
                    ok = GoogleSheetsLogger.log_to_pending_returns(scan)
                    dest = 'Pendientes'
                else:
                    ok = GoogleSheetsLogger.log_scan(scan)
                    dest = 'Principal'

                if ok is not False:
                    synced += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {label} → {dest}'))
                else:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f'  ✗ {label} → Error'))

                # Pausa para evitar rate limit de Google Sheets
                time.sleep(5)
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f'  ✗ {label} → {e}'))

        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(self.style.SUCCESS(
            f'Completado: {synced} sincronizados, {errors} errores'
        ))
        self.stdout.write(f'{"="*50}\n')
