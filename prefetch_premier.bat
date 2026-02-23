@echo off
REM Script para pre-cargar envios de Premier Mensajeria
REM Programar en Windows Task Scheduler a las 13:30 y 13:40

cd /d C:\Users\User\Desktop\mercado_scanner

echo ========================================
echo Pre-cargando envios de Premier...
echo ========================================
echo.

python manage.py prefetch_premier

echo.
echo ========================================
echo Pre-carga completada
echo ========================================
echo.

pause
