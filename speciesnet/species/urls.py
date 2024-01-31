from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('aquarist/<str:pk>/', views.aquarist, name="aquarist"), 
    path('species/<str:pk>/', views.species, name="species"), 
    path('speciesInstance/<str:pk>/', views.speciesInstance, name="speciesInstance"), 
    path('createSpecies/', views.createSpecies, name="createSpecies"),
    path('updateSpecies/<str:pk>/', views.updateSpecies, name="updateSpecies"),
    path('createSpeciesInstance/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('createSpeciesInstance//<str:pk>/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('updateSpeciesInstance/<str:pk>/', views.updateSpeciesInstance, name="updateSpeciesInstance"),
    path('deleteSpeciesObj/<str:pk>/', views.deleteSpeciesObj, name="deleteSpeciesObj"),
]