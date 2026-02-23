# Guía de Deployment en Railway

## Prerequisitos

1. Cuenta en [Railway.app](https://railway.app)
2. Repositorio GitHub con el proyecto
3. Credenciales de Google Sheets (JSON)
4. Tokens de Mercado Libre

## Paso 1: Conectar Repositorio

1. Ir a Railway Dashboard
2. Click en "Create New" → "From GitHub repo"
3. Seleccionar `mercado-scanner`
4. Railway detectará automáticamente `Procfile` y `runtime.txt`

## Paso 2: Configurar Variables de Entorno

En Railway Dashboard, ir a "Variables" y agregar:

### Variables obligatorias:

```
SECRET_KEY=<generar-clave-aleatoria>
DEBUG=False
ALLOWED_HOSTS=<tu-app>.railway.app
```

### Base de Datos

Railway proporciona `DATABASE_URL` automáticamente cuando agregas PostgreSQL.

Para agregar PostgreSQL:
1. Click en "Add Service" → "PostgreSQL"
2. Se agregará automáticamente la variable `DATABASE_URL`

### Google Sheets

Agregar `GOOGLE_CREDENTIALS` con el contenido de tu `credentials.json`:

```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...",
  ...
}
```

**En una sola línea (importante para Railway):**
```
{"type":"service_account","project_id":"...","private_key":"..."}
```

Y la ID de la hoja:
```
GOOGLE_SHEET_ID=1obCJ9BY2hzBFziImhn7qLe0TKIKk3hw7Kszc1OFG5Bs
```

### Mercado Libre Tokens

Agregar `MELI_TOKENS` con el JSON de tokens:

```json
[
  {
    "access_token": "APP_USR-...",
    "refresh_token": "TG-...",
    "user_id": 123456789,
    "client_id": "...",
    "client_secret": "...",
    "expires_at": 1234567890
  }
]
```

**En una sola línea:**
```
[{"access_token":"APP_USR-...","refresh_token":"TG-...","user_id":123456789}]
```

## Paso 3: Deploy

Railway desplegará automáticamente en cada push a main.

### Ver logs:
Railway Dashboard → Deployment Logs

### Acceder a la app:
```
https://<tu-app>.railway.app
```

## Paso 4: Migraciones iniciales

Si es la primera vez, ejecutar migraciones:

1. Railway Dashboard → CLI
2. Ejecutar:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

O agregar webhook para ejecutar automáticamente.

## Troubleshooting

### Error: No se encuentra credentials.json

**Solución**: Asegúrate de haber configurado `GOOGLE_CREDENTIALS` en Railway.

### Error: No se encuentra meli_tokens.json

**Solución**: Asegúrate de haber configurado `MELI_TOKENS` en Railway.

### Error: DATABASE_URL not found

**Solución**: Agregar PostgreSQL service en Railway (ver Paso 2).

### Error: Application failed to initialize

1. Revisar logs en Railway Dashboard
2. Asegúrate de que todas las variables de entorno estén configuradas
3. Ejecutar migraciones si es necesario

## Local Development

Para testear localmente con las mismas configuraciones:

1. Copiar `.env.example` a `.env`
2. Editar `.env` con tus valores locales
3. Instalar dependencias: `pip install -r requirements.txt`
4. Migrar BD: `python manage.py migrate`
5. Correr: `python manage.py runserver`

## Production Checklist

- [ ] `DEBUG=False` en Railway
- [ ] `SECRET_KEY` configurado (diferente al local)
- [ ] `ALLOWED_HOSTS` incluye tu dominio de Railway
- [ ] PostgreSQL agregado como servicio
- [ ] `DATABASE_URL` configurado automáticamente
- [ ] `GOOGLE_CREDENTIALS` configurado
- [ ] `MELI_TOKENS` configurado
- [ ] Migraciones ejecutadas
- [ ] Superusuario creado
- [ ] Primero deployment exitoso

## URLs Útiles

- Dashboard: https://railway.app/dashboard
- Documentación: https://docs.railway.app
- Django en Railway: https://docs.railway.app/guides/django
