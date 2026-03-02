# 📦 Scanner Mercado Envíos - Guía del Sistema

## ¿Qué es?

Una app web que se usa desde el celular para escanear los códigos QR de los paquetes.
Cuando escaneás un paquete, te dice al toque si está **vigente**, **cancelado** o si es una **devolución**.
Todo queda guardado en la base de datos y en Google Sheets automáticamente.

---

## ¿Cómo funciona?

1. Abrís la app desde el celu (con el link de ngrok)
2. Elegís quién escanea (Jose, Fede, Gonza, etc.)
3. Apuntás la cámara al QR del paquete
4. La app te muestra el resultado con sonido y color:
   - 🟢 **VIGENTE** → todo bien
   - 🔴 **CANCELADO** → no entregar
   - 🟠 **DEVOLUCIÓN** → hay que devolver
   - 🟡 **YA ESCANEADO** → duplicado

---

## Tipos de paquetes

- **Flex** → Paquetes de Mercado Libre, se consultan por API
- **Mensajería (Premier)** → Paquetes de Premier Mensajeria, se buscan en su web
- **Regresos** → Paquetes que vuelven al depósito, se marcan con el botón "Escanear Regreso"

---

## Caché de Premier (lo nuevo)

Para no tener que esperar que abra el navegador cada vez que escaneás un paquete de Premier,
el sistema pre-carga todos los envíos del día **antes** de que empiecen a escanear.

- Se ejecuta automáticamente a las **13:30** y **13:40** (con Task Scheduler)
- Cuando escaneás un QR de Premier, busca primero en el caché → **instantáneo**
- Si por alguna razón no está en el caché, abre el navegador como backup

---

## Tareas automáticas programadas

Estas tareas se configuran en el **Programador de Tareas de Windows** (Task Scheduler):

| Tarea | Horario | Qué hace | Archivo |
|-------|---------|----------|---------|
| Pre-cargar Premier | 13:30 y 13:40 | Carga los envíos de Premier en caché | `prefetch_premier.bat` |
| Actualizar estados | 23:00 | Recorre los escaneos del día y actualiza estados en BD y Sheets | `run_daily_update.bat` |
| Reporte semanal | Lunes | Genera el resumen de la semana en Sheets | `reporte_semanal.bat` |

**Importante:** Si movés el proyecto a otra PC, las tareas hay que crearlas de nuevo en el Task Scheduler de esa PC.

---

## Inicio automático

Todo se levanta con **un solo archivo**: `inicio_deposito.bat`

Ese archivo arranca:
1. El servidor de Mercado Scanner (puerto 8004)
2. El servidor de Sistema 3D Insumos (puerto 8005)
3. Los túneles de Cloudflare
4. El Router Flask (que conecta todo)
5. Ngrok (para el link fijo del celular)

Solo hay que hacer **doble click** en el bat y listo, todo funciona.

⚠️ **No cerrar las ventanas** que se abren, si cerrás alguna se cae esa parte del sistema.

---

## Si falla algo

### "No module named X"
Falta instalar alguna dependencia. Correr:
```
python -m pip install -r requirements.txt
```

### "Executable doesn't exist" (Playwright)
Falta descargar el navegador:
```
python -m playwright install chromium
```

### Los escaneos no llegan a Sheets
Correr el sincronizador manual:
```
python manage.py sync_to_sheets
```
Solo sube los que faltan, no duplica.

### Mover a otra PC
1. Clonar con `git clone`
2. Instalar dependencias: `python -m pip install -r requirements.txt`
3. Instalar navegador: `python -m playwright install chromium`
4. Crear base de datos: `python manage.py migrate`
5. Crear admin: `python manage.py createsuperuser`
6. Copiar `meli_tokens.json` y `credentials.json` manualmente
7. Configurar las tareas en el Task Scheduler
8. Ajustar las rutas en los `.bat` si la carpeta cambió

---

## Archivos importantes (no se suben a Git)

| Archivo | Qué tiene | Qué hacer si falta |
|---------|-----------|-------------------|
| `db.sqlite3` | Base de datos con todos los escaneos | `python manage.py migrate` + `createsuperuser` |
| `meli_tokens.json` | Tokens de las cuentas de Mercado Libre | Copiar de la otra PC |
| `credentials.json` | Credenciales de Google Sheets | Copiar de la otra PC |

---

## Acceso

- **Local**: `http://localhost:8004`
- **Admin Django**: `http://localhost:8004/admin`
- **Desde el celular**: Usar el link de ngrok (fijo, no cambia)
