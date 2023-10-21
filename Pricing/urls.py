from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='Pricing-home'),
    path('start/', views.start_game, name='Pricing-start'),
    path('individual/', views.individual, name='Pricing-individual'),
    path('group/', views.group, name='Pricing-group'),
    path('game_list/', views.game_list, name='Pricing-game_list'),
    path('game_dashboard/<str:game_id>/', views.game_dashboard, name='Pricing-game_dashboard'),
    path('written_premium_report/<str:game_id>/', views.written_premium_report, name='Pricing-written_premium_report'),
    path('join_group_game/<str:game_id>/', views.join_group_game, name='Pricing-join_group_game'),
    path('observe/', views.observe, name='Pricing-observe'),
    path('send_message/', views.send_message, name='send_message'),
    path('fetch_messages/', views.fetch_messages, name='fetch_messages'),
    ]
