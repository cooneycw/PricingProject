import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Case, When, Value, CharField, Max
from datetime import timedelta
from PricingProject.settings import CONFIG_FRESH_PREFS, CONFIG_MAX_HUMAN_PLAYERS
from .forms import GamePrefsForm
from .models import GamePrefs, IndivGames, Players, ChatMessage


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
    title = ': Start Game'
    template_name = 'Pricing/start_game.html'
    context = dict()
    form = None
    if request.POST.get('Individual') == 'Individual':
        return redirect('Pricing-individual')
    if request.POST.get('Re-Join') == 'Re-Join':
        return redirect('Pricing-game_list')
    if request.POST.get('Group') == 'Group':
        return redirect('Pricing-group')
    if request.POST.get('Observe') == 'Observe':
        return redirect('Pricing-observe')

    context['title'] = title
    context['form'] = form
    return render(request, template_name, context)


@login_required()
def individual(request):
    title = 'Insurance Pricing Game: Individual Game'
    template_name = 'Pricing/individual.html'
    context = dict()
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
        if request.POST.get('Start Game') == 'Start Game':
            unique_game_id = str(uuid.uuid4())

            game, created = IndivGames.objects.update_or_create(
                game_id=unique_game_id,
                initiator=request.user,
                initiator_name=str(request.user),
                status="active",
                game_observable=game_prefs.game_observable,
            )

            next_player_id = 0
            Players.objects.update_or_create(
                game=game,
                player_id=request.user,
                player_name=str(request.user),
                player_id_display=next_player_id,
                player_type='user',
                profile='individual',
            )

            next_player_id += 1
            for i in range(int(game_prefs.sel_type_01)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'growth_{i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='growth',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_02)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'profit_{int(game_prefs.sel_type_01) + i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='profitability',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_03)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'balanced_{int(game_prefs.sel_type_01) + int(game_prefs.sel_type_02) + i:02}',
                    player_id_display=next_player_id,
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
def group(request):
    title = 'Insurance Pricing Game: Game List'
    template_name = 'Pricing/group.html'
    context = dict()
    user = request.user

    all_games_annotated = IndivGames.objects.annotate(
        game_type=Case(
            When(human_player_cnt=1, then=Value('individual')),
            default=Value('group'),
            output_field=CharField(),
        )
    )

    # Now filter based on annotations
    accessible_games = all_games_annotated.exclude(
        initiator=user
    ).filter(
        game_type='group',
        status='waiting for players'
    ).order_by('-timestamp').annotate(
        current_human_player_cnt=Count(
            'players',
            filter=Q(players__profile='group'))
    )

    accessible_games = accessible_games.annotate(
        current_human_player_cnt=Count(
            'players',
            filter=Q(players__profile='group')))

    for game in accessible_games:
        game.additional_players_needed = game.human_player_cnt - game.current_human_player_cnt


    if request.method == 'POST':
        form = GamePrefsForm(request.POST)
        if form.is_valid():
            game_prefs, created = GamePrefs.objects.update_or_create(
                user=user,
                defaults={
                    'human_player_cnt': form.cleaned_data['human_player_cnt'],
                    'sel_type_01': form.cleaned_data['sel_type_01'],
                    'sel_type_02': form.cleaned_data['sel_type_02'],
                    'sel_type_03': form.cleaned_data['sel_type_03'],
                    'game_observable': form.cleaned_data['game_observable'],
                }
            )

        if request.POST.get('Back to Game Select') == 'Back to Game Select':
            return redirect('Pricing-start')
        if request.POST.get('Initiate Group Game') == 'Initiate Group Game':
            unique_game_id = str(uuid.uuid4())

            game, created = IndivGames.objects.update_or_create(
                game_id=unique_game_id,
                initiator=request.user,
                initiator_name=str(request.user),
                status="waiting for players",
                human_player_cnt=game_prefs.human_player_cnt,
                game_observable=game_prefs.game_observable,
            )

            next_player_id = 0
            Players.objects.update_or_create(
                game=game,
                player_id=request.user,
                player_name=str(request.user),
                player_id_display=next_player_id,
                player_type='user',
                profile='group',
            )

            next_player_id += 1
            for i in range(int(game_prefs.sel_type_01)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'growth_{i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='growth',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_02)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'profit_{int(game_prefs.sel_type_01) + i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='profitability',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_03)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'balanced_{int(game_prefs.sel_type_01) + int(game_prefs.sel_type_02) + i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='balanced',
                )
                next_player_id += 1

            return redirect('Pricing-game_list')  # Redirect to a new page
    else:
        form = GamePrefsForm()

    context['form'] = form
    context['accessible_games'] = accessible_games
    return render(request, template_name, context)


@login_required()
def game_list(request):
    title = 'Insurance Pricing Game: Game List'
    template_name = 'Pricing/game_list.html'
    context = dict()
    user = request.user
    player_game_ids = Players.objects.filter(player_id=user).values_list('game', flat=True)

    all_games = IndivGames.objects.filter(
        Q(initiator=user) | Q(game_id__in=player_game_ids)
    ).order_by('-timestamp').annotate(
        game_type=Case(
            When(human_player_cnt=1, then=Value('individual')),
            default=Value('group'),
            output_field=CharField(),
        )
    )

    all_games = all_games.annotate(
        current_human_player_cnt=Count(
            'players',
            filter=Q(players__profile='group')))

    for game in all_games:
        game.additional_players_needed = game.human_player_cnt - game.current_human_player_cnt

    active_games = [
        game for game in all_games if game.status in ['active', 'waiting for players']
    ]
    accessible_games = [
        game for game in all_games if game.status in ['running', 'completed']
    ]

    if request.POST.get('Back to Game Select') == 'Back to Game Select':
        return redirect('Pricing-start')

    context = {
        'active_games': active_games,
        'accessible_games': accessible_games,
    }
    return render(request, template_name, context)


@transaction.atomic()
@login_required()
def join_group_game(request, game_id):
    title = 'Insurance Pricing Game: Join Group Game'
    template_name = 'Pricing/join_group_game.html'
    context = dict()
    user = request.user

    game = get_object_or_404(IndivGames, game_id=game_id)

    current_players = Players.objects.filter(game=game, player_type__in=['user', 'human']).count()
    game.additional_players_needed = game.human_player_cnt - current_players

    if game.status in ['active', 'running', 'completed'] or \
        current_players >= game.human_player_cnt:
        messages.warning(request, "This game is either full or cannot be joined.  Create / select another game.")
        return redirect('Pricing-group')

    if request.method == "POST":
        if request.POST.get('Back to Group Game Select') == 'Back to Group Game Select':
            redirect('Pricing-group')
        if request.POST.get('Confirm Game Join'):
            max_display_id = Players.objects.filter(game=game).aggregate(Max('player_id_display'))[
                'player_id_display__max']

            next_display_id = (max_display_id + 1)

            Players.objects.create(
                game=game,
                player_id=request.user,
                player_name=request.user.username,
                player_id_display=next_display_id,
                player_type='human',  # Or 'user', based on your requirements
                profile='group'
            )

            current_players = Players.objects.filter(game=game, player_type__in=['user', 'human']).count()
            if current_players >= game.human_player_cnt:
                game.status = 'active'
                game.save()

            messages.success(request, "Successfully added to group game.")
            return redirect('Pricing-game_list')
    context['game'] = game
    return render(request, template_name, context)


@login_required()
def observe(request):
    title = 'Insurance Pricing Game: Observe Game'
    template_name = 'Pricing/observe.html'
    context = dict()
    user = request.user
    all_games = IndivGames.objects.filter(
        game_observable=True,
        status__in=['running', 'completed']
    ).order_by('-timestamp').annotate(
        game_type=Case(
            When(human_player_cnt=1, then=Value('individual')),
            default=Value('group'),
            output_field=CharField(),
        )
    )

    # All accessible (observable) games
    accessible_games = [game for game in all_games]

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Game Select') == 'Back to Game Select':
        return redirect('Pricing-start')

    # Populate the context and render the template
    context = {
        'accessible_games': accessible_games,
    }
    return render(request, template_name, context)


@login_required()
def game_dashboard(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))
    template_name = 'Pricing/dashboard.html'
    context = {
        'title': ' - Dashboard',
        'game': game,
    }
    return render(request, template_name, context)


@login_required
@csrf_exempt
def send_message(request):
    if request.method == 'POST':
        game_id = request.POST.get('game_id')  # Get game_id from POST data
        content = request.POST.get('message')
        from_user = request.user

        message = ChatMessage(
            from_user=from_user,
            game_id=IndivGames.objects.get(game_id=game_id),
            content=content
        )
        message.save()

        return JsonResponse({"message": content})


@login_required
def fetch_messages(request):
    if request.method == 'GET':
        game_id = request.GET.get('game_id')
        latest_sequence = int(request.GET.get('latest_sequence', 0))

        messages = ChatMessage.objects.filter(
            game_id=game_id,
            sequence_number__gt=latest_sequence
        ).order_by('sequence_number')[:50]

        message_list = []
        for msg in messages:
            # Perform timezone conversion to Django's default timezone
            timestamp_with_timezone = timezone.localtime(msg.timestamp)

            message_list.append({
                'from_sender': msg.from_user.username,
                'time': timestamp_with_timezone.strftime('%Y-%m-%d %H:%M:%S'),
                'content': msg.content,
                'sequence_number': msg.sequence_number
            })

        return JsonResponse({"messages": message_list})
