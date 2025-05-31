from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='Pricing-home'),
    path('start/', views.start_game, name='Pricing-start'),
    path('individual/', views.individual, name='Pricing-individual'),
    path('group/', views.group, name='Pricing-group'),
    path('game_list/', views.game_list, name='Pricing-game_list'),
    path('game_dashboard/<str:game_id>/', views.game_dashboard, name='Pricing-game_dashboard'),
    path('mktgsales_report/<str:game_id>/', views.mktgsales_report, name='Pricing-mktgsales_report'),
    path('industry_reports/<str:game_id>/', views.industry_reports, name='Pricing-industry_reports'),
    path('claim_devl_report/<str:game_id>/', views.claim_devl_report, name='Pricing-claim_devl_report'),
    path('claim_trend_report/<str:game_id>/', views.claim_trend_report, name='Pricing-claim_trend_report'),
    path('financials_report/<str:game_id>/', views.financials_report, name='Pricing-financials_report'),
    path('valuation_report/<str:game_id>/', views.valuation_report, name='Pricing-valuation_report'),
    path('decision_input/<str:game_id>/', views.decision_input, name='Pricing-decision_input'),
    path('decision_confirm/<str:game_id>/', views.decision_confirm, name='Pricing-decision_confirm'),
    path('join_group_game/<str:game_id>/', views.join_group_game, name='Pricing-join_group_game'),
    path('observe/', views.observe, name='Pricing-observe'),
    path('send_message/', views.send_message, name='send_message'),
    path('fetch_messages/', views.fetch_messages, name='fetch_messages'),
    path('fetch_game_list/', views.fetch_game_list, name='fetch_game_list'),
    ]
