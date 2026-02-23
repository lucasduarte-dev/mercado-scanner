from django.urls import path
from . import views

app_name = 'scanner'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/scan/', views.process_scan, name='process_scan'),
    path('api/scan/mark_return_complete/', views.mark_return_complete, name='mark_return_complete'),
    path('api/history/', views.scan_history, name='scan_history'),
    path('api/scan/<int:scan_id>/', views.scan_detail, name='scan_detail'),
]
