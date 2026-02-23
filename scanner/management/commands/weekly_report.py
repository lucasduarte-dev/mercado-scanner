"""
Management command para generar reporte semanal de envíos
Ejecutar cada lunes para ver estadísticas de la semana anterior"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
from scanner.models import Scan


class Command(BaseCommand):
    help = 'Genera reporte semanal de envíos (FLEX, CAMBIOS, PARTICULARES, CANCELADOS)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--week-offset',
            type=int,
            default=0,
            help='Semanas hacia atrás a reportar (0=semana pasada, 1=hace 2 semanas, etc.)'
        )

    def handle(self, *args, **options):
        week_offset = options['week_offset']
        
        # Calcular fecha de inicio y fin
        today = timezone.now().date()
        
        # Obtener el lunes de la semana
        # week_offset=0 significa la SEMANA ACTUAL (en curso)
        # week_offset=1 significa la SEMANA PASADA
        days_since_monday = today.weekday()  # 0=lunes, 6=domingo
        days_to_subtract = days_since_monday + (week_offset * 7)
        week_start = today - timedelta(days=days_to_subtract)
        week_end = week_start + timedelta(days=6)  # Domingo
        
        # Ajustar a datetime para queries
        week_start_dt = timezone.make_aware(timezone.datetime.combine(week_start, timezone.datetime.min.time()))
        week_end_dt = timezone.make_aware(timezone.datetime.combine(week_end, timezone.datetime.max.time()))
        
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS(f'  REPORTE SEMANAL: {week_start.strftime("%d/%m/%Y")} - {week_end.strftime("%d/%m/%Y")}'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        
        # Obtener datos de la hoja "Hoja 1" (Main dataset)
        from scanner.sheets_logger import GoogleSheetsLogger
        self.stdout.write('  Leyendo datos de Google Sheets (Hoja 1)...')
        
        sheet = GoogleSheetsLogger._get_sheet()
        if not sheet:
            self.stdout.write(self.style.ERROR('  [ERROR] No se pudo conectar a Google Sheets'))
            return

        all_rows = sheet.get_all_values()
        
        # Filtros y contadores
        # Índices (0-based): 
        # A=0 (FECHA), C=2 (ESTADO RETIRO), D=3 (ESTADO ACTUAL), H=7 (TIPO ENVIO)
        col_fecha = 0
        col_retiro = 2
        col_actual = 3
        col_tipo = 7
        
        flex_count = 0
        cambios_count = 0
        particulares_count = 0
        cancelados_count = 0
        cambios_cancelados = 0
        particulares_cancelados = 0
        
        daily_counts = {day: 0 for day in ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']}
        cancelados_list = [] # Para detalle
        
        # Iterar filas (saltando headers en filas 1-3)
        # Asumiendo que datos empiezan en fila 4 (indice 3)
        for row in all_rows[3:]:
            if not row or len(row) < 8: continue
            
            # 1. Filtrar por FECHA
            fecha_str = row[col_fecha]
            try:
                # Formato esperado: YYYY-MM-DD HH:MM:SS
                fecha_dt = datetime.strptime(fecha_str.split(' ')[0], '%Y-%m-%d')
                fecha_dt = timezone.make_aware(datetime.combine(fecha_dt.date(), datetime.min.time()))
                
                if not (week_start_dt <= fecha_dt <= week_end_dt):
                    continue
            except (ValueError, IndexError):
                continue
                
            # 2. Contar por DÍA
            # weekday(): 0=Lunes, 6=Domingo
            day_idx = fecha_dt.weekday()
            day_name = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][day_idx]
            daily_counts[day_name] += 1
            
            # 3. Categorizar
            tipo_envio = row[col_tipo].strip().upper()
            estado_retiro = row[col_retiro].strip().upper()
            estado_actual = row[col_actual].strip().upper()
            
            # FLEX
            if tipo_envio == 'FLEX':
                flex_count += 1
            
            # CAMBIOS (Solo si es MENSAJERIA y estado RETIRO es CAMBIO)
            if tipo_envio == 'MENSAJERIA' and 'CAMBIO' in estado_retiro:
                cambios_count += 1
                # Verificar si está cancelado
                if 'CANCELADO' in estado_actual:
                    cambios_cancelados += 1
            
            # PARTICULARES (Solo si es MENSAJERIA y estado RETIRO es PARTICULAR)
            if tipo_envio == 'MENSAJERIA' and 'PARTICULAR' in estado_retiro:
                particulares_count += 1
                # Verificar si está cancelado
                if 'CANCELADO' in estado_actual:
                    particulares_cancelados += 1
            
            
            # CANCELADOS TOTALES (Pre-entrega) - Excluir DEVOLUCIONES
            # BUG FIX #2: Usar comparación más robusta y excluir variantes de devolución
            estado_actual_upper = estado_actual.strip().upper()
            
            # Solo contar si es explícitamente CANCELADO y NO es devolución
            if 'CANCELADO' in estado_actual_upper:
                # Verificar que NO sea devolución (palabras clave)
                if not any(kw in estado_actual_upper for kw in ['DEVOLUCION', 'DEVOLUCIÓN', 'DEVOLVIENDO', 'RETURN']):
                    cancelados_count += 1
                    cancelados_list.append({
                        'id': row[5] if len(row) > 5 else 'N/A', # ID ENVIO
                        'order': row[1] if len(row) > 1 else 'N/A', # N VENTA
                        'cliente': row[6] if len(row) > 6 else 'N/A' # DIRECCION/CLIENTE
                    })



        a_devolver = cambios_cancelados + particulares_cancelados
        
        # Mostrar resultados
        self.stdout.write(self.style.HTTP_INFO('  [ENVIOS REALIZADOS]'))
        self.stdout.write('')
        self.stdout.write(f'     FLEX:         {flex_count:>4} envios')
        self.stdout.write(f'     CAMBIOS:      {cambios_count:>4} envios')
        self.stdout.write(f'     PARTICULARES: {particulares_count:>4} envios')
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('  [DESGLOSE POR DIA]'))
        self.stdout.write('')
        for day_name, count in daily_counts.items():
            self.stdout.write(f'     {day_name:>10}: {count:>4} escaneos')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('  [!] CANCELADOS (pre-entrega):'))
        self.stdout.write('')
        self.stdout.write(f'     Total:        {cancelados_count:>4} envios')
        self.stdout.write('')
        self.stdout.write(self.style.ERROR('  [<] A DEVOLVER:'))
        self.stdout.write('')
        self.stdout.write(f'     CAMBIOS:      {cambios_cancelados:>4} envios')
        self.stdout.write(f'     PARTICULARES: {particulares_cancelados:>4} envios')
        self.stdout.write(f'     ---------------------')
        self.stdout.write(self.style.ERROR(f'     TOTAL:        {a_devolver:>4} envios'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')

        
        # Detalle de cancelados (opcional)
        if cancelados_list:
            self.stdout.write(self.style.WARNING('  [DETALLE DE CANCELADOS]'))
            self.stdout.write('')
            for item in cancelados_list[:10]:  # Mostrar max 10
                self.stdout.write(f'     * {item["order"]} | {item["id"]} | {item["cliente"]}')
            
            if len(cancelados_list) > 10:
                self.stdout.write(f'     ... y {len(cancelados_list) - 10} más')
            self.stdout.write('')
        
        # Guardar reporte en Google Sheets
        self.stdout.write(self.style.HTTP_INFO('  Guardando reporte en Google Sheets...'))
        from scanner.sheets_logger import GoogleSheetsLogger
        
        if GoogleSheetsLogger.save_weekly_report(
            week_start,
            week_end,
            flex_count,
            cambios_count,
            particulares_count,
            cancelados_count,
            a_devolver,
            daily_counts
        ):
            self.stdout.write(self.style.SUCCESS('  [OK] Reporte guardado en Sheets'))
        else:
            self.stdout.write(self.style.WARNING('  [WARN] No se pudo guardar en Sheets'))
        
        self.stdout.write('')
