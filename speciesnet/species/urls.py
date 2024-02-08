from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginUser, name="login"),
    path('logout/', views.logoutUser, name="logout"), 
    path('register/', views.registerUser, name="register"), 
    path('', views.home, name="home"),
    path('aquarist/<str:pk>/', views.aquarist, name="aquarist"),
    path('species/<str:pk>/', views.species, name="species"), 
    path('speciesInstance/<str:pk>/', views.speciesInstance, name="speciesInstance"), 
    path('createSpecies/', views.createSpecies, name="createSpecies"),
    path('updateSpecies/<str:pk>/', views.updateSpecies, name="updateSpecies"),
    path('deleteSpecies/<str:pk>/', views.updateSpecies, name="updateSpecies"),
    #TODO refine SpeciesInstance creation - preselection of species required or editable in creation
    path('createSpeciesInstance/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('createSpeciesInstance//<str:pk>/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('updateSpeciesInstance/<str:pk>/', views.updateSpeciesInstance, name="updateSpeciesInstance"),
    path('deleteSpeciesInstance/<str:pk>/', views.deleteSpeciesInstance, name="deleteSpeciesInstance"),
    path('working/', views.working, name="working"),
]