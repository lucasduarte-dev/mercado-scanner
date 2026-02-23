import json
from django.http import JsonResponse
from .models import Scan

def process_premier_scan(qr_data, scanner_user):
    """Procesa un QR de Premier Mensajeria (logística externa)"""
    from .premier_api import buscar_envio_premier
    
    try:
        print(f"[Premier] Iniciando búsqueda para: {qr_data}")
        
        did = str(qr_data.get('did', ''))
        
        # DETECCIÓN DE DUPLICADOS
        existing_scan = Scan.objects.filter(
            shipment_id=did,
            is_logistics=True,
            status='success'
        ).first()
        
        if existing_scan:
            print(f"[Premier] ⚠️ Duplicado detectado: DID {did} (escaneado el {existing_scan.scanned_at})")
            
            from django.utils import timezone
            local_date = timezone.localtime(existing_scan.scanned_at)

            return JsonResponse({
                'success': True,
                'duplicate': True,
                'scan_id': existing_scan.id,
                'shipment_id': did,
                'is_logistics': True,
                'api_data': {
                    'is_logistics': True,
                    'is_duplicate': True,
                    'customer_name': existing_scan.logistics_customer_name,
                    'tipo': existing_scan.logistics_type,
                    'did': did,
                    'status': existing_scan.logistics_type or 'PARTICULAR',
                    'previous_scan_date': local_date.strftime('%d/%m/%Y %H:%M')
                },
                'status': existing_scan.status
            })
        
        # Crear registro inicial
        scan = Scan.objects.create(
            shipment_id=did,
            sender_id=None,
            hash_code=None,
            security_digit=None,
            raw_qr_data=json.dumps(qr_data),
            scanner_user=scanner_user,
            status='pending',
            is_logistics=True,
            logistics_data=qr_data
        )
        
        # Buscar en Premier Mensajeria
        result = buscar_envio_premier(qr_data)
        
        if result.get('found'):
            # Extraer datos
            nombre = result.get('nombre', '')
            apellido = result.get('apellido', '')
            tipo = result.get('tipo', '')
            
            # Actualizar registro
            scan.logistics_customer_name = f"{nombre} {apellido}".strip()
            scan.logistics_type = tipo
            scan.shipping_mode = 'mensajeria'  # Marcar como mensajería para stats
            scan.initial_status = tipo
            scan.current_status = tipo
            scan.status = 'success'
            scan.order_id = str(qr_data.get('did', ''))
            
            # Construir respuesta API simulada para frontend
            api_result = {
                'is_logistics': True,
                'customer_name': scan.logistics_customer_name,
                'tipo': tipo,
                'did': qr_data.get('did'),
                'status': result.get('status', 'VIGENTE')
            }
            
            print(f"[Premier] ✓ Encontrado: {scan.logistics_customer_name} - {tipo}")
        else:
            scan.status = 'error'
            scan.error_message = result.get('error', 'No se encontró el envío en Premier')
            api_result = {
                'is_logistics': True,
                'error': scan.error_message
            }
            print(f"[Premier] ✗ No encontrado")
        
        scan.save()
        
        # Registrar en Google Sheets
        if scan.status == 'success':
            from .sheets_logger import GoogleSheetsLogger
            GoogleSheetsLogger.log_scan(scan)
            # Si es un CAMBIO de Premier, también registrar en 'Pendientes de devolución'
            try:
                if getattr(scan, 'logistics_type', None) == 'CAMBIO':
                    GoogleSheetsLogger.log_to_pending_returns(scan)
            except Exception as e:
                print(f"[Premier WARN] No se pudo registrar en Pendientes: {e}")
        
        return JsonResponse({
            'success': scan.status == 'success',
            'scan_id': scan.id,
            'shipment_id': str(qr_data.get('did', '')),
            'is_logistics': True,
            'api_data': api_result,
            'status': scan.status
        })
        
    except Exception as e:
        print(f"[Premier ERROR] {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'is_logistics': True,
            'error': str(e)
        }, status=400)
