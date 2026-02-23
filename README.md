# Mercado Scanner

Sistema de escaneo y gestión de envíos en Mercado Libre con integración a Google Sheets.

## Características

- Escaneo de órdenes de Mercado Libre
- Actualización automática de estados de envíos
- Integración con Google Sheets para logging
- Detección de devoluciones y cambios de estado
- Reportes semanales automatizados

## Instalación Local

```bash
# Clonar repositorio
git clone <repo-url>
cd mercado_scanner

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar base de datos
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser
```

## Configuración

### Variables de Entorno
Crear archivo `.env` con:

```
DEBUG=False
SECRET_KEY=your-secret-key
DATABASE_URL=your-database-url
GOOGLE_SHEET_ID=your-sheet-id
```

### Credenciales de Google Sheets
1. Descargar `credentials.json` desde Google Cloud Console
2. Guardar en la raíz del proyecto

## Uso

### Ejecutar servidor local
```bash
python manage.py runserver
```

### Actualizar estados de envíos
```bash
python manage.py update_shipment_status
```

### Generar reporte semanal
```bash
python manage.py weekly_report
```

## Estructura del Proyecto

```
mercado_scanner/
├── scanner/              # App principal
│   ├── models.py        # Modelos de datos
│   ├── views.py         # Vistas
│   ├── ml_api.py        # API de Mercado Libre
│   ├── sheets_logger.py # Integración con Google Sheets
│   └── management/
│       └── commands/    # Comandos personalizados
├── mercado_scanner/     # Configuración Django
├── templates/           # Templates HTML
├── static/              # Archivos estáticos
└── tests/              # Tests
```

## Deployment en Railway

1. Conectar repositorio GitHub a Railway
2. Configurar variables de entorno en Railway dashboard
3. Railway detectará automáticamente `Procfile` y `runtime.txt`
4. Despliegue automático en cada push

## Licencia

Privado
