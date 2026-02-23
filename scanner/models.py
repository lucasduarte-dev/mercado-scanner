from django.db import models
from django.utils import timezone


class Scan(models.Model):
    """Registro de escaneos de QR/códigos de barras"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('success', 'Exitoso'),
        ('error', 'Error'),
    ]

    # Datos del QR escaneado
    shipment_id = models.CharField(max_length=50)
    sender_id = models.CharField(max_length=50, blank=True, null=True)
    hash_code = models.TextField(blank=True, null=True)
    security_digit = models.CharField(max_length=10, blank=True, null=True)
    raw_qr_data = models.TextField(help_text="JSON raw del QR escaneado")

    # Datos de la API de Mercado Libre
    api_response = models.JSONField(blank=True, null=True, help_text="Respuesta completa de la API")
    
    # Nuevos campos Scanner 2.0
    scanner_user = models.CharField(max_length=50, blank=True, null=True, help_text="Nombre de quien escaneó (Jose, Fede, etc)")
    is_cancelled = models.BooleanField(default=False)

    order_id = models.CharField(max_length=50, blank=True, null=True)
    buyer_nickname = models.CharField(max_length=100, blank=True, null=True)
    shipment_status = models.CharField(max_length=50, blank=True, null=True, help_text="Estado del envío físico")
    order_status = models.CharField(max_length=50, blank=True, null=True, help_text="Estado del pedido/orden")
    shipping_mode = models.CharField(max_length=20, blank=True, null=True, help_text="flex, me2, mensajeria")
    
    # Campos para seguimiento de estado
    initial_status = models.CharField(max_length=50, blank=True, null=True, help_text="Estado del pedido al momento del escaneo (ESTADO DE RETIRO)")
    current_status = models.CharField(max_length=50, blank=True, null=True, help_text="Estado del pedido actual (ESTADO ACTUAL - actualizado diariamente)")
    last_status_check = models.DateTimeField(blank=True, null=True, help_text="Última vez que se verificó el estado")
    
    # Campos para logística externa (Premier Mensajeria)
    is_logistics = models.BooleanField(default=False, help_text="Es de logística externa (no ML)")
    logistics_type = models.CharField(max_length=20, blank=True, null=True, help_text="Tipo: PARTICULAR o CAMBIO")
    logistics_customer_name = models.CharField(max_length=200, blank=True, null=True, help_text="Nombre completo del cliente")
    logistics_data = models.JSONField(blank=True, null=True, help_text="Datos completos del QR de logística")
    
    # Campo para tracking de devoluciones/cambios
    scan_count = models.IntegerField(default=1, help_text="Número de veces que se escaneó este código (para detectar 3er escaneo)")
    
    # Metadatos
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scanned_at']
        verbose_name = 'Scan'
        verbose_name_plural = 'Scans'

    def __str__(self):
        return f"Scan {self.shipment_id} - {self.status}"
