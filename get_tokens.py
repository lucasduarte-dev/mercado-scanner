import requests

import json
from urllib.parse import urlencode

# Configuración por defecto (puedes cambiarlas o dejar que el script pregunte)
DEFAULT_REDIRECT_URI = "https://3dinsumos.com.ar/"  # URL válida configurada en tu App de ML

def get_tokens():
    print("=== Generador de Tokens Mercado Libre ===")
    print("Este script te ayudará a obtener Access y Refresh Tokens para tus cuentas.\n")

    app_id = input("Ingresa tu App ID (Client ID): ").strip()
    client_secret = input("Ingresa tu Client Secret: ").strip()
    
    # Construir URL de autorización
    params = {
        'response_type': 'code',
        'client_id': app_id,
        'redirect_uri': DEFAULT_REDIRECT_URI
    }
    auth_url = f"https://auth.mercadolibre.com.ar/authorization?{urlencode(params)}"
    
    print(f"\nURL de autorización: {auth_url}")
    print("Visita el enlace anterior si necesitas obtener el código, luego pega la URL de redirección abajo.")
    
    redirected_url = input("\nPega la URL completa aquí: ").strip()
    
    # Extraer el código ("code=")
    try:
        if "code=" in redirected_url:
            code = redirected_url.split("code=")[1].split("&")[0]
        else:
            print("❌ No se encontró el código en la URL. Asegúrate de copiarla completa.")
            return
    except:
        print("❌ Error procesando la URL.")
        return

    print(f"\nCódigo detectado: {code}")
    print("Intercambiando código por tokens...")
    
    # Intercambiar código por token
    token_url = "https://api.mercadolibre.com/oauth/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': app_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': DEFAULT_REDIRECT_URI
    }
    
    try:
        response = requests.post(token_url, data=data)
        if response.status_code == 200:
            token_data = response.json()
            
            # Agregar el secret manualmente para que nuestra app funcione
            token_data['client_secret'] = client_secret
            token_data['client_id'] = app_id
            
            print("\n✅ ¡Tokens obtenidos con éxito!\n")
            print("Copia el siguiente bloque y agrégalo a tu lista en meli_tokens.json (agrega una coma si es necesario):")
            print("-" * 50)
            print(json.dumps(token_data, indent=2))
            print("-" * 50)
        else:
            print(f"\n❌ Error obteniendo tokens: {response.text}")
            
    except Exception as e:
        print(f"\n❌ Excepción: {e}")

if __name__ == "__main__":
    get_tokens()
