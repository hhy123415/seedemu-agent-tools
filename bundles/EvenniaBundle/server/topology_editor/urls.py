from django.urls import path
from . import views

urlpatterns = [
    path('topology/', views.index, name='topology-editor'),
    path('topology/data/', views.data, name='topology-editor-data'),
    path('topology/export/', views.export_document),
    path('topology/import-preview/', views.preview_import),
    path('topology/edit/', views.edit, name='topology-editor-edit'),
    path('topology/editor.js', views.javascript),
    path('topology/editor.css', views.stylesheet),
]
