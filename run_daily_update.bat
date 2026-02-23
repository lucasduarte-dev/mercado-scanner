@echo off
REM Script para actualizar estados de envios y limpiar registros antiguos
REM Ejecutar manualmente o via Windows Task Scheduler

cd /d C:\Users\User\Desktop\mercado_scanner

echo ========================================
echo Actualizando estados de envios...
echo ========================================
echo.

python manage.py update_shipment_status

echo.
echo ========================================
echo Proceso completado
echo ========================================
echo.

pause
