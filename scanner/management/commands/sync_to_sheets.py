"""
Management command para sincronizar escaneos de BD a Google Sheets.
Útil cuando los escaneos se guardaron en BD pero no en Sheets
(por ejemplo, si faltaban dependencias de Google en esa PC).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from scanner.models import Scan


class Command(BaseCommand):
    help = 'Sincroniza escaneos de BD a Google Sheets (para los que no se subieron)'

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
        parser.add_argument(
            '--skip',
            type=int,
            default=0,
            help='Saltear los primeros N escaneos (ya sincronizados)',
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

        # Buscar escaneos exitosos del día
        scans = Scan.objects.filter(
            scanned_at__gte=target_date,
            scanned_at__lt=next_day,
            status='success'
        ).order_by('scanned_at')

        total = scans.count()
        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(f'Sincronizando escaneos del {date_str}')
        self.stdout.write(f'Total encontrados en BD: {total}')
        self.stdout.write(f'{"="*50}\n')

        if total == 0:
            self.stdout.write(self.style.WARNING('No hay escaneos para sincronizar'))
            return

        if options.get('dry_run'):
            self.stdout.write(self.style.WARNING('--- DRY RUN (no se escribe nada) ---\n'))

        synced = 0
        errors = 0

        skip_count = options.get('skip', 0)
        if skip_count > 0:
            self.stdout.write(self.style.WARNING(f'Salteando los primeros {skip_count} escaneos\n'))

        for idx, scan in enumerate(scans):
            tipo = scan.logistics_type if scan.is_logistics else scan.shipping_mode or 'ML'
            label = f'ID={scan.shipment_id} | {tipo} | {scan.scanner_user or "?"}'

            if idx < skip_count:
                self.stdout.write(f'  ⏭ {label} (salteado)')
                continue

            if options.get('dry_run'):
                self.stdout.write(f'  [DRY] {label}')
                synced += 1
                continue

            try:
                # Determinar si va a pendientes o a hoja principal
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
                
                # Pausa para evitar rate limit de Google Sheets (max 60 writes/min)
                import time
                time.sleep(5)
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f'  ✗ {label} → {e}'))

        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(self.style.SUCCESS(
            f'Completado: {synced} sincronizados, {errors} errores'
        ))
        self.stdout.write(f'{"="*50}\n')
