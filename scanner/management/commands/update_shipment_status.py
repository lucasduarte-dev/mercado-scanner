"""
Management command para actualizar estados de envíos y limpiar registros antiguos
Ejecutar diariamente a las 23:00 con Windows Task Scheduler
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from scanner.models import Scan
from scanner.ml_api import MercadoLibreAPI
from scanner.sheets_logger import GoogleSheetsLogger
import gspread


class Command(BaseCommand):
    help = 'Actualiza estados actuales de envíos en BD y Sheets, y limpia registros antiguos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=30,
            help='Días de antigüedad para eliminar registros (default: 30)'
        )
        parser.add_argument(
            '--skip-cleanup',
            action='store_true',
            help='Omitir la limpieza de registros antiguos'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[INICIO] Actualizando estados de envíos...'))
        
        # Verificar la hora actual
        now = timezone.now()
        current_hour = now.hour
        current_minute = now.minute
        current_time = f'{current_hour:02d}:{current_minute:02d}'
        
        # Solo registrar en Pendientes si es después de 14:30
        should_register_pending = (current_hour > 14) or (current_hour == 14 and current_minute >= 30)
        
        if not should_register_pending:
            self.stdout.write(self.style.WARNING(f'⏰ Hora actual: {current_time} (antes de 14:30)'))
            self.stdout.write(self.style.WARNING('   → No se registrará en Pendientes de devolución esta ejecución'))
        else:
            self.stdout.write(self.style.SUCCESS(f'⏰ Hora actual: {current_time} (después de 14:30)'))
            self.stdout.write(self.style.SUCCESS('   → Se registrará en Pendientes de devolución si hay cambios'))
        
        # Obtener envíos desde Google Sheets
        self.stdout.write('Obteniendo envíos desde Google Sheets...')
        sheet_rows = GoogleSheetsLogger.get_all_shipments()
        total_rows = len(sheet_rows)
        
        if total_rows == 0:
            self.stdout.write(self.style.WARNING('No se encontraron envíos en Sheets para actualizar'))
            return
            
        self.stdout.write(f'Encontrados {total_rows} filas en Sheets')
        
        # Inicializar API
        ml_api = MercadoLibreAPI()
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        # Actualizar cada fila
        for i, row in enumerate(sheet_rows, 1):
            row_num = row['row_num']
            shipment_id = row['shipment_id']
            current_status = row['current_status']
            
            # Omitir si no hay ID válido para consultar
            if not shipment_id or shipment_id == 'N/A':
                skipped_count += 1
                continue
                
            try:
                self.stdout.write(f'[{i}/{total_rows}] Fila {row_num} (ID: {shipment_id})...', ending='')
                
                # Consultar API - Usamos shipment_id para encontrar la cuenta correcta
                # La API hace "fuerza bruta" entre cuentas si no le pasamos sender_id
                api_result = ml_api.get_full_shipment_info(shipment_id)
                
                if api_result.get('shipment'):
                    # Priorizar estado del PEDIDO/VENTA
                    new_status_raw = None
                    if api_result.get('order'):
                        new_status_raw = api_result['order'].get('status')
                        # self.stdout.write(f" [Order: {new_status_raw}]", ending='')
                    
                    # Fallback al estado del envío si no hay order
                    if not new_status_raw:
                        new_status_raw = api_result['shipment'].get('status')
                        # self.stdout.write(f" [Ship: {new_status_raw}]", ending='')


                    # Normalizar estado para comparación (VIGENTE / CANCELADO / DEVOLUCION)
                    # El formatter ahora detecta automáticamente devoluciones post-entrega
                    new_status_formatted = GoogleSheetsLogger._format_status(
                        new_status_raw,
                        order_data=api_result.get('order'),
                        shipment_data=api_result.get('shipment')
                    )
                    
                    # Comparar con estado actual en Sheets
                    # El estado actual en Sheets ya debería estar en formato "VIGENTE"/"CANCELADO"
                    # pero a veces puede ser texto crudo si se editó manual
                    
                    if new_status_formatted != current_status:
                        # Actualizar en Sheets con resaltado
                        if GoogleSheetsLogger.update_row_status(row_num, new_status_raw, highlight=True):
                            updated_count += 1
                            self.stdout.write(self.style.SUCCESS(f' ACTUALIZADO: {current_status} -> {new_status_formatted} ({new_status_raw})'))
                            
                            # DETECTAR: Si pasa de VIGENTE a CANCELADO, registrar en Pendientes (solo después de 14:30)
                            if should_register_pending and current_status == 'VIGENTE' and new_status_formatted == 'CANCELADO':
                                try:
                                    # Verificar si ya existe en Pendientes
                                    pending_sheet = GoogleSheetsLogger._get_pending_returns_sheet()
                                    existing = None
                                    if pending_sheet:
                                        try:
                                            existing = pending_sheet.find(shipment_id, in_column=6)  # Columna F (6) = ID ENVIO
                                        except gspread.CellNotFound:
                                            existing = None
                                    
                                    if existing:
                                        self.stdout.write(self.style.WARNING(f'  → Ya existe en Pendientes (fila {existing.row})'))
                                    else:
                                        scan_obj_tmp = Scan.objects.filter(shipment_id=shipment_id).latest('scanned_at')
                                        GoogleSheetsLogger.log_to_pending_returns(scan_obj_tmp)
                                        self.stdout.write(self.style.WARNING(f'  → Registrado en Pendientes de devolución: {shipment_id}'))
                                except Exception as e:
                                    self.stdout.write(self.style.WARNING(f'  [WARN] No se pudo registrar en Pendientes: {e}'))
                            elif not should_register_pending and current_status == 'VIGENTE' and new_status_formatted == 'CANCELADO':
                                self.stdout.write(self.style.WARNING(f'  ⏰ Cambio a CANCELADO detectado pero es antes de 14:30 - No se registra en Pendientes'))
                            
                            # BUG FIX #4: También actualizar en BD para mantener sincronización
                            try:
                                # Buscar el scan en BD por shipment_id
                                scan_obj = Scan.objects.filter(shipment_id=shipment_id).latest('scanned_at')
                                
                                # Actualizar current_status
                                scan_obj.current_status = new_status_raw
                                
                                # Actualizar is_cancelled basado en el nuevo estado formateado
                                if new_status_formatted == 'CANCELADO':
                                    scan_obj.is_cancelled = True
                                elif new_status_formatted == 'DEVOLUCION':
                                    scan_obj.is_cancelled = False
                                    # Asegurar que current_status tenga keyword 'returned'
                                    if 'returned' not in str(new_status_raw).lower():
                                        scan_obj.current_status = 'returned'
                                else:  # VIGENTE u otros
                                    scan_obj.is_cancelled = False
                                
                                # Actualizar timestamp de última verificación
                                scan_obj.last_status_check = timezone.now()
                                scan_obj.save()
                                
                            except Scan.DoesNotExist:
                                # No está en BD (tal vez es Premier o fue eliminado)
                                pass
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f' [WARN] No se pudo actualizar BD: {e}'))
                        else:
                            self.stdout.write(self.style.ERROR(' ERROR al escribir en Sheets'))
                    else:
                        skipped_count += 1
                        self.stdout.write(f' Sin cambios ({current_status})')
                        
                else:
                    # No encontrado en ML (Posiblemente Premier o Error)
                    skipped_count += 1
                    errors = '; '.join(api_result.get('errors', []))
                    if 'No encontrado' in errors or 'Envío no encontrado' in errors:
                        self.stdout.write(f' No encontrado en ML (¿Premier?)')
                    else:
                        error_count += 1
                        self.stdout.write(self.style.WARNING(f' API Error: {errors}'))
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f' EXCEPTION: {e}'))
        
        # Resumen de actualización
        self.stdout.write(self.style.SUCCESS(f'\n[RESUMEN ACTUALIZACIÓN]'))
        self.stdout.write(f'  Total Filas: {total_rows}')
        self.stdout.write(f'  Actualizados: {updated_count}')
        self.stdout.write(f'  Omitidos/Sin Cambios: {skipped_count}')
        self.stdout.write(f'  Errores: {error_count}')
        
        # Limpieza de registros antiguos
        if not options['skip_cleanup']:
            self.stdout.write(self.style.SUCCESS(f'\n[INICIO] Limpiando registros antiguos...'))
            cleanup_days = options['cleanup_days']
            
            try:
                result = GoogleSheetsLogger.cleanup_old_records(days=cleanup_days)
                if result:
                    self.stdout.write(self.style.SUCCESS(f'Limpieza completada exitosamente'))
                else:
                    self.stdout.write(self.style.WARNING(f'Limpieza completada con advertencias'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error durante limpieza: {e}'))
        else:
            self.stdout.write(self.style.WARNING('\n[SKIP] Limpieza de registros omitida'))
        
        self.stdout.write(self.style.SUCCESS('\n[FIN] Proceso completado'))
