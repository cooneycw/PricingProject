import uuid
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from PricingProject.settings import CONFIG_FRESH_PREFS
from .forms import GamePrefsForm
from .models import GamePrefs, IndivGames, Players


# Create your views here.
def home(request):
    title = 'Insurance Pricing Game: Home Page'
    context = dict()
    form = None
    if request.user.is_authenticated:
        # User is authenticated, perform your view logic here
        return redirect('Pricing-start')
    if request.POST:
        if request.POST.get('Sign Up') == "Sign Up":
            return redirect('register')

    context['title'] = title
    context['form'] = form
    return render(request, 'Pricing/home.html', context)


@login_required()
def start_game(request):
    title = 'Insurance Pricing Game: Start Game'
    template_name = 'Pricing/start_game.html'
    context = dict()
    form = None
    if request.POST.get('Individual') == 'Individual':
        return redirect('Pricing-individual')
    if request.POST:
        cwc = 0
    context['title'] = title
    context['form'] = form
    return render(request, template_name, context)


@login_required()
def individual(request):
    title = 'Insurance Pricing Game: Individual Game'
    template_name = 'Pricing/individual.html'
    context = dict()
    form = None

    initial_data = {}
    user = request.user

    if request.method == 'POST':
        form = GamePrefsForm(request.POST)
        if form.is_valid():
            game_prefs, created = GamePrefs.objects.update_or_create(
                user=user,
                defaults={
                    'sel_type_01': form.cleaned_data['sel_type_01'],
                    'sel_type_02': form.cleaned_data['sel_type_02'],
                    'sel_type_03': form.cleaned_data['sel_type_03'],
                    'game_observable': form.cleaned_data['game_observable'],
                }
            )

        if request.POST.get('Back to Game Select') == 'Back to Game Select':
            return redirect('Pricing-start')
        else:
            unique_game_id = str(uuid.uuid4())

            game, created = IndivGames.objects.update_or_create(
                game_id=unique_game_id,
                initiator=request.user,
                status="active",
                game_observable=game_prefs.game_observable,
            )

            next_player_id = 0
            Players.objects.update_or_create(
                game=game,
                player=str(request.user),
                player_id=next_player_id,
                player_type='user',
                profile='individual',
            )

            next_player_id += 1
            for i in range(int(game_prefs.sel_type_01)):
                Players.objects.create(
                    game=game,
                    player=f'growth_{i:02}',
                    player_id=next_player_id,
                    player_type='computer',
                    profile='growth',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_02)):
                Players.objects.create(
                    game=game,
                    player=f'profit_{int(game_prefs.sel_type_01) + i:02}',
                    player_id=next_player_id,
                    player_type='computer',
                    profile='profitability',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_03)):
                Players.objects.create(
                    game=game,
                    player=f'balanced_{int(game_prefs.sel_type_01) + int(game_prefs.sel_type_02) + i:02}',
                    player_id=next_player_id,
                    player_type='computer',
                    profile='balanced',
                )
                next_player_id += 1

            return redirect('Pricing-game_list')  # Redirect to a new page
    else:
        form = GamePrefsForm()

    context['form'] = form
    return render(request, template_name, context)


@login_required()
def game_list(request):
    title = 'Insurance Pricing Game: Individual Game List'
    template_name = 'Pricing/game_list.html'
    context = dict()
    form = None

    user = request.user
    active_games = IndivGames.objects.filter(initiator=user, status='active')
    accessible_games = [
        game for game in active_games if game.status in ['running', 'completed']
    ]

    context = {
        'active_games': active_games,
        'accessible_games': accessible_games,
    }
    return render(request, template_name, context)
