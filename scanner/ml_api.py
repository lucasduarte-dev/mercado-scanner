"""
Cliente para la API de Mercado Libre (Multi-Cuenta)
Usa tokens guardados en meli_tokens.json o variable de entorno MELI_TOKENS
"""
import json
import requests
from datetime import datetime
from pathlib import Path
import os

class MercadoLibreAPI:
    BASE_URL = "https://api.mercadolibre.com"
    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
    TOKEN_FILE = Path(__file__).parent.parent / "meli_tokens.json"
    TOKENS_JSON = os.getenv('MELI_TOKENS')  # Variable de entorno para Railway
    
    def __init__(self):
        self.accounts = []
        self.load_tokens()

    def load_tokens(self):
        """Carga tokens desde variable de entorno o archivo JSON
        
        Orden de precedencia:
        1. Variable MELI_TOKENS (Railway/Production)
        2. Archivo meli_tokens.json (Desarrollo local)
        """
        raw_accounts = []
        
        # Intentar desde variable de entorno (Railway)
        if self.TOKENS_JSON:
            try:
                data = json.loads(self.TOKENS_JSON)
                if isinstance(data, dict):
                    raw_accounts = [data]
                elif isinstance(data, list):
                    raw_accounts = data
            except Exception as e:
                print(f"[WARN] Error al parsear MELI_TOKENS: {e}")
        
        # Fallback a archivo local
        if not raw_accounts and self.TOKEN_FILE.exists():
            try:
                with open(self.TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                
                # Normalizar a lista
                if isinstance(data, dict):
                    raw_accounts = [data]
                elif isinstance(data, list):
                    raw_accounts = data
            except Exception as e:
                print(f"[WARN] Error al leer meli_tokens.json: {e}")
        
        if not raw_accounts:
            print("[WARN] No se encontraron tokens de Mercado Libre")
            print(f"  - Variable MELI_TOKENS: {'Sí' if self.TOKENS_JSON else 'No'}")
            print(f"  - Archivo {self.TOKEN_FILE}: {'Sí' if self.TOKEN_FILE.exists() else 'No'}")
            return
        
        self.accounts = []
        for acc in raw_accounts:
            account = {
                'access_token': acc.get('access_token'),
                'refresh_token': acc.get('refresh_token'),
                'user_id': acc.get('user_id'),
                'client_secret': acc.get('client_secret'),
                'expires_at': acc.get('expires_at', 0),
                'client_id': acc.get('client_id')
            }
            
            # Intentar extraer App ID si no existe
            if not account['client_id'] and account['access_token'] and 'APP_USR-' in account['access_token']:
                try:
                    parts = account['access_token'].split('-')
                    if len(parts) > 1:
                        account['client_id'] = parts[1]
                except:
                    pass
            
            self.accounts.append(account)
        
        print(f"[OK] {len(self.accounts)} cuentas cargadas.")
        self.check_expirations()

    def check_expirations(self):
        """Revisa y refresca tokens expirados al inicio"""
        now = datetime.now().timestamp()
        for account in self.accounts:
            if account['expires_at'] < now:
                print(f"[INFO] Token expirado para usuario {account.get('user_id')}. Refrescando...")
                self.try_refresh_token(account)

    def save_tokens(self):
        """Guarda la lista de cuentas en el JSON"""
        try:
            # Si solo hay una cuenta y el formato original era dict, podríamos mantenerlo,
            # pero para estandarizar, guardaremos lista si hay > 1, o lista siempre.
            # El usuario aceptó cambiar formato, así que guardamos lista.
            with open(self.TOKEN_FILE, 'w') as f:
                json.dump(self.accounts, f, indent=2)
            print(f"[OK] Tokens guardados")
        except Exception as e:
            print(f"[ERROR] Error guardando tokens: {e}")

    def try_refresh_token(self, account):
        """Intenta refrescar el access token de una cuenta específica"""
        if not account.get('refresh_token'):
            return False
            
        client_id = account.get('client_id', "1698826354444207") # Default fallback
        
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'refresh_token': account['refresh_token']
            }
            if account.get('client_secret'):
                data['client_secret'] = account['client_secret']
            
            response = requests.post(self.TOKEN_URL, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Actualizar cuenta en memoria
                account['access_token'] = token_data.get('access_token')
                account['refresh_token'] = token_data.get('refresh_token')
                account['user_id'] = token_data.get('user_id') or account['user_id']
                
                expires_in = token_data.get('expires_in', 21600)
                account['expires_at'] = int(datetime.now().timestamp() + expires_in)
                
                self.save_tokens()
                print(f"[OK] Token refrescado para usuario {account['user_id']}")
                return True
            else:
                print(f"[ERROR] Falló refresh para user {account.get('user_id')}: {response.text}")
                return False
        except Exception as e:
            print(f"[ERROR] Excepción refresh: {e}")
            return False

    def _make_request(self, endpoint, account, method='GET', params=None, data=None):
        """Realiza una petición usando una cuenta específica"""
        if not account.get('access_token'):
            return {'error': 'No hay access token'}

        headers = {
            'Authorization': f'Bearer {account["access_token"]}',
            'Content-Type': 'application/json'
        }
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                response = requests.post(url, headers=headers, json=data, timeout=30)
            
            # Si expira, intentar refresh una vez
            if response.status_code == 401:
                print("[INFO] 401 Detectado. Intentando refresh...")
                if self.try_refresh_token(account):
                    headers['Authorization'] = f'Bearer {account["access_token"]}'
                    if method == 'GET':
                        response = requests.get(url, headers=headers, params=params, timeout=30)
                    else:
                        response = requests.post(url, headers=headers, json=data, timeout=30)
            
            # Si sigue siendo 401/403, devolver el error tal cual para que el llamador sepa
            if response.status_code in [401, 403]:
                return {'error': 'auth_error', 'details': response.json() if response.content else {}}
                
            return response.json()
            
        except Exception as e:
            return {'error': str(e)}

    def find_shipment(self, shipment_id, sender_id=None):
        """Busca el shipment probando cuentas o usando sender_id"""
        
        # 1. Si tenemos sender_id, intentar buscar esa cuenta
        if sender_id:
            sender_id = int(sender_id) if str(sender_id).isdigit() else sender_id
            for account in self.accounts:
                if account.get('user_id') == sender_id:
                    print(f"[INFO] Usando cuenta {sender_id} por coincidencia directa")
                    res = self._make_request(f"/shipments/{shipment_id}", account)
                    if 'error' not in res or res['error'] != 'auth_error':
                        return res, account
        
        # 2. Si no hay sender_id o falló la específica, probar todas (fuerza bruta inteligente)
        print("[INFO] Buscando envío en todas las cuentas...")
        for account in self.accounts:
            res = self._make_request(f"/shipments/{shipment_id}", account)
            
            # Si encontramos el shipment (status_code 200 implícito en json válido)
            if 'id' in res and str(res['id']) == str(shipment_id):
                print(f"[INFO] Envío encontrado en cuenta {account.get('user_id')}")
                return res, account
                
            # Si recibimos 'not_found' (404), seguimos buscando. 
            # Si recibimos 'auth_error', seguimos buscando.
            
        return {'error': 'Envío no encontrado en ninguna cuenta vinculada'}, None

    def get_full_shipment_info(self, shipment_id, sender_id=None):
        """Obtiene info completa usando la cuenta correcta"""
        result = {
            'shipment': None, 'order': None, 'items': None, 'errors': []
        }
        
        # 1. Encontrar el envío y la cuenta dueña
        shipment, account = self.find_shipment(shipment_id, sender_id)
        
        if not account or ('error' in shipment and 'id' not in shipment):
            msg = shipment.get('message') or shipment.get('error') or 'No encontrado'
            result['errors'].append(f"Shipment: {msg}")
            return result

        result['shipment'] = shipment
        
        # 2. Obtener Order
        order_id = shipment.get('order_id')
        if order_id:
            order = self._make_request(f"/orders/{order_id}", account)
            if 'id' in order:
                result['order'] = order
            else:
                result['errors'].append(f"Order: {order.get('message','Error')}")

        # 3. Obtener Items
        items = self._make_request(f"/shipments/{shipment_id}/items", account)
        if isinstance(items, list):
            result['items'] = items
        elif 'error' not in items: # A veces es un dict si hay error
             result['items'] = items # Asumimos éxito si no hay error explícito
        
        return result

    def get_credentials_status(self):
        """Retorna estado de las cuentas"""
        return {
            'accounts_count': len(self.accounts),
            'accounts': [
                {'user_id': acc.get('user_id'), 'has_token': bool(acc.get('access_token'))}
                for acc in self.accounts
            ]
        }
