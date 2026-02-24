"""
Management command para pre-cargar envíos de Premier Mensajeria.
Ejecutar a las 13:30 y 13:40 con Windows Task Scheduler.
Scrape todos los envíos PARTICULAR/CAMBIO y los guarda en caché local
para que los escaneos sean instantáneos.
"""
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from scanner.models import PremierShipmentCache
from scanner.premier_api import PremierMensajeriaAPI

# Playwright usa event loop async internamente.
# Esto permite que Django haga queries sync dentro de ese contexto.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class Command(BaseCommand):
    help = 'Pre-carga envíos de Premier Mensajeria en caché local'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-old',
            action='store_true',
            help='No limpiar caché anterior del día',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            '=' * 50 + '\n'
            '[Premier PreFetch] Iniciando pre-carga de envíos...\n'
            + '=' * 50
        ))

        # PASO 1: Scrape (con Playwright - contexto async)
        api = PremierMensajeriaAPI()
        shipments = []
        try:
            api.start()
            if not api.login():
                self.stdout.write(self.style.ERROR('[Premier PreFetch] ✗ Login falló'))
                return

            self.stdout.write(self.style.SUCCESS('[Premier PreFetch] ✓ Login exitoso'))
            shipments = api.fetch_all_shipments()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[Premier PreFetch] ERROR en scrape: {e}'))
            import traceback
            traceback.print_exc()
            return
        finally:
            api.close()

        # PASO 2: Guardar en BD (ya sin Playwright activo)
        if not shipments:
            self.stdout.write(self.style.WARNING('[Premier PreFetch] No se encontraron envíos PARTICULAR/CAMBIO'))
            return

        try:
            # Limpiar caché anterior del día (a menos que --keep-old)
            if not options.get('keep_old'):
                today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                deleted_count, _ = PremierShipmentCache.objects.filter(
                    fetched_at__gte=today_start
                ).delete()
                if deleted_count > 0:
                    self.stdout.write(f'[Premier PreFetch] Limpiados {deleted_count} registros anteriores del día')

            # Guardar en caché
            created_count = 0
            particular_count = 0
            cambio_count = 0

            for shipment in shipments:
                PremierShipmentCache.objects.create(
                    did=shipment['did'],
                    customer_name=shipment.get('customer_name', ''),
                    tipo=shipment.get('tipo', ''),
                    raw_row_data=shipment,
                )
                created_count += 1
                if shipment.get('tipo') == 'PARTICULAR':
                    particular_count += 1
                elif shipment.get('tipo') == 'CAMBIO':
                    cambio_count += 1

            # Resumen
            self.stdout.write(self.style.SUCCESS(
                '\n' + '=' * 50 + '\n'
                f'[Premier PreFetch] ✓ COMPLETADO\n'
                f'  Total cargados: {created_count}\n'
                f'  PARTICULAR: {particular_count}\n'
                f'  CAMBIO: {cambio_count}\n'
                + '=' * 50
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[Premier PreFetch] ERROR guardando en BD: {e}'))
            import traceback
            traceback.print_exc()
