import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Scan
from .ml_api import MercadoLibreAPI
from .premier_handler import process_premier_scan


def index(request):
    """Vista principal con el scanner de QR"""
    ml_api = MercadoLibreAPI()
    credentials = ml_api.get_credentials_status()
    recent_scans = Scan.objects.all()[:10]
    
    # Calcular estadísticas
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)
    
    today_scans = Scan.objects.filter(scanned_at__gte=today_start)
    
    # Separar CANCELADOS y DEVOLUCIONES del total
    # Esto evita confusión al entregar - solo cuentan paquetes vigentes
    cancelados = today_scans.filter(is_cancelled=True).count()
    devoluciones = today_scans.filter(current_status__icontains='return').count()
    
    # Total de escaneos VIGENTES (excluye cancelados y devoluciones)
    total_scans = today_scans.count()
    vigentes = total_scans - cancelados - devoluciones
    
    cambios = today_scans.filter(logistics_type='CAMBIO').exclude(is_cancelled=True).count()
    particulares = today_scans.filter(logistics_type='PARTICULAR').exclude(is_cancelled=True).count()

    stats = {
        'flex': today_scans.filter(shipping_mode='flex').exclude(is_cancelled=True).exclude(current_status__icontains='return').count(),
        'mensajeria': today_scans.filter(shipping_mode='mensajeria').exclude(is_cancelled=True).exclude(current_status__icontains='return').count(),
        'vigentes': vigentes,  # Solo paquetes que deben entregar
        'cancelados': cancelados,  # Aparte para no confundir
        'devoluciones': devoluciones,  # Aparte
        'total': total_scans,  # Total de escaneos (incluye todo)
        'cambios': cambios,
        'particulares': particulares,
        'total_mensajeria': cambios + particulares,
    }
    
    context = {
        'accounts': credentials.get('accounts', []),
        'accounts_count': credentials.get('accounts_count', 0),
        'any_active': any(acc.get('has_token') for acc in credentials.get('accounts', [])),
        'stats': stats,
        'recent_scans': recent_scans,
    }
    return render(request, 'scanner/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def process_scan(request):
    """Procesa el QR escaneado y consulta la API de ML"""
    try:
        data = json.loads(request.body)
        raw_qr_data = data.get('qr_data', '')
        scanner_user = data.get('scanner_user', '') # Nuevo campo
        
        # Intentar parsear el JSON del QR
        try:
            qr_json = json.loads(raw_qr_data)
            
            # Detectar si es QR de Premier Mensajeria (logística)
            if 'local' in qr_json and 'did' in qr_json and 'cliente' in qr_json:
                # Es un QR de Premier Mensajeria
                print(f"[SCAN] QR de Premier Mensajeria detectado scroll: {qr_json}")
                return process_premier_scan(qr_json, scanner_user)
            
            # Es un QR de Mercado Libre
            shipment_id = qr_json.get('id', '')
            sender_id = str(qr_json.get('sender_id', ''))
            hash_code = qr_json.get('hash_code', '')
            security_digit = qr_json.get('security_digit', '')
        except json.JSONDecodeError:
            # Si no es JSON, asumimos que es un código de barras de ML
            shipment_id = raw_qr_data.strip()
            sender_id = None
            hash_code = None
            security_digit = None
            qr_json = {'raw': raw_qr_data}
        
        # TRACKING DE ESCANEOS - Contar cuántas veces se escaneó este código
        previous_scans = Scan.objects.filter(
            shipment_id=shipment_id,
            status='success'
        ).order_by('-scanned_at')

        # PREVENCIÓN DE DUPLICADOS: Primero buscar en Google Sheets (si disponible)
        try:
            from .sheets_logger import GoogleSheetsLogger
            sheet_rows = GoogleSheetsLogger.get_all_shipments()
            sheet_match = None
            for r in sheet_rows:
                sid = (r.get('shipment_id') or '')
                oid = (r.get('order_id') or '')
                # Comparar shipment_id o order_id (si acaso)
                if shipment_id and sid and shipment_id in sid:
                    sheet_match = r
                    break
                if shipment_id and oid and shipment_id in oid:
                    sheet_match = r
                    break

            if sheet_match:
                prev_date = sheet_match.get('fecha') or 'Fecha desconocida'
                return JsonResponse({
                    'success': True,
                    'duplicate': True,
                    'source': 'sheets',
                    'shipment_id': shipment_id,
                    'previous_scan_date': prev_date,
                    'status': sheet_match.get('current_status'),
                    'api_data': {
                        'previous_scan_date': prev_date,
                        'status': sheet_match.get('current_status')
                    }
                })
        except Exception as e:
            print(f"[WARN] Error consultando Sheets para duplicados: {e}")

        # PREVENCIÓN DE DUPLICADOS (comportamiento similar a Premier) usando la BD
        if previous_scans.exists():
            last_scan = previous_scans.first()
            try:
                from django.utils import timezone
                local_date = timezone.localtime(last_scan.scanned_at)
                prev_date = local_date.strftime('%d/%m/%Y %H:%M')
            except Exception:
                prev_date = str(last_scan.scanned_at)

            # Si no se encontró en Sheets anteriormente, intentar sincronizar la fila
            try:
                from .sheets_logger import GoogleSheetsLogger
                # Re-check rápido: si no hay fila en Sheets (sheet_match variable), intentamos subirla
                if 'sheet_match' in locals() and sheet_match is None:
                    ok = GoogleSheetsLogger.log_scan(last_scan)
                    if ok:
                        print(f"[SYNC] Scan {last_scan.id} sincronizado a Sheets antes de devolver duplicate")
            except Exception as e:
                print(f"[WARN] No se pudo sincronizar a Sheets antes de devolver duplicate: {e}")

            return JsonResponse({
                'success': True,
                'duplicate': True,
                'scan_id': last_scan.id,
                'shipment_id': shipment_id,
                'previous_scan_date': prev_date,
                'status': last_scan.status,
                'api_data': {
                    'previous_scan_date': prev_date,
                    'scan_id': last_scan.id,
                    'status': last_scan.status
                }
            })

        scan_count = previous_scans.count() + 1  # +1 porque este es un nuevo escaneo

        print(f"[SCAN] Shipment {shipment_id} - Escaneo #{scan_count}")

        # Si es 2do o 3er escaneo, mostrar info del escaneo anterior
        if scan_count >= 2:
            last_scan = previous_scans.first()
            print(f"[SCAN] ⚠️ Re-escaneo detectado: {shipment_id} (último escaneo: {last_scan.scanned_at})")
        
        # Crear registro del escaneo con scan_count
        scan = Scan.objects.create(
            shipment_id=shipment_id,
            sender_id=sender_id,
            hash_code=hash_code,
            security_digit=security_digit,
            raw_qr_data=raw_qr_data,
            scanner_user=scanner_user,
            scan_count=scan_count,  # Guardar el número de escaneo
            status='pending'
        )
        
        # Consultar API de Mercado Libre
        ml_api = MercadoLibreAPI()
        # Pasamos sender_id para ayudar a seleccionar la cuenta correcta
        api_result = ml_api.get_full_shipment_info(shipment_id, sender_id)
        
        # Actualizar el registro con la respuesta de la API
        if api_result.get('shipment'):
            scan.api_response = api_result
            scan.shipment_status = api_result['shipment'].get('status')
            scan.order_id = api_result['shipment'].get('order_id')
            
            # Determinar tipo de envío (Flex vs ME2)
            logistic_type = api_result['shipment'].get('logistic_type')
            if logistic_type == 'self_service':
                scan.shipping_mode = 'flex'
            else:
                scan.shipping_mode = 'me2'
            
            # Obtener estado del pedido (más preciso que el estado del envío)
            order_status = None
            if api_result.get('order'):
                order_status = api_result['order'].get('status')
                scan.order_status = order_status
                buyer = api_result['order'].get('buyer', {})
                scan.buyer_nickname = buyer.get('nickname')
            
            # Guardar estados del PEDIDO (no del envío) - más preciso
            scan.initial_status = order_status or scan.shipment_status
            scan.current_status = order_status or scan.shipment_status
            
            # IMPORTANTE: Verificar DEVOLUCIONES PRIMERO (antes de cancelaciones)
            # porque una devolución puede tener order_status='cancelled' pero es DEVOLUCION, no CANCELADO
            ship_status = str(scan.shipment_status).lower()
            substatus = str(api_result['shipment'].get('substatus', '')).lower()
            
            return_keywords = ['returned', 'returning', 'refused', 'automatic_return']
            is_return = any(k in ship_status for k in return_keywords) or any(k in substatus for k in return_keywords)
            
            # Verificar si fue entregado y luego cancelado (= devolución post-entrega)
            is_delivered_then_cancelled = False
            if order_status == 'cancelled' and api_result.get('order'):
                tags = api_result['order'].get('tags', [])
                payments = api_result['order'].get('payments', [])
                
                # SOLO es devolución si hay evidencia clara de ENTREGA previa
                # BUG FIX: 'refunded' por sí solo NO significa devolución - ML reembolsa también en cancelaciones pre-entrega
                
                # Caso 1: Si tiene tag 'delivered' → definitivamente es DEVOLUCION
                if 'delivered' in tags:
                    is_delivered_then_cancelled = True
                
                # Caso 2: Si tiene 'not_delivered' → definitivamente es CANCELADO (no devolución)
                # Incluso si el pago está refunded
                elif 'not_delivered' in tags:
                    is_delivered_then_cancelled = False  # Explícitamente cancelado, no devuelto
                
                # Caso 3: Si no tiene ni 'delivered' ni 'not_delivered', pero tiene pago refunded
                # Solo entonces podemos asumir que PUEDE ser devolución (caso edge raro)
                elif any(p.get('status') == 'refunded' for p in payments):
                    # Verificación adicional: si el shipment tiene substatus returning_to_sender
                    # o status 'returned', entonces sí es devolución
                    if api_result.get('shipment'):
                        ship_sub = str(api_result['shipment'].get('substatus', '')).lower()
                        if 'return' in ship_sub:
                            is_delivered_then_cancelled = True
                        # Si no tiene indicador de return en shipment, asumir CANCELADO
                        # (refund solo significa que se devolvió el dinero, no el producto)
            
            if is_return or is_delivered_then_cancelled:
                # Es DEVOLUCIÓN
                scan.current_status = 'returned'
                scan.is_cancelled = False  # NO es cancelado, es devolución
            elif order_status == 'cancelled':
                # Es CANCELADO (pre-entrega)
                scan.is_cancelled = True
                scan.current_status = 'cancelled'
            elif not order_status:
                # Fallback al estado del envío si no hay order
                substatus_val = api_result['shipment'].get('substatus')
                if scan.shipment_status == 'cancelled' or substatus_val == 'cancelled':
                    scan.is_cancelled = True
                    scan.current_status = 'cancelled'
            
            scan.status = 'success'
        else:
            # Fallback a Escaneo Interno (INTERNO)
            # Si no es un envío de ML reconocido, lo tratamos como escaneo interno
            print(f"[SCAN] Fallback a Interno para: {raw_qr_data}")
            
            scan.is_logistics = True
            scan.logistics_type = 'INTERNO'
            scan.shipping_mode = 'mensajeria' # Asumimos mensajería para internos desconocidos también
            scan.logistics_customer_name = raw_qr_data
            scan.order_id = raw_qr_data # Usar dato raw como Order ID también
            # Usar 'did' para que aparezca en columnas de ID en Sheets
            scan.logistics_data = {'did': raw_qr_data, 'raw': raw_qr_data}
            scan.status = 'success'
            scan.error_message = None
            
            # Respuesta simulada para frontend
            api_result = {
                'shipment': {'status': 'active'}, # Dummy to prevent errors
            }
            scan.api_response = api_result

        scan.save()
        
        # Registrar en Google Sheets (async idealmente, pero sync por ahora)
        if scan.status == 'success':
            from .sheets_logger import GoogleSheetsLogger
            
            # Determinar tipo de estado para tracking de devoluciones
            estado_tipo = None
            if scan.is_logistics:
                estado_tipo = scan.logistics_type
            else:
                if scan.current_status == 'cancelled':
                    estado_tipo = 'CANCELADO'
                elif scan.current_status == 'returned' or 'returned' in str(scan.current_status).lower():
                    estado_tipo = 'DEVOLUCION'
                elif 'returning' in str(scan.current_status).lower():
                    estado_tipo = 'DEVOLUCION'
            
            # Determinar si debe ir a "Pendientes de devolución"
            debe_registrar_pendiente = False
            
            if scan_count == 1:
                if scan.is_logistics:
                    if estado_tipo in ['CAMBIO', 'PARTICULAR']:
                        debe_registrar_pendiente = True
                else:
                    estado_retiro_fmt = GoogleSheetsLogger._format_status(
                        scan.initial_status,
                        order_data=scan.api_response.get('order') if scan.api_response else None,
                        shipment_data=scan.api_response.get('shipment') if scan.api_response else None
                    )
                    
                    estado_actual_fmt = GoogleSheetsLogger._format_status(
                        scan.current_status,
                        order_data=scan.api_response.get('order') if scan.api_response else None,
                        shipment_data=scan.api_response.get('shipment') if scan.api_response else None
                    )
                    
                    if estado_retiro_fmt == 'VIGENTE' and estado_actual_fmt == 'CANCELADO':
                        debe_registrar_pendiente = True
                        print(f"[SCAN] Detectado: Vigente→CANCELADO - Registrando en Pendientes")
            
            # REGISTRAR EN AMBAS HOJAS cuando corresponda
            if debe_registrar_pendiente:
                print(f"[SCAN] 1er escaneo de {estado_tipo} - Registrando en hoja principal Y en 'Pendientes de devolución'")
                # Registrar en hoja principal (para que aparezca en el reporte semanal)
                GoogleSheetsLogger.log_scan(scan)
                # Registrar también en hoja de pendientes
                GoogleSheetsLogger.log_to_pending_returns(scan)
            else:
                # Registrar solo en hoja principal
                GoogleSheetsLogger.log_scan(scan)
            
            # TERCER ESCANEO de CAMBIO/DEVOLUCION → Marcar como completo
            if scan_count == 3 and estado_tipo in ['CAMBIO', 'DEVOLUCION']:
                print(f"[SCAN] 3er escaneo de {estado_tipo} - Marcando como COMPLETO")
                GoogleSheetsLogger.mark_return_complete(scan.shipment_id, estado_tipo)
        
        # Construir respuesta JSON
        response_data = {
            'success': True,
            'scan_id': scan.id,
            'shipment_id': scan.shipment_id,
            'sender_id': sender_id,
            'qr_data': qr_json,
            'status': scan.status,
            'scan_count': scan_count  # Informar al frontend cuántas veces se escaneó
        }
        
        if scan.is_logistics and scan.logistics_type == 'INTERNO':
            response_data['is_logistics'] = True
            response_data['api_data'] = {
                'is_logistics': True,
                'status': 'VIGENTE',
                'tipo': 'INTERNO',
                'customer_name': raw_qr_data,
                'did': raw_qr_data
            }
        else:
            response_data['api_data'] = api_result
            
            # Determinar status_type explícito para el frontend
            if scan.is_cancelled:
                response_data['api_data']['status_type'] = 'CANCELADO'
                response_data['api_data']['display_status'] = 'CANCELADO'
            elif 'returned' in str(scan.current_status).lower() or 'returning' in str(scan.current_status).lower():
                response_data['api_data']['status_type'] = 'DEVOLUCION'
                response_data['api_data']['display_status'] = 'DEVOLUCIÓN'
            else:
                response_data['api_data']['status_type'] = 'VIGENTE'
                response_data['api_data']['display_status'] = 'VIGENTE'
            
            # Mensaje especial para 3er escaneo de CAMBIO/DEVOLUCION
            if scan_count == 3:
                estado_tipo = None
                if scan.is_logistics:
                    estado_tipo = scan.logistics_type
                else:
                    if 'returned' in str(scan.current_status).lower() or 'returning' in str(scan.current_status).lower():
                        estado_tipo = 'DEVOLUCION'
                
                if estado_tipo in ['CAMBIO', 'DEVOLUCION']:
                    response_data['api_data']['completion_message'] = f"{estado_tipo} COMPLETADO ✓"
            
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"Error procesando scan: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def scan_history(request):
    """Obtiene historial de escaneos"""
    scans = Scan.objects.all()[:20]
    data = [
        {
            'id': s.id,
            'shipment_id': s.shipment_id,
            'status': s.status,
            'shipment_status': s.shipment_status,
            'buyer_nickname': s.buyer_nickname,
            'scanned_at': s.scanned_at.isoformat()
        }
        for s in scans
    ]
    return JsonResponse({'scans': data})


def scan_detail(request, scan_id):
    """Obtiene detalle completo de un escaneo"""
    try:
        scan = Scan.objects.get(id=scan_id)
        return JsonResponse({
            'success': True,
            'scan': {
                'id': scan.id,
                'shipment_id': scan.shipment_id,
                'sender_id': scan.sender_id,
                'hash_code': scan.hash_code,
                'security_digit': scan.security_digit,
                'raw_qr_data': scan.raw_qr_data,
                'api_response': scan.api_response,
                'status': scan.status,
                'error_message': scan.error_message,
                'scanned_at': scan.scanned_at.isoformat()
            }
        })
    except Scan.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Scan no encontrado'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def mark_return_complete(request):
    """Marca un retorno/cambio en 'Pendientes de devolución' como entregado en empresa
    
    No crea un nuevo Scan ni dispara lógica de duplicados.
    Solo actualiza la columna H (ESTADO CIERRE) en la hoja 'Pendientes de devolución'.
    """
    try:
        data = json.loads(request.body)
        shipment_id = data.get('shipment_id', '').strip()
        
        if not shipment_id:
            return JsonResponse({
                'success': False,
                'error': 'shipment_id es requerido'
            }, status=400)
        
        # Si el shipment_id es un JSON de Premier (QR completo), extraer el 'did'
        try:
            qr_parsed = json.loads(shipment_id)
            if isinstance(qr_parsed, dict) and 'did' in qr_parsed:
                shipment_id = str(qr_parsed['did'])
        except (json.JSONDecodeError, TypeError):
            pass  # No es JSON, usar el valor tal cual
        
        # Marcar en Pendientes de devolución
        from .sheets_logger import GoogleSheetsLogger
        
        # Intentar marcar como completo (busca la fila y actualiza columna H)
        ok = GoogleSheetsLogger.mark_return_complete(shipment_id, 'ENTREGADO EN EMPRESA')
        
        if ok:
            return JsonResponse({
                'success': True,
                'shipment_id': shipment_id,
                'message': 'Retorno marcado como entregado en empresa',
                'status': 'ENTREGADO EN EMPRESA'
            })
        else:
            return JsonResponse({
                'success': False,
                'shipment_id': shipment_id,
                'error': 'No se encontró el shipment en Pendientes de devolución'
            }, status=404)
    
    except Exception as e:
        print(f"Error marcando retorno completo: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
