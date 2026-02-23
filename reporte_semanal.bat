@echo off
cd /d C:\Users\User\Desktop\mercado_scanner
python manage.py weekly_report >> logs\weekly_report.log 2>&1
echo.
echo Reporte ejecutado el %date% a las %time% >> logs\weekly_report.log
