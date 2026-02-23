from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Scan, PremierShipmentCache

class TipoEnvioFilter(admin.SimpleListFilter):
    title = _('Tipo de Envío')
    parameter_name = 'tipo_envio'

    def lookups(self, request, model_admin):
        return (
            ('flex', _('FLEX (Mercado Libre)')),
            ('cambio', _('CAMBIOS (Premier)')),
            ('particular', _('PARTICULARES (Premier)')),
            ('me2', _('Mercado Envíos (ME2)')),
            ('mensajeria', _('Mensajería (Otros)')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'flex':
            return queryset.filter(shipping_mode='flex')
        if self.value() == 'cambio':
            return queryset.filter(is_logistics=True, logistics_type__iexact='CAMBIO')
        if self.value() == 'particular':
            return queryset.filter(is_logistics=True, logistics_type__iexact='PARTICULAR')
        if self.value() == 'me2':
            return queryset.filter(shipping_mode='me2')
        if self.value() == 'mensajeria':
            return queryset.filter(shipping_mode='mensajeria').exclude(is_logistics=True)

class EstadoGeneralFilter(admin.SimpleListFilter):
    title = _('Estado General')
    parameter_name = 'estado_general'

    def lookups(self, request, model_admin):
        return (
            ('vigente', _('Vigente')),
            ('cancelado', _('Cancelado')),
            ('devolucion', _('Devolución')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'vigente':
            return queryset.exclude(is_cancelled=True).exclude(current_status__icontains='returned').exclude(current_status='cancelled')
        if self.value() == 'cancelado':
            return queryset.filter(is_cancelled=True) | queryset.filter(current_status='cancelled')
        if self.value() == 'devolucion':
            return queryset.filter(current_status__icontains='returned')

@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ('shipment_id', 'get_tipo_display', 'scanned_at', 'get_status_display', 'scanner_user')
    list_filter = (TipoEnvioFilter, EstadoGeneralFilter, 'scanned_at', 'status', 'scanner_user')
    search_fields = ('shipment_id', 'sender_id', 'order_id', 'logistics_customer_name', 'buyer_nickname')
    ordering = ('-scanned_at',)
    
    def get_tipo_display(self, obj):
        if obj.shipping_mode == 'flex':
            return 'FLEX'
        if obj.is_logistics:
            return f"{obj.logistics_type or 'MENSAJERIA'} (Premier)"
        return obj.shipping_mode or 'ME2'
    get_tipo_display.short_description = 'Tipo'
    
    def get_status_display(self, obj):
        if obj.current_status == 'returned' or (obj.current_status and 'returned' in obj.current_status):
            return 'DEVOLUCIÓN'
        if obj.is_cancelled or obj.current_status == 'cancelled':
            return 'CANCELADO'
        return obj.current_status or 'VIGENTE'
    get_status_display.short_description = 'Estado'


@admin.register(PremierShipmentCache)
class PremierShipmentCacheAdmin(admin.ModelAdmin):
    list_display = ('did', 'customer_name', 'tipo', 'fetched_at', 'used')
    list_filter = ('tipo', 'used', 'fetched_at')
    search_fields = ('did', 'customer_name')
    ordering = ('-fetched_at',)
