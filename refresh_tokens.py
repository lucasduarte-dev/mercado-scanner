"""
Script para refrescar manualmente los tokens de ML
"""
import requests
import json
from pathlib import Path
from datetime import datetime, timezone

TOKEN_FILE = Path(__file__).parent / "meli_tokens.json"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

def refresh_account(account, idx):
    user_id = account.get("user_id")
    refresh_token = account.get("refresh_token")
    client_id = account.get("client_id")
    client_secret = account.get("client_secret")

    print(f"\n[{idx}] Refrescando cuenta user_id={user_id}...")

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(TOKEN_URL, data=data, timeout=15)
        result = response.json()

        if "access_token" in result:
            account["access_token"] = result["access_token"]
            account["refresh_token"] = result.get("refresh_token", refresh_token)
            account["expires_at"] = result.get("expires_in", 21600) + int(datetime.now(timezone.utc).timestamp())
            print(f"  OK - Token renovado para {user_id}")
            return True
        else:
            print(f"  ERROR - {result.get('message') or result.get('error') or result}")
            return False
    except Exception as e:
        print(f"  EXCEPCION - {e}")
        return False

if __name__ == "__main__":
    with open(TOKEN_FILE, "r") as f:
        accounts = json.load(f)

    changed = False
    for i, acc in enumerate(accounts, 1):
        ok = refresh_account(acc, i)
        if ok:
            changed = True

    if changed:
        with open(TOKEN_FILE, "w") as f:
            json.dump(accounts, f, indent=2)
        print("\nTokens guardados en meli_tokens.json")
    else:
        print("\nNo se pudo refrescar ningun token.")
