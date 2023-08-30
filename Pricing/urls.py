from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='Pricing-home'),
    path('start/', views.start_game, name='Pricing-start'),
    path('individual/', views.individual, name='Pricing-individual'),
    ]
