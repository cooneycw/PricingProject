from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='Pricing-home'),
    path('start/', views.start_game, name='Pricing-start'),
    path('individual/', views.individual, name='Pricing-individual'),
    path('group/', views.group, name='Pricing-group'),
    path('game_list/', views.game_list, name='Pricing-game_list'),
    path('game_dashboard/<str:game_key>/', views.game_dashboard, name='Pricing-game_dashboard'),
    path('join_group_game/<str:game_key>/', views.join_group_game, name='Pricing-join_group_game'),
    ]
