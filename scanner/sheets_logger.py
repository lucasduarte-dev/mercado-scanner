"""
Módulo para registrar escaneos en Google Sheets
Requiere: gspread y oauth2client
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from pathlib import Path
import time
from googleapiclient.discovery import build
import os
import json
from tempfile import NamedTemporaryFile


class GoogleSheetsLogger:
    SCOPE = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Intentar leer credenciales desde variable de entorno o archivo local
    CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS')
    CREDENTIALS_FILE = Path(__file__).parent.parent / "credentials.json"
    MAX_RETRIES = 3
    SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID', "1obCJ9BY2hzBFziImhn7qLe0TKIKk3hw7Kszc1OFG5Bs")
    
    # Nombre de las hojas
    MAIN_SHEET_NAME = "Mercado Envíos Scans"
    PENDING_RETURNS_SHEET_NAME = "Pendientes de devolución"
    WEEKLY_REPORTS_SHEET_NAME = "Reportes Semanales"
    
    # Encabezados de las columnas
    HEADERS = ["FECHA", "Nº VENTA/PEDIDO", "ESTADO DE RETIRO", "ESTADO ACTUAL", "QUIEN ESCANEO", "ID ENVIO", "DIRECCION/CLIENTE", "TIPO ENVIO", "URL"]
    PENDING_RETURNS_HEADERS = ["FECHA", "NRO VENTA/ORDEN", "ESTADO DE RETIRO", "ESTADO ACTUAL", "QUIEN ESCANEO", "ID ENVIO", "DIRECCION", "ESTADO CIERRE", "URL"]
    
    @classmethod
    def _format_status(cls, status, order_data=None, shipment_data=None):
        """Convierte estados técnicos a VIGENTE, CANCELADO o DEVOLUCION
        
        Args:
            status: El estado raw del order o shipment
            order_data: Dict con datos completos del order (opcional)
            shipment_data: Dict con datos completos del shipment (opcional)
        """
        if not status:
            return "DESCONOCIDO"
        
        status_lower = str(status).lower()
        
        # 1. Detectar devoluciones explícitas en shipment
        if shipment_data:
            ship_status = str(shipment_data.get('status', '')).lower()
            ship_substatus = str(shipment_data.get('substatus', '')).lower()
            if 'returned' in ship_status or 'returning' in ship_status or \
               'returned' in ship_substatus or 'returning' in ship_substatus:
                return "DEVOLUCION"
        
        # 2. Si el estado es 'cancelled', diferenciar entre cancelación y devolución
        if status_lower == 'cancelled':
            # Verificar si fue entregado antes de cancelar (= devolución post-entrega)
            if order_data:
                tags = order_data.get('tags', [])
                
                # Caso 1: Si tiene el tag 'delivered', es una devolución
                if 'delivered' in tags:
                    return "DEVOLUCION"
                
                # Caso 2: Si tiene tag 'not_delivered', es CANCELADO (no devolución)
                # BUG FIX: Incluso si el pago está refunded
                if 'not_delivered' in tags:
                    return "CANCELADO"
                
                # Caso 3: Si no tiene ni 'delivered' ni 'not_delivered', verificar pago refunded
                payments = order_data.get('payments', [])
                has_refunded = any(p.get('status') == 'refunded' for p in payments)
                
                if has_refunded:
                    # Verificación adicional con shipment
                    if shipment_data:
                        ship_sub = str(shipment_data.get('substatus', '')).lower()
                        if 'return' in ship_sub:
                            return "DEVOLUCION"
                    # Si no hay indicador de return en shipment, es CANCELADO
                    # (refund solo = dinero devuelto, no producto devuelto)
                    return "CANCELADO"
            
            # Si no fue entregado, es una cancelación pre-entrega
            return "CANCELADO"
        
        # 3. Detectar devoluciones en el status raw
        elif 'returned' in status_lower or 'returning' in status_lower:
            return "DEVOLUCION"
        
        # 4. Cualquier otro estado es VIGENTE
        else:
            return "VIGENTE"
    
    @classmethod
    def _get_sheet(cls):
        """Obtiene la conexión a la hoja de cálculo
        
        Intenta usar credenciales desde:
        1. Variable de entorno GOOGLE_CREDENTIALS (JSON string)
        2. Archivo local credentials.json
        """
        creds = None
        credentials_file = None
        
        # Intentar usar credenciales desde variable de entorno (Railway/Production)
        if cls.CREDENTIALS_JSON:
            try:
                creds_dict = json.loads(cls.CREDENTIALS_JSON)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, cls.SCOPE)
            except Exception as e:
                print(f"[WARN] Error al parsear GOOGLE_CREDENTIALS: {e}")
        
        # Fallback a archivo local si no hay variable de entorno
        if not creds and cls.CREDENTIALS_FILE.exists():
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(cls.CREDENTIALS_FILE, cls.SCOPE)
            except Exception as e:
                print(f"[ERROR] Error al leer credentials.json: {e}")
        
        if not creds:
            print(f"[ERROR] No se encontraron credenciales de Google")
            print(f"  - Variable GOOGLE_CREDENTIALS: {'Sí' if cls.CREDENTIALS_JSON else 'No'}")
            print(f"  - Archivo {cls.CREDENTIALS_FILE}: {'Sí' if cls.CREDENTIALS_FILE.exists() else 'No'}")
            return None
            
        try:
            client = gspread.authorize(creds)
            sheet = client.open_by_key(cls.SPREADSHEET_ID).sheet1
            return sheet
        except gspread.SpreadsheetNotFound:
            print(f"[ERROR] No se encontró la hoja con ID: {cls.SPREADSHEET_ID}")
            print("Asegúrate de haber compartido la hoja con: scanner-bot@ml-scanner-484416.iam.gserviceaccount.com")
            return None
    
    @classmethod
    def _ensure_headers(cls, sheet):
        """Asegura que los encabezados estén en la fila 3"""
        try:
            # Reservar filas 1-2 para estadísticas
            # Fila 1: Pedidos Hoy
            # Fila 2: Pedidos Esta Semana
            # Fila 3: Encabezados
            
            # Verificar si han cambiado los headers (ej. si agregamos columna)
            current_row_3 = sheet.row_values(3)
            
            # Si hay diferencia en longitud o contenido, actualizar
            if len(current_row_3) != len(cls.HEADERS) or current_row_3 != cls.HEADERS:
                # Actualizar encabezados
                # Calcular rango dinámicamente según len(HEADERS)
                last_col_idx = len(cls.HEADERS)
                last_col_char = chr(64 + last_col_idx) # A=1, B=2... H=8
                sheet.update(f'A3:{last_col_char}3', [cls.HEADERS])
                print("[OK] Encabezados actualizados con nueva estructura")
                
            # Actualizar fórmulas de estadísticas
            today = datetime.now().strftime('%Y-%m-%d')
            # Calcular inicio de semana (lunes)
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            
            # Fórmula para contar pedidos del día
            # SUMPRODUCT excluye filas donde ESTADO DE RETIRO (col C) sea CANCELADO
            sheet.update('A1', [[f'Pedidos Hoy: {today}']])
            sheet.update('B1', [[f'=SUMPRODUCT((LEFT(A4:A5000,10)="{today}")*(C4:C5000<>"CANCELADO")*(A4:A5000<>""))']], raw=False)
            
            # Fórmula para contar pedidos de la semana
            sheet.update('A2', [[f'Pedidos Esta Semana (desde {week_start}):']])
            sheet.update('B2', [[f'=SUMPRODUCT((LEFT(A4:A5000,10)>="{week_start}")*(C4:C5000<>"CANCELADO")*(A4:A5000<>""))']], raw=False)
            
            # print("[OK] Encabezados y estadísticas verificados")
        except Exception as e:
            print(f"[WARN] Error actualizando encabezados: {e}")
    
    @classmethod
    def log_scan(cls, scan_obj):
        """Registra un nuevo escaneo en la hoja de cálculo"""
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return False
            
            # Asegurar encabezados
            cls._ensure_headers(sheet)
            
            # Preparar datos
            # FECHA, Nº VENTA/PEDIDO, ESTADO DE RETIRO, ESTADO ACTUAL, QUIEN ESCANEO, ID ENVIO, DIRECCION, TIPO ENVIO
            from django.utils import timezone
            local_date = timezone.localtime(scan_obj.scanned_at)
            fecha = local_date.strftime('%Y-%m-%d %H:%M:%S')
            usuario = scan_obj.scanner_user or 'Desconocido'
            
            tipo_envio = "DESCONOCIDO"
            if scan_obj.shipping_mode == 'flex':
                tipo_envio = "FLEX"
            elif scan_obj.shipping_mode == 'me2':
                tipo_envio = "MERCADO ENVIOS"
            elif scan_obj.shipping_mode == 'mensajeria':
                tipo_envio = "MENSAJERIA"
            
            # Manejar escaneos de logística (Premier) vs Mercado Libre
            url_link = ''  # Inicializar URL vacía
            
            if scan_obj.is_logistics:
                # Premier Mensajeria
                # Usar IDs directos del modelo si existen
                did_val = scan_obj.shipment_id or scan_obj.logistics_data.get('did', 'N/A') if scan_obj.logistics_data else 'N/A'
                
                # Para logística, Order ID y Shipment ID suelen ser el mismo (DID)
                raw_id = scan_obj.order_id if scan_obj.order_id else did_val
                
                if scan_obj.logistics_type == 'INTERNO':
                    # Formato solicitado: ID-(INTERNO)
                    order_id = f"'{raw_id}-(INTERNO)"
                    shipment = raw_id # El ID raw en la columna de envío también
                else:
                    order_id = f"'{raw_id}"
                    shipment = raw_id  # También asignar shipment para casos no INTERNO

                
                estado_retiro = scan_obj.logistics_type or 'DESCONOCIDO'
                estado_actual = scan_obj.logistics_type or 'DESCONOCIDO'
                direccion = scan_obj.logistics_customer_name or 'N/A'
                
                # Forzar Mensajeria si es logística externa
                if tipo_envio == "DESCONOCIDO":
                    tipo_envio = "MENSAJERIA"
                    
            else:
                # Mercado Libre
                order_id = f"'{scan_obj.order_id}" if scan_obj.order_id else 'N/A'
                shipment = scan_obj.shipment_id or 'N/A'
                
                # Crear hipervínculo a Mercado Libre para columna URL
                if scan_obj.order_id:
                    url_link = '=HYPERLINK("https://www.mercadolibre.com.ar/venta/' + str(scan_obj.order_id) + '", "Ver venta")'

                # Calcular estados usando el formatter (igual que update_shipment_status)
                # Estado de retiro: como estaba cuando se escaneó
                estado_retiro = cls._format_status(
                    scan_obj.initial_status,
                    order_data=scan_obj.api_response.get('order') if scan_obj.api_response else None,
                    shipment_data=scan_obj.api_response.get('shipment') if scan_obj.api_response else None
                )
                
                # Estado actual: como está ahora
                estado_actual = cls._format_status(
                    scan_obj.current_status,
                    order_data=scan_obj.api_response.get('order') if scan_obj.api_response else None,
                    shipment_data=scan_obj.api_response.get('shipment') if scan_obj.api_response else None
                )
                
                # BUG FIX: Si es DEVOLUCION, mostrar como VIGENTE en hoja principal
                if estado_actual == 'DEVOLUCION':
                    estado_actual = 'VIGENTE'
                
                # Dirección extraída de la respuesta API (si existe)
                direccion = ""
                if scan_obj.api_response and 'shipment' in scan_obj.api_response:
                    addr = scan_obj.api_response['shipment'].get('receiver_address', {})
                    street = f"{addr.get('street_name','')} {addr.get('street_number','')}"
                    city = addr.get('city', {}).get('name', '')
                    direccion = f"{street.strip()} - {city}".strip(' -')

            # Escribir fila (después de la fila 3 que tiene encabezados)
            # URL va al final
            row = [fecha, order_id, estado_retiro, estado_actual, usuario, shipment, direccion, tipo_envio, url_link]
            
            # Insertar la fila
            sheet.append_row(row)
            
            # Si hay fórmula en URL (columna 9), actualizar con raw=False para interpretarla como fórmula
            if url_link.startswith('=HYPERLINK'):
                try:
                    # Obtener el número de fila que acabamos de insertar
                    all_rows = sheet.get_all_values()
                    last_row_num = len(all_rows)
                    # Actualizar solo la celda de URL (columna I = 9) con raw=False
                    sheet.update(f'I{last_row_num}', [[url_link]], raw=False)
                except Exception as e:
                    print(f"[WARNING] No se pudo actualizar fórmula en URL: {e}")
            
            print(f"[OK] Escaneo registrado en Sheets: {row}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error escribiendo en Sheets: {e}")
            return False
    
    @classmethod
    def get_all_shipments(cls):
        """Retorna una lista de diccionarios con info de cada fila para actualizar"""
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return []
            
            # Obtener todos los valores (incluyendo headers)
            all_rows = sheet.get_all_values()
            
            # Las filas de datos empiezan en la fila 4 (indice 3)
            # Fila 1: Stats
            # Fila 2: Stats
            # Fila 3: Headers
            datarows = []
            
            for index, row in enumerate(all_rows):
                # Ajustar índice a número de fila en Sheets (1-based)
                row_num = index + 1
                
                # Omitir filas de cabecera y vacías
                if row_num < 4 or not row:
                    continue
                    
                # Parsear datos de interés
                # Col A: FECHA (idx 0)
                # Col B: Nº VENTA/PEDIDO (idx 1)
                # Col D: ESTADO ACTUAL (idx 3)
                # Col F: ID ENVIO (idx 5)
                
                try:
                    fecha_val = row[0] if len(row) > 0 else ""
                    shipment_id = row[5] if len(row) > 5 else ""
                    order_id_raw = row[1] if len(row) > 1 else ""
                    current_status = row[3] if len(row) > 3 else ""

                    # Limpiar comillas simples que ponemos para evitar notación científica
                    order_id = order_id_raw.replace("'", "")

                    if shipment_id or order_id:
                        datarows.append({
                            'row_num': row_num,
                            'fecha': fecha_val,
                            'shipment_id': shipment_id,
                            'order_id': order_id,
                            'current_status': current_status
                        })
                except IndexError:
                    continue
                    
            return datarows
            
        except Exception as e:
            print(f"[ERROR] Error leyendo filas de Sheets: {e}")
            return []

    @classmethod
    def update_row_status(cls, row_num, new_status, highlight=False):
        """Actualiza el estado directamente en una fila específica"""
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return False
                
            formatted_status = cls._format_status(new_status)
            
            # Actualizar columna D (4) de esa fila
            sheet.update_cell(row_num, 4, formatted_status)
            
            # Resaltar la celda si se requiere
            if highlight:
                try:
                    # Rango D{row_num}
                    cell_ref = f"D{row_num}"
                    # Color amarillo claro para indicar actualización (#FFF9C4)
                    # gspread usa valores 0-1 para RGB
                    fmt = {
                        "backgroundColor": {
                            "red": 1.0,
                            "green": 0.98,
                            "blue": 0.77
                        }
                    }
                    sheet.format(cell_ref, fmt)
                except Exception as e:
                    print(f"[WARN] No se pudo resaltar la celda {row_num}: {e}")
            
            return True
        except Exception as e:
            print(f"[ERROR] Error actualizando fila {row_num}: {e}")
            return False

    @classmethod
    def update_status(cls, shipment_id, new_status):
        """Actualiza el estado actual de un envío en Google Sheets (Búsqueda)"""
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return False
            
            # Convertir estado técnico a VIGENTE/CANCELADO
            formatted_status = cls._format_status(new_status)
            
            # Buscar la fila con este shipment_id (columna F = 6)
            cell = sheet.find(shipment_id, in_column=6)  # Columna F = 6
            if cell:
                # Actualizar columna D (ESTADO ACTUAL)
                sheet.update_cell(cell.row, 4, formatted_status)
                print(f"[OK] Estado actualizado para {shipment_id}: {formatted_status} (original: {new_status})")
                return True
            else:
                print(f"[WARN] No se encontró el shipment {shipment_id} en Sheets")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error actualizando estado en Sheets: {e}")
            return False
    
    @classmethod
    def cleanup_old_records(cls, days=30):
        """Elimina registros más antiguos que X días manteniendo formatos
        
        Usa batch requests de la API de Google Sheets para evitar problemas con
        múltiples eliminaciones secuenciales que causan desplazamiento de índices
        """
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return False
            
            # Calcular fecha límite
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d')
            
            print(f"[INFO] Limpiando registros anteriores a {cutoff_str}")
            
            # Obtener todas las filas
            all_rows = sheet.get_all_values()
            
            # Identificar filas a eliminar (desde la 4 en adelante, las 3 primeras son stats/headers)
            rows_to_delete = []  # Lista de índices 0-based
            deleted_count = 0
            
            for idx, row in enumerate(all_rows[3:], start=4):  # Empieza en fila 4 (1-based)
                if not row or not row[0]:  # Fila vacía
                    continue
                    
                try:
                    # Parsear fecha (formato: YYYY-MM-DD HH:MM:SS)
                    row_date_str = row[0].split(' ')[0]  # Tomar solo la parte de fecha
                    row_date = datetime.strptime(row_date_str, '%Y-%m-%d')
                    
                    if row_date < cutoff_date:
                        rows_to_delete.append(idx - 1)  # Guardar como 0-based
                        deleted_count += 1
                        print(f"[INFO] Marcada para eliminar fila {idx} (fecha: {row_date_str})")
                except ValueError:
                    # Si no se puede parsear la fecha, mantener la fila
                    pass
            
            # Eliminar filas usando batch requests (evita problemas de índices)
            if rows_to_delete:
                # Sortear en orden inverso (de abajo hacia arriba)
                sorted_rows = sorted(rows_to_delete, reverse=True)
                
                # Usar credenciales para acceder a la API
                creds = ServiceAccountCredentials.from_json_keyfile_name(cls.CREDENTIALS_FILE, cls.SCOPE)
                sheets_service = build('sheets', 'v4', credentials=creds)
                
                # Obtener el ID de la hoja (sheet_id)
                sheet_id = sheet.id
                
                # Construir batch request para eliminar todas las filas en una sola llamada
                requests = []
                for row_idx_0based in sorted_rows:
                    # deleteDimension requiere startIndex y endIndex (0-based)
                    # startIndex: 0-based row number
                    # endIndex: exclusive, row number + 1
                    requests.append({
                        'deleteDimension': {
                            'range': {
                                'sheetId': sheet_id,
                                'dimension': 'ROWS',
                                'startIndex': row_idx_0based,
                                'endIndex': row_idx_0based + 1
                            }
                        }
                    })
                
                try:
                    # Ejecutar batch update
                    body = {
                        'requests': requests
                    }
                    sheets_service.spreadsheets().batchUpdate(
                        spreadsheetId=cls.SPREADSHEET_ID,
                        body=body
                    ).execute()
                    
                    print(f"[OK] Limpieza completada: {deleted_count} registros eliminados en batch")
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Quota exceeded" in error_str:
                        print(f"[WARN] Error por límite de cuota: {e}")
                        print("[WARN] Se marcaron las filas para eliminar pero se alcanzó el límite de API")
                    else:
                        print(f"[WARN] Error en batch update: {e}")
                        # Intentar eliminación secuencial como fallback
                        print("[INFO] Intentando eliminación secuencial...")
                        for row_idx_0based in sorted_rows:
                            try:
                                row_num_1based = row_idx_0based + 1
                                sheet.delete_rows(row_num_1based, row_num_1based)
                                print(f"[OK] Fila {row_num_1based} eliminada")
                            except Exception as e2:
                                if "429" in str(e2) or "Quota exceeded" in str(e2):
                                    print(f"[WARN] Error de cuota eliminando fila {row_num_1based}")
                                    time.sleep(1)
                                    continue
                                else:
                                    print(f"[WARN] Error eliminando fila {row_num_1based}: {e2}")
            else:
                print("[INFO] No hay registros antiguos para eliminar")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error durante limpieza: {e}")
            import traceback
            traceback.print_exc()
            return False
    @classmethod
    def save_weekly_report(cls, week_start, week_end, flex_count, cambios_count, particulares_count, cancelados_count, a_devolver, daily_counts=None):
        """Guarda o actualiza el reporte semanal en una hoja dedicada de Google Sheets"""
        try:
            sheet = cls._get_sheet()
            if not sheet:
                return False
            
            spreadsheet = sheet.spreadsheet
            
            # Intentar obtener o crear la hoja "Reportes Semanales"
            sheet_exists = True
            try:
                report_sheet = spreadsheet.worksheet("Reportes Semanales")
            except gspread.WorksheetNotFound:
                # Crear la hoja si no existe
                report_sheet = spreadsheet.add_worksheet(title="Reportes Semanales", rows="100", cols="15")
                sheet_exists = False
                print("[OK] Hoja 'Reportes Semanales' creada")
            
            # Configurar/verificar encabezados
            headers = ["SEMANA INICIO", "SEMANA FIN", "FLEX", "CAMBIOS", "PARTICULARES", "CANCELADOS", "A DEVOLVER", "LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM", "FECHA REPORTE"]
            
            # Verificar si la fila 1 tiene los encabezados correctos
            try:
                first_row = report_sheet.row_values(1)
                if not first_row or first_row != headers:
                    # Actualizar encabezados
                    report_sheet.update('A1:O1', [headers])
                    print("[OK] Encabezados actualizados")
            except:
                # Si hay error, crear los encabezados
                report_sheet.update('A1:O1', [headers])
                print("[OK] Encabezados creados")
            
            # Preparar datos
            fecha_reporte = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            week_start_str = week_start.strftime('%Y-%m-%d')
            week_end_str = week_end.strftime('%Y-%m-%d')
            
            # Construir fila con conteos diarios
            row = [
                week_start_str,
                week_end_str,
                flex_count,
                cambios_count,
                particulares_count,
                cancelados_count,
                a_devolver
            ]
            
            # Agregar conteos diarios si existen
            if daily_counts:
                days_order = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                for day in days_order:
                    row.append(daily_counts.get(day, 0))
            else:
                # Si no hay datos diarios, agregar 0s
                row.extend([0, 0, 0, 0, 0, 0, 0])
            
            row.append(fecha_reporte)
            
            # Buscar si ya existe una fila para esta semana (desde fila 2 en adelante)
            existing_row = None
            try:
                # Obtener todas las filas desde la 2 en adelante
                all_values = report_sheet.get_all_values()
                
                # Buscar la semana en las filas de datos (skip row 0 que son headers)
                for idx, row_data in enumerate(all_values[1:], start=2):  # start=2 porque las filas empiezan en 1 y saltamos header
                    if row_data and len(row_data) > 0 and row_data[0] == week_start_str:
                        existing_row = idx
                        break
            except Exception as e:
                print(f"[WARN] Error buscando fila existente: {e}")
            
            if existing_row:
                # Actualizar fila existente
                range_notation = f'A{existing_row}:O{existing_row}'
                report_sheet.update(range_notation, [row])
                print(f"[OK] Reporte semanal ACTUALIZADO en Sheets: {week_start_str} - {week_end_str} (fila {existing_row})")
            else:
                # No existe, crear nueva fila
                report_sheet.append_row(row)
                print(f"[OK] Reporte semanal CREADO en Sheets: {week_start_str} - {week_end_str}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error guardando reporte en Sheets: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @classmethod
    def _get_pending_returns_sheet(cls):
        """Obtiene la hoja 'Pendientes de devolución'"""
        if not cls.CREDENTIALS_FILE.exists():
            print(f"[WARN] No se encontró credentials.json en {cls.CREDENTIALS_FILE}")
            return None
            
        creds = ServiceAccountCredentials.from_json_keyfile_name(cls.CREDENTIALS_FILE, cls.SCOPE)
        client = gspread.authorize(creds)
        
        try:
            spreadsheet = client.open_by_key(cls.SPREADSHEET_ID)
            
            # Intentar obtener la hoja existente
            try:
                sheet = spreadsheet.worksheet(cls.PENDING_RETURNS_SHEET_NAME)
            except gspread.WorksheetNotFound:
                # Crear la hoja si no existe
                sheet = spreadsheet.add_worksheet(title=cls.PENDING_RETURNS_SHEET_NAME, rows="1000", cols="8")
                # Agregar encabezados
                sheet.update('A1:H1', [cls.PENDING_RETURNS_HEADERS])
                print(f"[OK] Hoja '{cls.PENDING_RETURNS_SHEET_NAME}' creada con encabezados")
            
            return sheet
        except gspread.SpreadsheetNotFound:
            print(f"[ERROR] No se encontró la hoja con ID: {cls.SPREADSHEET_ID}")
            return None
    
    @classmethod
    def log_to_pending_returns(cls, scan_obj):
        """Registra un escaneo en 'Pendientes de devolución' (solo primer escaneo de CAMBIO/DEVOLUCION)"""
        try:
            sheet = cls._get_pending_returns_sheet()
            if not sheet:
                return False
            
            # Preparar datos - similar a log_scan pero para la hoja de pendientes
            from django.utils import timezone
            local_date = timezone.localtime(scan_obj.scanned_at)
            fecha = local_date.strftime('%Y-%m-%d %H:%M:%S')
            usuario = scan_obj.scanner_user or 'Desconocido'
            
            # Inicializar URL vacía
            url_link = ''
            
            # Determinar order_id y shipment_id
            if scan_obj.is_logistics:
                did_val = scan_obj.shipment_id or scan_obj.logistics_data.get('did', 'N/A') if scan_obj.logistics_data else 'N/A'
                raw_id = scan_obj.order_id if scan_obj.order_id else did_val
                order_id = f"'{raw_id}"
                shipment = raw_id
                direccion = scan_obj.logistics_customer_name or 'N/A'
                estado_retiro = scan_obj.logistics_type or 'DESCONOCIDO'
                estado_actual = scan_obj.logistics_type or 'DESCONOCIDO'
            else:
                # Mercado Libre
                order_id = f"'{scan_obj.order_id}" if scan_obj.order_id else 'N/A'
                shipment = scan_obj.shipment_id or 'N/A'
                
                # URL con hipervínculo para columna final
                if scan_obj.order_id:
                    url_link = '=HYPERLINK("https://www.mercadolibre.com.ar/venta/' + str(scan_obj.order_id) + '", "Ver venta")'
                
                # Estado usando el formatter
                estado_retiro = cls._format_status(
                    scan_obj.initial_status,
                    order_data=scan_obj.api_response.get('order') if scan_obj.api_response else None,
                    shipment_data=scan_obj.api_response.get('shipment') if scan_obj.api_response else None
                )
                
                estado_actual = cls._format_status(
                    scan_obj.current_status,
                    order_data=scan_obj.api_response.get('order') if scan_obj.api_response else None,
                    shipment_data=scan_obj.api_response.get('shipment') if scan_obj.api_response else None
                )
                
                # Dirección
                direccion = ""
                if scan_obj.api_response and 'shipment' in scan_obj.api_response:
                    addr = scan_obj.api_response['shipment'].get('receiver_address', {})
                    street = f"{addr.get('street_name','')} {addr.get('street_number','')}"
                    city = addr.get('city', {}).get('name', '')
                    direccion = f"{street.strip()} - {city}".strip(' -')
            
            # Columna H (ESTADO CIERRE) queda vacía inicialmente
            estado_cierre = ""
            
            # Escribir fila: FECHA, NRO VENTA/ORDEN, ESTADO DE RETIRO, ESTADO ACTUAL, QUIEN ESCANEO, ID ENVIO, DIRECCION, ESTADO CIERRE, URL
            row = [fecha, order_id, estado_retiro, estado_actual, usuario, shipment, direccion, estado_cierre, url_link]
            sheet.append_row(row)
            
            # Si hay fórmula en URL (columna I = 9), actualizar con raw=False para interpretarla como fórmula
            if url_link.startswith('=HYPERLINK'):
                try:
                    # Obtener el número de fila que acabamos de insertar
                    all_rows = sheet.get_all_values()
                    last_row_num = len(all_rows)
                    # Actualizar solo la celda de URL (columna I = 9) con raw=False
                    sheet.update(f'I{last_row_num}', [[url_link]], raw=False)
                except Exception as e:
                    print(f"[WARNING] No se pudo actualizar fórmula en URL de Pendientes: {e}")
            
            print(f"[OK] Registrado en 'Pendientes de devolución': {shipment}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error escribiendo en 'Pendientes de devolución': {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @classmethod
    def mark_return_complete(cls, shipment_id, return_type):
        """Marca la devolución como completa en columna H (3er escaneo)
        
        Args:
            shipment_id: ID del envío
            return_type: 'CAMBIO' o 'DEVOLUCION'
        """
        try:
            sheet = cls._get_pending_returns_sheet()
            if not sheet:
                return False
            
            # Buscar la fila con este shipment_id (columna F = 6)
            try:
                cell = sheet.find(shipment_id, in_column=6)
                if cell:
                    # Actualizar columna H (8) con el estado de cierre
                    status_text = f"{return_type} COMPLETO"
                    sheet.update_cell(cell.row, 8, status_text)
                    print(f"[OK] Marcado como completo en 'Pendientes de devolución': {shipment_id} -> {status_text}")
                    return True
                else:
                    print(f"[WARN] No se encontró {shipment_id} en 'Pendientes de devolución'")
                    return False
            except gspread.exceptions.CellNotFound:
                print(f"[WARN] No se encontró {shipment_id} en 'Pendientes de devolución'")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error marcando devolución completa: {e}")
            import traceback
            traceback.print_exc()
            return False
