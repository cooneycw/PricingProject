import uuid
import copy
import pytz
import numpy as np
import pandas as pd
import decimal
from .utils import reverse_pv_index, calculate_growth_rate, calculate_avg_profit, calculate_future_value, perform_logistic_regression, perform_logistic_regression_indication
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Case, When, Value, CharField, Max, Sum, Exists, Min, F, OuterRef, Subquery
from datetime import timedelta
from PricingProject.settings import CONFIG_FRESH_PREFS
from .forms import GamePrefsForm
from .models import GamePrefs, IndivGames, Players, MktgSales, Financials, Industry, Valuation, Triangles, ClaimTrends, Indications, Decisions, ChatMessage, Lock
pd.set_option('display.max_columns', None)  # None means show all columns


def get_force_term(game):
    """Helper function to return 'Customers' for Novice games, 'In-Force' otherwise"""
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            return 'Customers'
    except GamePrefs.DoesNotExist:
        pass
    return 'In-Force'


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
        if request.POST.get('Back to Game Select') == 'Back to Game Select':
            return redirect('Pricing-start')

        if form.is_valid():
            total_companies = sum(int(form.cleaned_data[field]) for field in ['sel_type_01', 'sel_type_02', 'sel_type_03'])

            if total_companies < 5:
                messages.warning(request, "You must select at least 5 CPU companies in total.")
                context['form'] = form
                return render(request, template_name, context)

            game_prefs, created = GamePrefs.objects.update_or_create(
                user=user,
                defaults={
                    'sel_type_01': form.cleaned_data['sel_type_01'],
                    'sel_type_02': form.cleaned_data['sel_type_02'],
                    'sel_type_03': form.cleaned_data['sel_type_03'],
                    'game_observable': form.cleaned_data['game_observable'],
                    'default_selection_type': form.cleaned_data['default_selection_type'],
                    'game_difficulty': form.cleaned_data['game_difficulty'],  # Added game_difficulty
                }
            )

        if request.POST.get('Start Game') == 'Start Game':
            unique_game_id = str(uuid.uuid4())

            game, created = IndivGames.objects.update_or_create(
                game_id=unique_game_id,
                initiator=request.user,
                initiator_name=str(request.user),
                status="active",
                game_observable=game_prefs.game_observable,
            )

            user_profile = form.cleaned_data['default_selection_type']
            if user_profile == 'Balanced':
                profile_type = 'balanced'
            elif user_profile == 'Growth':
                profile_type = 'growth'
            elif user_profile == 'Profit':
                profile_type = 'profitability'

            next_player_id = 0
            Players.objects.update_or_create(
                game=game,
                player_id=request.user,
                player_name=str(request.user),
                player_id_display=next_player_id,
                player_type='user',
                profile=profile_type,
            )

            next_player_id += 1
            for i in range(int(game_prefs.sel_type_01)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'growth_{i + 1:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='growth',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_02)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'profit_{int(game_prefs.sel_type_01) + i + 1:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='profitability',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_03)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'balanced_{int(game_prefs.sel_type_01) + int(game_prefs.sel_type_02) + i + 1:02}',
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
    user = request.user
    context = dict()
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
            filter=Q(players__player_type='user'))
    )

    accessible_games = accessible_games.annotate(
        current_human_player_cnt=Count(
            'players',
            filter=Q(players__player_type='user')))

    for game in accessible_games:
        game.additional_players_needed = game.human_player_cnt - game.current_human_player_cnt
        # Add game difficulty information
        try:
            game_prefs = GamePrefs.objects.get(user=game.initiator)
            game.difficulty = game_prefs.game_difficulty
        except GamePrefs.DoesNotExist:
            game.difficulty = 'Expert'  # Default to Expert if no preferences found

    if request.method == 'POST':
        form = GamePrefsForm(request.POST)
        if form.is_valid():
            total_companies = sum(int(form.cleaned_data[field]) for field in ['human_player_cnt', 'sel_type_01', 'sel_type_02', 'sel_type_03'])
            human_companies = sum(int(form.cleaned_data[field]) for field in ['human_player_cnt'])
            if human_companies < 2:
                messages.warning(request, "You must select at least two human players.")
                context['form'] = form
                return render(request, template_name, context)
            if total_companies < 6:
                messages.warning(request, "You must select at least 6 companies in total (including humans).")
                context['form'] = form
                return render(request, template_name, context)

            game_prefs, created = GamePrefs.objects.update_or_create(
                user=user,
                defaults={
                    'human_player_cnt': form.cleaned_data['human_player_cnt'],
                    'sel_type_01': form.cleaned_data['sel_type_01'],
                    'sel_type_02': form.cleaned_data['sel_type_02'],
                    'sel_type_03': form.cleaned_data['sel_type_03'],
                    'game_observable': form.cleaned_data['game_observable'],
                    'default_selection_type': form.cleaned_data['default_selection_type'],
                    'game_difficulty': form.cleaned_data['game_difficulty'],
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

            user_profile = form.cleaned_data['default_selection_type']
            if user_profile == 'Balanced':
                profile_type = 'balanced'
            elif user_profile == 'Growth':
                profile_type = 'growth'
            elif user_profile == 'Profit':
                profile_type = 'profitability'

            next_player_id = 0
            Players.objects.update_or_create(
                game=game,
                player_id=request.user,
                player_name=str(request.user),
                player_id_display=next_player_id,
                player_type='user',
                profile=profile_type,
            )

            next_player_id += 1
            for i in range(int(game_prefs.sel_type_01)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'growth_{1 + i:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='growth',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_02)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'profit_{int(game_prefs.sel_type_01) + i + 1:02}',
                    player_id_display=next_player_id,
                    player_type='computer',
                    profile='profitability',
                )
                next_player_id += 1

            for i in range(int(game_prefs.sel_type_03)):
                Players.objects.create(
                    game=game,
                    player_id=None,
                    player_name=f'balanced_{int(game_prefs.sel_type_01) + int(game_prefs.sel_type_02) + i + 1:02}',
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
            filter=Q(players__player_type='user')))

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
    user = request.user

    game = get_object_or_404(IndivGames, game_id=game_id)

    current_players = Players.objects.filter(game=game, player_type__in=['user']).count()
    initiator_name = IndivGames.objects.filter(game_id=game_id).first().initiator
    profile = Players.objects.filter(game=game_id, player_name=initiator_name).first().profile
    game.additional_players_needed = game.human_player_cnt - current_players

    if game.status in ['active', 'running', 'completed'] or \
        current_players >= game.human_player_cnt:
        messages.warning(request, "This game is either full or cannot be joined.  Create / select another game.")
        return redirect('Pricing-group')

    if request.method == "POST":
        if request.POST.get('Back to Group Game Select') == 'Back to Group Game Select':
            return redirect('Pricing-group')
        if request.POST.get('Confirm Game Join'):
            max_display_id = Players.objects.filter(game=game).aggregate(Max('player_id_display'))[
                'player_id_display__max']

            next_display_id = (max_display_id + 1)

            Players.objects.create(
                game=game,
                player_id=request.user,
                player_name=request.user.username,
                player_id_display=next_display_id,
                player_type='user',  # Or 'user', based on your requirements
                profile=profile
            )

            current_players = Players.objects.filter(game=game, player_type__in=['user']).count()
            if current_players >= game.human_player_cnt:
                game.status = 'active'
                game.save()

            messages.success(request, "Successfully added to group game.")
            return redirect('Pricing-game_list')
    context = dict()
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
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")
    decisions_obj = Decisions.objects.filter(game_id=game, player_id=user)

    unique_years = decisions_obj.order_by('-year').values_list('year', flat=True).distinct()
    latest_year = unique_years[0] if unique_years else None
    current_datetime = None
    target_datetime = None
    decisions_frozen = True

    is_novice_game = False  # Default to not Novice
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass # Keep is_novice_game as False if prefs not found

    if unique_years:  # Proceed if there are any financial years available
        # Querying the database
        decisions_data_list = list(decisions_obj.values('year', 'decisions_game_stage', 'decisions_time_stamp', 'decisions_locked'))

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(decisions_data_list)

        if not df.empty:
            # Filter out only the rows belonging to the latest four years
            latest_df = df[df['year'] == latest_year]

            if latest_df['decisions_game_stage'].values[0] == 'decisions':
                if not latest_df['decisions_locked'].values[0]:
                    decisions_frozen = False
                    target_datetime = latest_df['decisions_time_stamp'].values[0]['future_time']
                    current_datetime = latest_df['decisions_time_stamp'].values[0]['current_time']
                else:
                    pass
            else:
                pass

    template_name = 'Pricing/dashboard.html'
    green_list = ['Government officials', 'Injury reform', 'product reform', 'after observing']
    orange_list = ['Regulatory']
    purple_list = ['OSFI']

    context = {
        'title': ' - Dashboard',
        'game': game,
        'current_datetime': current_datetime,
        'target_datetime': target_datetime,
        'decisions_frozen': decisions_frozen,
        'green_list': green_list,
        'orange_list': orange_list,
        'purple_list': purple_list,
        'is_novice_game': is_novice_game, # Add to context
    }

    return render(request, template_name, context)


@login_required()
def mktgsales_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    financial_data = MktgSales.objects.filter(game_id=game, player_id=user)
    unique_years = financial_data.order_by('-year').values_list('year', flat=True).distinct()
    latest_year = unique_years[0] if unique_years else None
    template_name = 'Pricing/mktgsales_report.html'

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.GET.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    is_novice_game = False  # Default to not Novice
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass # Keep is_novice_game as False if prefs not found

    chart_data = None
    # Determine initial styles based on game difficulty
    if is_novice_game:
        initial_chart_style = "display: block;"
        initial_table_style = "display: none;"
    else:
        initial_chart_style = "display: none;"
        initial_table_style = "display: block;"

    if unique_years:  # Proceed if there are any financial years available
        # Querying the database
        financial_data_list = list(
            financial_data.values('year', 'beg_in_force',
                                  'mktg_expense', 'mktg_expense_ind', 'avg_prem',
                                  'quotes', 'sales', 'canx', 'end_in_force', 'in_force_ind'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(financial_data_list)

        if not df.empty:
            if selected_year not in unique_years:
                selected_year = latest_year
                # Filter out only the rows belonging to the latest four years
            all_data_years = df['year'].unique()  # Get all unique years
            all_data_years = sorted(all_data_years, reverse=True)  # Sort and pick the latest four years
            
            # For the HTML table (latest 4 years up to selected_year)
            selected_years_table = sorted([yr for yr in all_data_years if yr <= selected_year], reverse=True)[:4]
            # For the chart (latest 20 years up to selected_year)
            chart_selected_years = sorted([yr for yr in all_data_years if yr <= selected_year], reverse=True)[:20]

            df = df.sort_values('year', ascending=False)

            # Creating a copy of the filtered DataFrame for the TABLE
            df_latest_table = df[df['year'].isin(selected_years_table)].copy()

            # Transposing the DataFrame to get years as columns and metrics as rows (for TABLE)
            transposed_df = df_latest_table.set_index('year').T  # Set 'year' as index before transposing
            percentage_data = {}
            close_ratio_data = {}
            retention_ratio_data = {}
            mkt_share_ratio_data = {}
            # Now, we'll go through each row in the transposed DataFrame, rename it, and apply specific formatting
            for index, row in transposed_df.iterrows():
                if index == 'beg_in_force':
                    # Rename and format the 'written_premium' row
                    new_row_name = f'Beginning-{get_force_term(game)}'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"{int(x):,}")  # formatting as currency without decimals
                elif index == 'mktg_expense':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Marketing Expense'
                    transposed_df.loc[index] = row.apply(lambda x: f"${int(x):,}")  # formatting as an integer
                elif index == 'mktg_expense_ind':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Industry Marketing Expense'
                    transposed_df.loc[index] = row.apply(lambda x: f"${int(x):,}")  # formatting as an integer
                elif index == 'avg_prem':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Average Premium'
                    transposed_df.loc[index] = row.apply(lambda x: f"${x:,.2f}")  # formatting as an integer
                elif index == 'quotes':
                    new_row_name = 'Quotes'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as currency without decimals
                elif index == 'sales':
                    new_row_name = 'Sales'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as currency without decimals
                elif index == 'canx':
                    new_row_name = 'Cancellations'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as currency without decimals
                elif index == 'end_in_force':
                    # Rename and format the 'in_force' row
                    new_row_name = f'Ending-{get_force_term(game)}'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer
                elif index == 'in_force_ind':
                    # Rename and format the 'in_force' row
                    new_row_name = f'Industry-{get_force_term(game)}'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer

                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)

                # Continue with additional conditions for more rows as needed

            for year in transposed_df.columns:
                # Convert the marketing expenses from string to float for calculation
                quotes = float(transposed_df.at['Quotes', year].replace(',', ''))
                sales = float(transposed_df.at['Sales', year].replace(',', ''))
                canx = float(transposed_df.at['Cancellations', year].replace(',', ''))
                force_term = get_force_term(game)
                in_force = float(transposed_df.at[f'Beginning-{force_term}', year].replace(',', ''))
                in_force_end = float(transposed_df.at[f'Ending-{force_term}', year].replace(',', ''))
                in_force_ind = float(transposed_df.at[f'Industry-{force_term}', year].replace(',', ''))
                marketing_expense = float(transposed_df.at['Marketing Expense', year].replace('$', '').replace(',', ''))
                industry_marketing_expense = float(
                    transposed_df.at['Industry Marketing Expense', year].replace('$', '').replace(',', ''))

                # Calculate the percentage (ensuring not to divide by zero)
                if industry_marketing_expense > 0:
                    percentage = (marketing_expense / industry_marketing_expense) * 100
                else:
                    percentage = 0  # or None, or however you wish to represent this edge case

                if quotes > 0:
                    close_ratio = (sales / quotes) * 100
                else:
                    close_ratio = 0  # or None, or however you wish to represent this edge case

                if in_force > 0:
                    retention_ratio = ((in_force - canx) / in_force) * 100
                else:
                    retention_ratio = 0
                if in_force_end > 0:
                    mkt_share = (in_force_end / in_force_ind) * 100
                else:
                    mkt_share = 0
                # Store the calculated percentage in our dictionary
                percentage_data[year] = f"{percentage:.2f}%"  # formatted to two decimal places
                close_ratio_data[year] = f"{close_ratio:.1f}%"  # formatted to one decimal places
                retention_ratio_data[year] = f"{retention_ratio:.1f}%"  # formatted to one decimal places
                mkt_share_ratio_data[year] = f"{mkt_share:.1f}%"  # formatted to one decimal places
            percentage_df = pd.DataFrame(percentage_data, index=['Marketing Spend as % of Industry'])
            close_ratio_df = pd.DataFrame(close_ratio_data, index=['Close Ratio'])
            retention_ratio_df = pd.DataFrame(retention_ratio_data, index=['Retention Ratio'])
            mkt_share_ratio_df = pd.DataFrame(mkt_share_ratio_data, index=['Market Share'])

            insert_position_mktg = transposed_df.index.get_loc('Industry Marketing Expense') + 1
            df_top_mktg = transposed_df.iloc[:insert_position_mktg]
            df_bottom_mktg = transposed_df.iloc[insert_position_mktg:]
            transposed_df_mktg = pd.concat([df_top_mktg, percentage_df, df_bottom_mktg])

            insert_position_close = transposed_df_mktg.index.get_loc('Sales') + 1
            df_top_close = transposed_df_mktg.iloc[:insert_position_close]
            df_bottom_close = transposed_df_mktg.iloc[insert_position_close:]
            transposed_df_close = pd.concat([df_top_close, close_ratio_df, df_bottom_close])

            insert_position_retention = transposed_df_close.index.get_loc('Cancellations') + 1
            df_top_retention = transposed_df_close.iloc[:insert_position_retention]
            df_bottom_retention = transposed_df_close.iloc[insert_position_retention:]
            transposed_df_retention = pd.concat([df_top_retention, retention_ratio_df, df_bottom_retention])

            force_term = get_force_term(game)
            insert_position_mktshare = transposed_df_retention.index.get_loc(f'Industry-{force_term}') + 1
            df_top_mktshare = transposed_df_retention.iloc[:insert_position_mktshare]
            df_bottom_mktshare = transposed_df_close.iloc[insert_position_mktshare:]
            transposed_df = pd.concat([df_top_mktshare, mkt_share_ratio_df, df_bottom_mktshare])

            selected_columns = [col for col in transposed_df.columns if int(col) <= selected_year]
            transposed_df = transposed_df[selected_columns]
            # Convert the final, formatted DataFrame to HTML for rendering
            if len(transposed_df.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df.columns)
                for i in range(missing_years):
                    transposed_df[f'{min(selected_columns) - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

            index = 1
            blank_row = pd.DataFrame([['' for _ in transposed_df.columns]], columns=transposed_df.columns)
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 5
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 7
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 11
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 14
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            financial_data_table = transposed_df.to_html(classes='my-financial-table', border=0, justify='initial',
                                                         index=True)

            # Prepare data for the CHART (up to 20 years)
            # Use the original df and filter by chart_selected_years
            chart_df_source = pd.DataFrame(financial_data_list) # Re-create or use a broader scope df if needed
            chart_df = chart_df_source[chart_df_source['year'].isin(chart_selected_years)].copy()
            chart_df = chart_df.sort_values('year', ascending=False) # CHANGED: Newest to oldest for chart
            
            if not chart_df.empty:
                # Calculate Marketing Spend as % of Industry
                # Ensure mktg_expense_ind is numeric and handle division by zero
                mktg_spend_percent_industry = []
                for idx, row in chart_df.iterrows():
                    mktg_exp = pd.to_numeric(row['mktg_expense'], errors='coerce')
                    mktg_exp_ind = pd.to_numeric(row['mktg_expense_ind'], errors='coerce')
                    if pd.notna(mktg_exp) and pd.notna(mktg_exp_ind) and mktg_exp_ind != 0:
                        mktg_spend_percent_industry.append(round((mktg_exp / mktg_exp_ind) * 100, 2))
                    else:
                        mktg_spend_percent_industry.append(0) # Default to 0 if data is missing or division by zero

                # Calculate Cancellation Rate and Close Ratio
                cancellation_rate_list = []
                close_ratio_list = [] # Will become sales_ratio_list
                for idx, row in chart_df.iterrows():
                    customers_val = pd.to_numeric(row['end_in_force'], errors='coerce')
                    cancellations_val = pd.to_numeric(row['canx'], errors='coerce')
                    sales_val = pd.to_numeric(row['sales'], errors='coerce')
                    quotes_val = pd.to_numeric(row['quotes'], errors='coerce')

                    if pd.notna(customers_val) and pd.notna(cancellations_val) and customers_val != 0:
                        cancellation_rate_list.append(round((cancellations_val / customers_val) * 100, 2))
                    else:
                        cancellation_rate_list.append(0)

                    if pd.notna(sales_val) and pd.notna(quotes_val) and quotes_val != 0:
                        close_ratio_list.append(round((sales_val / quotes_val) * 100, 2)) # Calculation remains the same
                    else:
                        close_ratio_list.append(0)

                chart_data = {
                    'years': chart_df['year'].tolist(),
                    'customers': [int(c) for c in chart_df['end_in_force'].tolist()],
                    'marketing_spend_percent_industry': mktg_spend_percent_industry,
                    'average_premium': [float(ap) for ap in chart_df['avg_prem'].tolist()],
                    'quotes': [int(q) for q in chart_df['quotes'].tolist()],
                    'sales': [int(s) for s in chart_df['sales'].tolist()],
                    'cancellations': [int(c) for c in chart_df['canx'].tolist()],
                    'cancellation_rate': cancellation_rate_list,
                    'sales_ratio': close_ratio_list # Changed key name
                }
                
                # --- SCATTER PLOT DATA PREPARATION ---
                # Create scatter plot data with profit_margin + marketing_expense decisions
                scatter_data = []
                
                # Get OSFI intervention counts and product reform data
                industry_data = Industry.objects.filter(game_id=game)
                claim_trends_data = ClaimTrends.objects.filter(game_id=game)
                
                # Get user's decisions data
                user_decisions = Decisions.objects.filter(
                    game_id=game,
                    player_id=user
                ).order_by('year')
                
                # Get the Player object for the current user to assist in excluding their data from industry counts
                current_player_obj = Players.objects.filter(game=game, player_id=user).first()

                # Create a dictionary for OSFI intervention counts by year
                osfi_intervention_counts = {}
                for year_val in chart_df['year'].unique():
                    # Count capital test failures in the industry for each year
                    industry_failures_query = industry_data.filter(year=year_val, capital_test='Fail')
                    if current_player_obj:
                        # Exclude the current user's company from the industry count if it failed
                        # The player_id field in Industry model likely refers to the User model instance
                        industry_failures_query = industry_failures_query.exclude(player_id=user)
                    
                    failures = industry_failures_query.count()
                    osfi_intervention_counts[year_val] = failures
                    # print(f"DEBUG: Year {year_val} - Industry MCT failures (excluding host): {failures}")
                
                print(f"DEBUG: OSFI intervention counts by year (pre-lag): {osfi_intervention_counts}")
                
                # --- Apply one-year lag so the impact is felt in the FOLLOWING year ---
                osfi_intervention_counts = {yr + 1: cnt for yr, cnt in osfi_intervention_counts.items()}
                print(f"DEBUG: Shifted OSFI intervention counts (impact year): {osfi_intervention_counts}")
                
                # Host-company (player) MCT failure flag – lagged by one year as well
                host_failure_prev = {}
                host_financials = Financials.objects.filter(game_id=game, player_id=user)
                for fin in host_financials:
                    host_failure_prev[fin.year + 1] = (fin.capital_test == 'Fail')

                # Get product reform data
                product_reforms = {}
                for ct in claim_trends_data:
                    try:
                        trends = ct.claim_trends
                        bi_reform = trends.get('bi_reform', {}).get(str(ct.year), 0)
                        cl_reform = trends.get('cl_reform', {}).get(str(ct.year), 0)
                        
                        # Determine reform type
                        if bi_reform and cl_reform:
                            reform_type = 'Both'
                        elif bi_reform:
                            reform_type = 'BI'  
                        elif cl_reform:
                            reform_type = 'CL'
                        else:
                            reform_type = None
                        
                        product_reforms[ct.year] = reform_type
                    except:
                        product_reforms[ct.year] = None
                
                # Calculate combined expense (profit_margin + marketing_expense) and align with current year's ratios
                years_sorted = sorted(chart_df['year'].unique())
                
                for curr_year in years_sorted:
                    # Get decision data for PRIOR year (lag 1)
                    # decision = user_decisions.filter(year=curr_year - 1).first()
                    # if not decision:
                        # Fallback to same-year decision if prior not available (first year)
                        # decision = user_decisions.filter(year=curr_year).first()
                    
                    # Fetch current and previous year decisions for YoY premium change
                    decision_for_curr_year_effective_rate = user_decisions.filter(year=curr_year - 1).first()
                    decision_for_prev_year_effective_rate = user_decisions.filter(year=curr_year - 2).first()

                    # For a point representing curr_year (and its ratios),
                    # the x-axis (yoy_rate_change) will be the rate change implemented for curr_year + 1.
                    # decision_for_rate_change_next_period = user_decisions.filter(year=curr_year + 1).first() // COMMENTING OUT
                    # decision_for_rate_change_curr_period_for_calc = user_decisions.filter(year=curr_year).first() // COMMENTING OUT

                    yoy_rate_change = 0.0  # Default to 0% change

                    # if decision_for_rate_change_next_period and decision_for_rate_change_next_period.sel_avg_prem is not None and \
                    #    decision_for_rate_change_curr_period_for_calc and decision_for_rate_change_curr_period_for_calc.sel_avg_prem is not None and \
                    #    decision_for_rate_change_curr_period_for_calc.sel_avg_prem > 0:
                    if decision_for_curr_year_effective_rate and decision_for_curr_year_effective_rate.sel_avg_prem is not None and \
                       decision_for_prev_year_effective_rate and decision_for_prev_year_effective_rate.sel_avg_prem is not None and \
                       decision_for_prev_year_effective_rate.sel_avg_prem > 0:
                        try:
                            # prem_next_for_rate_calc = decimal.Decimal(decision_for_rate_change_next_period.sel_avg_prem)
                            # prem_curr_for_rate_calc = decimal.Decimal(decision_for_rate_change_curr_period_for_calc.sel_avg_prem)
                            # prem_curr_val = decimal.Decimal(decision_curr.sel_avg_prem) # USING decision_curr
                            # prem_prev_val = decimal.Decimal(decision_prev.sel_avg_prem) # USING decision_prev
                            prem_effective_curr_val = decimal.Decimal(decision_for_curr_year_effective_rate.sel_avg_prem)
                            prem_effective_prev_val = decimal.Decimal(decision_for_prev_year_effective_rate.sel_avg_prem)
                            yoy_rate_change = float((prem_effective_curr_val / prem_effective_prev_val - 1) * 100)
                        except (decimal.InvalidOperation, TypeError):
                            yoy_rate_change = 0.0 # Fallback if conversion fails
                    
                    # if decision: // This was for combined_expense
                        # Calculate profit_margin + marketing_expense (both stored as integers representing tenths)
                        # profit_margin = decision.sel_profit_margin / 10.0  # Convert to percentage
                        # marketing_expense = decision.sel_exp_ratio_mktg / 10.0  # Convert to percentage
                        # combined_expense = profit_margin + marketing_expense
                        
                    # Get current year's retention and close ratios
                    curr_data = chart_df[chart_df['year'] == curr_year].iloc[0]
                    
                    curr_customers = float(curr_data['end_in_force'])
                    curr_canx = float(curr_data['canx'])
                    curr_quotes = float(curr_data['quotes'])
                    curr_sales = float(curr_data['sales'])
                    
                    # Calculate retention ratio for current year
                    if curr_customers > 0:
                        retention_ratio = ((curr_customers - curr_canx) / curr_customers) * 100
                    else:
                        retention_ratio = 0
                    
                    # Calculate close ratio for current year
                    if curr_quotes > 0:
                        close_ratio = (curr_sales / curr_quotes) * 100
                    else:
                        close_ratio = 0
                    
                    # Get OSFI interventions from current year
                    osfi_count = osfi_intervention_counts.get(curr_year, 0)
                    
                    # Did our own company fail capital test in prior year?
                    host_failed = host_failure_prev.get(curr_year, False)
                     
                    # Get product reforms from PRIOR year (to show impact on curr_year's point)
                    reform_status_for_this_point = product_reforms.get(curr_year - 1, None)
                     
                    scatter_data.append({
                         'year': int(curr_year),  # Convert numpy.int64 to Python int
                         # 'combined_expense': round(combined_expense, 1),
                         'yoy_rate_change': round(yoy_rate_change, 1),
                         'retention_ratio': round(retention_ratio, 2),
                         'close_ratio': round(close_ratio, 2),
                         'osfi_interventions': int(osfi_count),  # Convert to int in case it's numpy type
                         'product_reforms': reform_status_for_this_point,  # Pass lagged reform type as string
                         'host_failure': host_failed
                     })
                    
                    # print(f"DEBUG: Year {curr_year} - OSFI interventions: {osfi_count}, Combined expense: {combined_expense:.1f}%")
                    print(f"DEBUG: Year {curr_year} - OSFI interventions: {osfi_count}, YoY Rate Change: {yoy_rate_change:.1f}%")

            # Calculate logistic regression curves if we have scatter data
            close_ratio_curve = []
            retention_ratio_curve = []
            
            if len(scatter_data) > 3:  # Need at least 4 points for meaningful regression
                try:
                    # Extract X (combined expense) and Y values for both ratios
                    # X = np.array([point['combined_expense'] for point in scatter_data]) # Commented out as combined_expense is removed
                    # For the polynomial curves, if they are still needed, X should be updated to yoy_rate_change.
                    # For now, this will prevent an error. The impact on these specific curves needs review.
                    y_close = np.array([point['close_ratio'] for point in scatter_data])
                    y_retention = np.array([point['retention_ratio'] for point in scatter_data])
                    
                    # Fit polynomial regression (degree 2)
                    # This requires X. If X is not defined, polyfit will fail.
                    # If these curves are still desired, X must be redefined based on 'yoy_rate_change'.
                    # Example: X_poly = np.array([point['yoy_rate_change'] for point in scatter_data])
                    # Then use X_poly in np.polyfit.
                    # For now, to prevent errors and keep the existing structure, we can skip polyfit if X is based on combined_expense.
                    # However, the user summary mentioned linear trends calculated in JS, these python curves might be separate.
                    
                    # Temporary check: if combined_expense was the intended X, these curves can't be calculated as is.
                    # We will skip populating them to avoid errors.
                    # if 'combined_expense' in scatter_data[0]: # This check is now problematic as combined_expense is removed
                    #    X = np.array([point['combined_expense'] for point in scatter_data])
                    #    close_poly = np.polyfit(X, y_close, 2)
                    #    retention_poly = np.polyfit(X, y_retention, 2)
                    #    x_range = np.linspace(X.min(), X.max(), 50)
                    #    close_curve_values = np.polyval(close_poly, x_range)
                    #    retention_curve_values = np.polyval(retention_poly, x_range)
                    #    for i in range(len(x_range)):
                    #        close_ratio_curve.append({
                    #            'x': float(round(x_range[i], 2)),
                    #            'y': float(round(close_curve_values[i], 2))
                    #        })
                    #        retention_ratio_curve.append({
                    #            'x': float(round(x_range[i], 2)),
                    #            'y': float(round(retention_curve_values[i], 2))
                    #        })
                    pass # Temporarily skipping python polynomial curve calculation to avoid error with X.
                         # These curves are separate from the linear trends in JS.
                except Exception as e:
                    print(f"Regression for Python polynomial curves failed: {e}")
                    pass
            
            print(f"DEBUG: Close ratio curve points (Python poly): {len(close_ratio_curve)}")

            chart_data['scatter_data'] = scatter_data
            chart_data['close_ratio_curve'] = close_ratio_curve
            chart_data['retention_ratio_curve'] = retention_ratio_curve
            
            print(f"DEBUG: Final scatter_data sent to template:")
            for point in scatter_data:
                print(f"  Year {point['year']}: osfi_interventions={point['osfi_interventions']}")
        else:
            chart_data = None # Explicitly set to None if no chart data

        # print(f"DEBUG chart_data: {chart_data}")
        print(f"DEBUG: Final chart_data keys: {list(chart_data.keys()) if chart_data else 'None'}")
        if chart_data and 'scatter_data' in chart_data:
            print(f"DEBUG: scatter_data in chart_data has {len(chart_data['scatter_data'])} points")
        else:
            financial_data_table = '<p>No detailed financial data to display for the selected years.</p>'
    else:
        financial_data_table = '<p>No financial data available.</p>'

    context = {
        'title': ' - Marketing / Sales Report',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': financial_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': int(selected_year) if selected_year else None,  # Convert selected_year to int if it's not None
        'is_novice_game': is_novice_game,
        'chart_data': chart_data,
        'initial_chart_style': initial_chart_style,
        'initial_table_style': initial_table_style,
    }
    return render(request, template_name, context)


@login_required()
def financials_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))

    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    financial_data_table = '<p>No financial data available.</p>'  # Ensure always defined

    # Determine if this is a novice game
    is_novice_game = False
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass

    # Determine initial styles based on game difficulty
    if is_novice_game:
        initial_chart_style = "display: block;"
        initial_table_style = "display: none;"
    else:
        initial_chart_style = "display: none;"
        initial_table_style = "display: block;"

    financial_data = Financials.objects.filter(game_id=game, player_id=user)
    unique_years = financial_data.order_by('-year').values_list('year', flat=True).distinct()
    latest_year = unique_years[0] if unique_years else None
    template_name = 'Pricing/financials_report.html'

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.GET.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None


    if unique_years:  # Proceed if there are any financial years available
        # Querying the database
        financial_data_list = list(
            financial_data.values('year', 'written_premium', 'inv_income', 'in_force',  'annual_expenses',
                                  'ay_losses', 'py_devl', 'profit', 'dividend_paid',
                                  'capital', 'capital_ratio', 'capital_test'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(financial_data_list)

        # --- CHART DATA PREPARATION ---
        chart_data = None
        if not df.empty:
            # Prepare chart data for the last 20 years (most recent on the left)
            chart_years = sorted(df['year'].unique(), reverse=True)[:20]
            chart_years = list(chart_years)
            chart_years.sort(reverse=True)  # Most recent first (left side)
            chart_df = df[df['year'].isin(chart_years)].copy()
            chart_df = chart_df.sort_values('year', ascending=False)  # Most recent first
            # Fill missing values with 0 for charting
            chart_df['written_premium'] = pd.to_numeric(chart_df['written_premium'], errors='coerce').fillna(0)
            chart_df['capital'] = pd.to_numeric(chart_df['capital'], errors='coerce').fillna(0)
            chart_df['profit'] = pd.to_numeric(chart_df['profit'], errors='coerce').fillna(0)
            chart_df['dividend_paid'] = pd.to_numeric(chart_df['dividend_paid'], errors='coerce').fillna(0)
            
            # Calculate year-over-year change in written premium
            chart_df = chart_df.sort_values('year')  # Ensure proper ordering for diff calculation
            chart_df['premium_change'] = chart_df['written_premium'].diff().fillna(0)
            
            # Sort back to reverse order (most recent first) for display
            chart_df = chart_df.sort_values('year', ascending=False)
            
            chart_data = {
                'years': chart_df['year'].tolist(),
                'written_premium': chart_df['written_premium'].tolist(),
                'premium_change': chart_df['premium_change'].tolist(),
                'capital': chart_df['capital'].tolist(),
                'profitability': chart_df['profit'].tolist(),
                'dividends': chart_df['dividend_paid'].tolist(),
                'mct_test': chart_df['capital_test'].tolist()
            }
        # ... existing code ...
        if not df.empty:
            if selected_year not in unique_years:
                selected_year = latest_year
                # Filter out only the rows belonging to the latest four years
            all_data_years = df['year'].unique()  # Get all unique years
            all_data_years = sorted(all_data_years, reverse=True)  # Sort and pick the latest four years
            selected_years = sorted([yr for yr in all_data_years if yr <= selected_year], reverse=True)[:4]
            df = df.sort_values('year', ascending=False)

            # Creating a copy of the filtered DataFrame
            df_latest = df[df['year'].isin(selected_years)].copy()

            # Renaming columns without 'inplace=True'
            df_latest.rename(columns={"year": "Year"}, inplace=True)

            transposed_df = df_latest.set_index('Year').T  # Set 'year' as index before transposing
            # Now, we'll go through each row in the transposed DataFrame, rename it, and apply specific formatting
            for index, row in transposed_df.iterrows():
                if index == 'written_premium':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'Written Premium'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${round(x):,}")  # formatting as currency without decimals
                elif index == 'in_force':
                    # Rename and format the 'in_force' row
                    new_row_name = get_force_term(game)
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer
                elif index == 'inv_income':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Investment Income'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'annual_expenses':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Expenses'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'ay_losses':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Acc Yr Claims Incurred'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'py_devl':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Prior Yr Development'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'profit':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Profit'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'dividend_paid':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Dividend Paid'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'capital':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Ending Capital'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'capital_ratio':
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Ratio'
                    transposed_df.loc[index] = row.apply(lambda x: f"{round(x * 100, 1)}%")  # formatting as an integer
                elif index == 'capital_test':
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Test'

                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)

            selected_columns = [col for col in transposed_df.columns if int(col) <= selected_year]
            transposed_df = transposed_df[selected_columns]
            # Convert the final, formatted DataFrame to HTML for rendering
            if len(transposed_df.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df.columns)
                for i in range(missing_years):
                    transposed_df[f'{min(selected_columns) - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

            index = 2
            blank_row = pd.DataFrame([['' for _ in transposed_df.columns]], columns=transposed_df.columns)
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 4
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 8
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 11
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 13
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            financial_data_table = transposed_df.to_html(classes='my-financial-table', border=0, justify='initial',
                                                         index=True)
        else:
            financial_data_table = '<p>No detailed financial data to display for the selected years.</p>'
    else:
        financial_data_table = '<p>No financial data available.</p>'
        chart_data = None

    context = {
        'title': ' - Financial Report',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': financial_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': int(selected_year) if selected_year else None,  # Convert selected_year to int if it's not None
        'chart_data': chart_data,
        'is_novice_game': is_novice_game,
        'initial_chart_style': initial_chart_style,
        'initial_table_style': initial_table_style,
    }
    return render(request, template_name, context)


@login_required()
def industry_reports(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")


    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    # Handle GET request for year selection (from dropdown)
    if request.method == 'GET':
        selected_year = request.GET.get('year')
    else:
        selected_year = request.POST.get('year')
    
    selected_year = int(selected_year) if selected_year else None
    curr_pos = request.session.get('curr_pos', 0)

    template_name = 'Pricing/industry_reports.html'

    all_data = Industry.objects.filter(game_id=game)
    unique_years = all_data.order_by('-year').values_list('year', flat=True).distinct()
    latest_year = unique_years[0] if unique_years else None

    ordered_data = all_data.order_by('id', 'player_name')

    # Keep track of the players you've already seen
    seen_players = set()
    distinct_players = []

    # Iterate over the ordered queryset
    for entry in ordered_data:
        player_name = entry.player_name
        if player_name not in seen_players:
            distinct_players.append(player_name)
            seen_players.add(player_name)

    default_player_id = None
    player_id_list = []
    player_list = []
    if request.user.username in distinct_players:
        distinct_players.remove(request.user.username)
    distinct_players.insert(0, request.user.username)
    for count_id, unique_player in enumerate(distinct_players):
        player_name = f"{unique_player}"
        if unique_player == request.user.username:
            default_player_id = count_id
        player_list.append(player_name)
        player_id_list.append(count_id)

    max_pos = max(len(player_id_list) - 4, 0)

    # Save the updated curr_pos in the session
    if request.session.get('selected_year', 0) != selected_year:
        curr_pos = 0

    # Update curr_pos based on Next and Last buttons
    if request.POST.get('Next') == 'Next':
        curr_pos = min(curr_pos + 1, max_pos)
    if request.POST.get('Last') == 'Last':
        curr_pos = max(curr_pos - 1, 0)

    request.session['curr_pos'] = curr_pos

    # Find the position of default_player_id
    default_pos = player_id_list.index(default_player_id)

    # Calculate the starting position for displayed_players
    # It should always start with default_player_id and show next 3 players in the list
    start_pos = max(default_pos + curr_pos, 0)
    end_pos = min(start_pos + 4, len(player_id_list))

    # Build the displayed players list starting with default_player_id
    displayed_players = [default_player_id] + player_id_list[start_pos + 1:end_pos]

    # If the list is shorter than 4, pad it with the next available players
    while len(displayed_players) < 4 and end_pos < len(player_id_list):
        displayed_players.append(player_id_list[end_pos])
        end_pos += 1

    # Prepare the data for displayed companies (assuming player_list is a dictionary or list)
    companies = [player_list[player_id] for player_id in displayed_players]

    industry_id = len(player_list)
    industry_company_name = "Total Industry"
    player_list.append(f"{industry_company_name}" )
    player_id_list.append(len(player_id_list))
    distinct_players.append(industry_company_name)

    player_options = list(zip(player_id_list, player_list))

    # Prepare chart data
    chart_data = None
    is_novice_game = getattr(game, 'difficulty', 'novice').lower() == 'novice'

    if unique_years:  # Proceed if there are any financial years available
        if selected_year not in unique_years:
            selected_year = unique_years[0]
        request.session['selected_year'] = selected_year
        
        # Get all company data for the selected year (excluding "Total Industry")
        company_chart_data = Industry.objects.filter(
            game_id=game, 
            year=selected_year
        ).exclude(player_name="Total Industry").values(
            'player_name', 'written_premium', 'profit', 'capital', 
            'annual_expenses', 'cy_losses', 'capital_test'
        )
        
        if company_chart_data:
            chart_companies = []
            chart_written_premium = []
            chart_profitability = []
            chart_capital = []
            chart_loss_ratio = []
            chart_expense_ratio = []
            chart_mct_failures = []
            
            for company in company_chart_data:
                chart_companies.append(company['player_name'])
                chart_written_premium.append(float(company['written_premium']))
                chart_profitability.append(float(company['profit']))
                chart_capital.append(float(company['capital']))
                
                # Calculate loss ratio
                wp = float(company['written_premium'])
                loss_ratio = (float(company['cy_losses']) / wp * 100) if wp > 0 else 0
                chart_loss_ratio.append(loss_ratio)
                
                # Calculate expense ratio
                expense_ratio = (float(company['annual_expenses']) / wp * 100) if wp > 0 else 0
                chart_expense_ratio.append(expense_ratio)
                
                # Check MCT failure
                is_mct_fail = company['capital_test'] in ['Fail', 'fail', 'False', False]
                chart_mct_failures.append(is_mct_fail)
            
            chart_data = {
                'companies': chart_companies,
                'written_premium': chart_written_premium,
                'profitability': chart_profitability,
                'capital': chart_capital,
                'loss_ratio': chart_loss_ratio,
                'expense_ratio': chart_expense_ratio,
                'mct_failures': chart_mct_failures,
                'selected_year': selected_year,
                'current_user': user.username
            }

        # Create a DataFrame for the total view, excluding 'capital_test' and 'capital_ratio'
        industry_data = Industry.objects.filter(game_id=game, year=selected_year).values('year').annotate(
            written_premium=Sum('written_premium'),
            annual_expenses=Sum('annual_expenses'),
            cy_losses=Sum('cy_losses'),
            profit=Sum('profit'),
            capital=Sum('capital')
        )
        industry_data_list = list(
            industry_data.values('written_premium', 'annual_expenses',
                            'cy_losses', 'profit',
                            'capital'))  # add more fields as necessary

        company_data = Industry.objects.filter(game_id=game, year=selected_year)
        company_data_list = list(
            company_data.values('player_name', 'written_premium', 'annual_expenses',
                                'cy_losses', 'profit',
                                'capital', 'capital_ratio', 'capital_test'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        industry_df = pd.DataFrame(industry_data_list)
        industry_df['player_name'] = industry_company_name
        company_df = pd.DataFrame(company_data_list)

        for column in company_df.columns:
            if column not in industry_df.columns:
                industry_df[column] = pd.NA

        combined_df = pd.concat([company_df, industry_df], ignore_index=True)

        # Reset the index of the combined dataframe
        combined_df.reset_index(drop=True, inplace=True)

        if not combined_df.empty:
            if selected_year not in unique_years:
                selected_year = latest_year
                # Filter out only the rows belonging to the latest four years
            all_data_players = combined_df['player_name'].unique()  # Get all unique players
            all_data_players = sorted(all_data_players, reverse=False)  # Sort and pick the latest four years
            selected_players = sorted([player for player in all_data_players], reverse=False)[:4]

            # Now, we'll go through each row in the transposed DataFrame, rename it, and apply specific formatting
            combined_df.rename(columns={"player_name": "Company"}, inplace=True)

            transposed_df = combined_df.set_index('Company').T

            expense_ratio_data = {}
            loss_ratio_data = {}
            for index, row in transposed_df.iterrows():
                if index == 'written_premium':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'Written Premium'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${round(x):,}")  # formatting as currency without decimals
                elif index == 'annual_expenses':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Annual Expenses'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'cy_losses':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Calendar Year Losses'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'profit':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Profit'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'capital':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Capital'
                    transposed_df.loc[index] = row.apply(lambda x: f"${round(x):,}")  # formatting as an integer
                elif index == 'capital_ratio':
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Ratio'
                    transposed_df.loc[index] = row.apply(lambda x: f"{round(x * 100, 1)}%")  # formatting as an integer
                    transposed_df.loc[index][industry_company_name] = ' '
                elif index == 'capital_test':
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Test'
                    transposed_df.loc[index][industry_company_name] = ' '
                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)
            # Get displayed player names that actually exist in the DataFrame
            displayed_players_names = [player_list[i] for i in displayed_players]
            # Filter to only use column names that exist in the DataFrame
            available_columns = [name for name in displayed_players_names if name in transposed_df.columns]
            
            # Creating a new DataFrame with only the displayed players that exist
            if available_columns:
                transposed_df = transposed_df[available_columns]
            # If no columns match, continue with all columns

            for player in transposed_df.columns:
                # Convert the marketing expenses from string to float for calculation
                wprem = float(transposed_df.at['Written Premium', player].replace('$', '').replace(',', ''))
                annual_expenses = float(transposed_df.at['Annual Expenses', player].replace('$', '').replace(',', ''))
                cy_losses = float(transposed_df.at['Calendar Year Losses', player].replace('$', '').replace(',', ''))
                # canx = float(transposed_df.at['Cancellations', year].replace(',', ''))
                #in_force = float(transposed_df.at['Beginning-In-Force', year].replace(',', ''))
                # in_force_ind = float(transposed_df.at['Industry-In-Force', year].replace(',', ''))

                # Calculate the percentage (ensuring not to divide by zero)
                if wprem > 0:
                    expense_ratio = (annual_expenses / wprem) * 100
                else:
                    expense_ratio = 0  # or None, or however you wish to represent this edge case

                expense_ratio_data[player] = f"{expense_ratio:.1f}%"  # formatted to one decimal places

                if wprem > 0:
                    loss_ratio = (cy_losses / wprem) * 100
                else:
                    loss_ratio = 0  # or None, or however you wish to represent this edge case

                loss_ratio_data[player] = f"{loss_ratio:.1f}%"  # formatted to one decimal places

            expense_ratio_df = pd.DataFrame(expense_ratio_data, index=['Expense Ratio'])
            loss_ratio_df = pd.DataFrame(loss_ratio_data, index=['Loss Ratio'])

            insert_position_exp_ratio = transposed_df.index.get_loc('Annual Expenses') + 1
            df_top_exp_ratio = transposed_df.iloc[:insert_position_exp_ratio]
            df_bottom_exp_ratio = transposed_df.iloc[insert_position_exp_ratio:]
            transposed_df_exp = pd.concat([df_top_exp_ratio, expense_ratio_df, df_bottom_exp_ratio])

            insert_position_loss_ratio = transposed_df_exp.index.get_loc('Calendar Year Losses') + 1
            df_top_loss_ratio = transposed_df_exp.iloc[:insert_position_loss_ratio]
            df_bottom_loss_ratio = transposed_df_exp.iloc[insert_position_loss_ratio:]
            transposed_df = pd.concat([df_top_loss_ratio, loss_ratio_df, df_bottom_loss_ratio])

            # Convert the final, formatted DataFrame to HTML for rendering

            index = 1
            blank_row = pd.DataFrame([['' for _ in transposed_df.columns]], columns=transposed_df.columns)
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 4
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 7
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')
            index = 11
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            financial_data_table = transposed_df.to_html(classes='my-financial-table', border=0, justify='initial',
                                                         index=True)

        else:
            financial_data_table = '<p>No detailed financial data to display for the selected years.</p>'
    else:
        financial_data_table = '<p>No financial data available.</p>'

    context = {
        'title': ' - Industry Reports',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': company_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': selected_year,
        'player_options': player_options,
        'chart_data': chart_data,
        'is_novice_game': is_novice_game,
    }
    return render(request, template_name, context)


@login_required()
def valuation_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    financial_data_table = '<p>No valuation data available.</p>'  # Ensure always defined

    # Determine if this is a novice game
    is_novice_game = False
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass

    # Determine initial styles based on game difficulty
    if is_novice_game:
        initial_chart_style = "display: block;"
        initial_table_style = "display: none;"
    else:
        initial_chart_style = "display: none;"
        initial_table_style = "display: block;"

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    curr_pos = request.session.get('curr_pos', 0)
    template_name = 'Pricing/valuation_report.html'

    valuation_data = Valuation.objects.filter(game_id=game)
    ordered_data = valuation_data.order_by('id', 'player_name')

    # Keep track of the players you've already seen
    seen_players = set()
    distinct_players = []

    # Iterate over the ordered queryset
    for entry in ordered_data:
        player_name = entry.player_name
        if player_name not in seen_players:
            distinct_players.append(player_name)
            seen_players.add(player_name)

    default_player_id = None
    player_id_list = []
    player_list = []
    if request.user.username in distinct_players:
        distinct_players.remove(request.user.username)
    distinct_players.insert(0, request.user.username)
    for count_id, unique_player in enumerate(distinct_players):
        # player_name = f"{1 + count_id:02d} - {unique_player}"
        player_name = f"{unique_player}"
        if unique_player == request.user.username:
            default_player_id = count_id
        player_list.append(player_name)
        player_id_list.append(count_id)

    max_pos = max(len(player_id_list) - 4, 0)

    if request.session.get('selected_year', 0) != selected_year:
        curr_pos = 0

    # Update curr_pos based on Next and Last buttons
    if request.POST.get('Next') == 'Next':
        curr_pos = min(curr_pos + 1, max_pos)
    if request.POST.get('Last') == 'Last':
        curr_pos = max(curr_pos - 1, 0)

    # Save the updated curr_pos in the session
    request.session['curr_pos'] = curr_pos

    # Find the position of default_player_id
    default_pos = player_id_list.index(default_player_id)

    # Calculate the starting position for displayed_players
    # It should always start with default_player_id and show next 3 players in the list
    start_pos = max(default_pos + curr_pos, 0)
    end_pos = min(start_pos + 4, len(player_id_list))

    # Build the displayed players list starting with default_player_id
    displayed_players = [default_player_id] + player_id_list[start_pos + 1:end_pos]

    # If the list is shorter than 4, pad it with the next available players
    while len(displayed_players) < 4 and end_pos < len(player_id_list):
        displayed_players.append(player_id_list[end_pos])
        end_pos += 1

    # Prepare the data for displayed companies (assuming player_list is a dictionary or list)
    companies = [player_list[player_id] for player_id in displayed_players]

    unique_years = valuation_data.order_by('-year').values_list('year', flat=True).distinct()
    
    # Initialize variables
    chart_data = None
    valuation_period = None
    latest_year = None
    
    if unique_years:  # Proceed if there are any financial years available
        valuation_data_list = list(valuation_data.values('id', 'player_name', 'year', 'in_force', 'beg_in_force',
                                                         'profit',
                                                         'dividend_paid', 'excess_capital',
                                                         'pv_index', 'inv_rate', 'irr_rate'))
        val_df = pd.DataFrame(valuation_data_list)
        irr_rate_scalar = val_df['irr_rate'].iloc[0]
    # Creating a DataFrame from the obtained data
        if not val_df.empty:
            if selected_year not in unique_years:
                selected_year = unique_years[0]
            request.session['selected_year'] = selected_year
            
            # Continue with table data preparation (original logic)
            val_df = val_df[val_df['year'] <= selected_year]
            val_df = val_df.sort_values(by=['player_name', 'year'])
            all_data_years = val_df['year'].unique()  # Get all unique years
            latest_year = all_data_years.max()
            earliest_year = max((latest_year - 20 + 1), all_data_years.min())
            valuation_period = f'Utilizing estimates from period: {earliest_year} - {latest_year} '

            # print(f'companies: {companies} max_pos: {max_pos} curr_pos: {curr_pos}  default_pos: {default_pos}  start_pos: {start_pos}  displayed: {displayed_players}')
            val_df = val_df.groupby('player_name').apply(reverse_pv_index).reset_index(drop=True)

            val_df['dividend_pv'] = val_df['new_pv_index'] * val_df['dividend_paid']
            val_df['profit'] = np.where(val_df['year'] >=earliest_year, val_df['profit'], 0)
            val_df['excess_capital'] = np.where(val_df['year'] == selected_year, val_df['excess_capital'], 0)
            val_df['in_force'] = np.where(val_df['year'] == selected_year, val_df['in_force'], 0)
            val_df['tot_in_force'] = np.where(val_df['year'] >= earliest_year, val_df['beg_in_force'], 0)
            val_df['beg_in_force'] = np.where(val_df['year'] == earliest_year, val_df['beg_in_force'], 0)
            val_df['future_value'] = 0
            val_df['total_valuation'] = val_df['dividend_pv'] + val_df['excess_capital']
            # df = val_df.groupby('player_name')['dividend_pv'].sum().reset_index()
            df = val_df.groupby('player_name').agg({'in_force': 'sum',
                                                    'beg_in_force': 'sum',
                                                    'tot_in_force': 'sum',
                                                    'profit': 'sum',
                                                    'future_value': 'sum',
                                                    'dividend_pv': 'sum', 'excess_capital': 'sum',
                                                    'future_value': 'sum',
                                                    'total_valuation': 'sum'}).reset_index()
            df['capped_growth_rate'] = df.apply(lambda row: calculate_growth_rate(row, latest_year, earliest_year ), axis=1)
            df['avg_profit'] = df.apply(lambda row: calculate_avg_profit(row,),  axis=1)
            df['future_value'] = df.apply(lambda row: calculate_future_value(row, irr_rate_scalar), axis=1)
            df['total_valuation'] = df['total_valuation'] + df['future_value']
            
            # --- CHART DATA PREPARATION (after table data is processed) ---
            # Prepare competitive comparison chart data for all companies
            if not df.empty and latest_year:
                # Sort companies by total valuation (highest first) for competitive display
                chart_df_all_companies = df.sort_values('total_valuation', ascending=False).copy()
                
                # Convert all decimal values to float for chart compatibility
                chart_df_all_companies['total_valuation'] = pd.to_numeric(chart_df_all_companies['total_valuation'], errors='coerce').fillna(0).astype(float)
                chart_df_all_companies['dividend_pv'] = pd.to_numeric(chart_df_all_companies['dividend_pv'], errors='coerce').fillna(0).astype(float)
                chart_df_all_companies['future_value'] = pd.to_numeric(chart_df_all_companies['future_value'], errors='coerce').fillna(0).astype(float)
                chart_df_all_companies['excess_capital'] = pd.to_numeric(chart_df_all_companies['excess_capital'], errors='coerce').fillna(0).astype(float)
                chart_df_all_companies['in_force'] = pd.to_numeric(chart_df_all_companies['in_force'], errors='coerce').fillna(0).astype(float)
                
                # Prepare chart data for competitive comparison
                chart_data = {
                    'companies': chart_df_all_companies['player_name'].tolist(),
                    'total_valuation': (chart_df_all_companies['total_valuation'] / 100000 * 0.1).tolist(),
                    'dividend_pv': (chart_df_all_companies['dividend_pv'] / 100000 * 0.1).tolist(),
                    'future_value': (chart_df_all_companies['future_value'] / 100000 * 0.1).tolist(),
                    'excess_capital': (chart_df_all_companies['excess_capital'] / 100000 * 0.1).tolist(),
                    'in_force': chart_df_all_companies['in_force'].tolist(),
                    'valuation_ranks': [], # Will be populated after Valuation Rank column is created
                    'force_term': get_force_term(game),
                    'valuation_year': selected_year,
                    'current_user': user.username
                }
            
            # Continue with table rendering (original logic)
            # Rename the 'player_name' column to 'Company'
            df = df.rename(columns={'player_name': 'Company'})
            df['Valuation Rank'] = df['total_valuation'].rank(ascending=False, method='min').astype(int)

            # Update chart_data with valuation ranks now that they're available
            if 'chart_data' in locals() and chart_data is not None:
                # Sort companies by total valuation (highest first) for competitive display
                chart_df_sorted = df.sort_values('total_valuation', ascending=False).copy()
                chart_data['valuation_ranks'] = chart_df_sorted['Valuation Rank'].tolist()

            filtered_df = df[df['Company'].isin(companies)]
            filtered_df = filtered_df.drop(['tot_in_force', 'beg_in_force', 'profit'], axis=1)  # Drop unwanted columns
            filtered_df = filtered_df.set_index('Company').loc[companies].reset_index()

            transposed_df = filtered_df.T
            transposed_df = transposed_df.rename(columns=transposed_df.iloc[0]).drop(transposed_df.index[0])

            for index, row in transposed_df.iterrows():
                if index == 'in_force':
                    # Rename and format the 'written_premium' row
                    new_row_name = get_force_term(game)
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"{x:,}")  # formatting as currency without decimals
                elif index == 'capped_growth_rate':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'Capped Growth Rate'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"{100 * x:.1f}%")  # formatting as currency without decimals
                elif index == 'avg_profit':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'Avg Profit / Client'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${round(x):,}")  # formatting as currency without decimals
                elif index == 'future_value':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'Future Proj Value (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):,.1f}")  # formatting as currency without decimals
                elif index == 'dividend_pv':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'P.V. Dividends (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):,.1f}")  # formatting as currency without decimals
                elif index == 'excess_capital':
                    new_row_name = f'Excess Capital (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):,.1f}")  # formatting as currency without decimals
                elif index == 'total_valuation':
                    new_row_name = 'Total Valuation (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):,.1f}")  # formatting as currency without decimals
                elif index == 'Valuation Rank':
                    new_row_name = 'Valuation Rank'

                transposed_df.rename(index={index: new_row_name}, inplace=True)
            force_term = get_force_term(game)
            row_order = {
                force_term: 0,
                'Capped Growth Rate': 1,
                'Avg Profit / Client': 2,
                'Future Proj Value (MM)': 3,
                'P.V. Dividends (MM)': 4,
                'Excess Capital (MM)': 5,
                'Total Valuation (MM)': 6,
                'Valuation Rank': 7,
            }
            transposed_df['RowOrder'] = transposed_df.index.map(row_order)
            transposed_df.sort_values(by='RowOrder', inplace=True)
            transposed_df.drop(columns=['RowOrder'], inplace=True)

            index = 3
            blank_row = pd.DataFrame([['' for _ in transposed_df.columns]], columns=transposed_df.columns)
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 7
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            index = 9
            transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

            financial_data_table = transposed_df.to_html(classes='my-financial-table', border=0, justify='initial',
                                                         index=True)
        else:
            financial_data_table = '<p>No detailed financial data to display for the selected years.</p>'
    else:
        financial_data_table = '<p>No financial data available.</p>'
        latest_year = None

    if len(unique_years) > 2:
        unique_years = unique_years[0:len(unique_years)-2]

    context = {
        'title': ' - Valuation Report',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': valuation_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': selected_year,
        'valuation_period': valuation_period,
        'chart_data': chart_data,
        'is_novice_game': is_novice_game,
        'initial_chart_style': initial_chart_style,
        'initial_table_style': initial_table_style,
    }
    return render(request, template_name, context)


@login_required()
def claim_devl_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    default_coverage_id = 2
    coverage_id_list = []
    coverage_list = []
    coverages = ['Bodily Injury', 'Collision', 'Total']
    for count_id, coverage in enumerate(coverages):
        coverage_list.append(coverage)
        coverage_id_list.append(count_id)
    coverage_options = list(zip(coverage_id_list, coverage_list))

    selected_coverage = request.POST.get('coverage')
    selected_coverage = int(selected_coverage) if selected_coverage else default_coverage_id

    template_name = 'Pricing/claim_devl_report.html'

    triangle_data = Triangles.objects.filter(game_id=game, player_id=user)
    unique_years = triangle_data.order_by('-year').values_list('year', flat=True).distinct()
    if unique_years:  # Proceed if there are any financial years available
        triangle_data_list = list(triangle_data.values('id', 'player_name', 'year', 'triangles'))
        triangle_df = pd.DataFrame(triangle_data_list)

    # Creating a DataFrame from the obtained data
        if not triangle_df.empty:
            all_data_years = triangle_df['year'].unique()  # Get all unique years
            latest_year = all_data_years.max()
            if selected_year not in unique_years:
                selected_year = unique_years[0]
            triangle_df = triangle_df[triangle_df['year'] == selected_year].reset_index(drop=True)
            triangle_df = triangle_df.sort_values('year', ascending=False)

            claim_data = triangle_df.triangles[0]['triangles']
            acc_yrs = [f'Acc Yr {acc_yr}' for acc_yr in claim_data['acc_yrs']]
            devl_mths = [(yr + 1)*12 for yr in claim_data['devl_yrs']]
            covg = ['paid_bi', 'paid_cl', 'paid_to'][selected_coverage]
            incd_covg = ['incd_bi', 'incd_cl', 'incd_to'][selected_coverage]

            df = pd.DataFrame(columns=acc_yrs, index=devl_mths)
            incd_df = copy.deepcopy(df)

            for i, devl_mth in enumerate(devl_mths):
                df.loc[devl_mth] = claim_data[covg][i]
                incd_df.loc[devl_mth] = claim_data[incd_covg][i]

            transposed_df = df.T
            transposed_incd_df = incd_df.T
            transposed_incd_df.iloc[3, 2] = 0
            transposed_incd_df.iloc[4, 1] = 0
            transposed_incd_df.iloc[4, 2] = 0

            transposed_booked_error_df = copy.deepcopy(incd_df.T).iloc[0:3, :]
            transposed_booked_error_df.iloc[0:3, 0] = transposed_booked_error_df.iloc[0:3, 0] / transposed_booked_error_df.iloc[0:3, 2] - 1
            transposed_booked_error_df.iloc[0:3, 1] = transposed_booked_error_df.iloc[0:3, 1] / transposed_booked_error_df.iloc[0:3, 2] - 1
            transposed_booked_error_df.iloc[0:3, 2] = -99999999
            transposed_booked_error_df.columns = [str(int(col)) if col < 36 else '' for col in transposed_booked_error_df.columns]
            transposed_booked_error_df_fmt = transposed_booked_error_df.map(lambda x: '' if x == -99999999 else '{:,.1f}%'.format(100*x))

            fact_labels = ['Age-to-Age']
            fact_devl_mths = copy.deepcopy(devl_mths)
            fact_devl_mths[0] = None
            fact_df = pd.DataFrame(columns=fact_labels, index=fact_devl_mths)

            for i, fact_devl_mth in enumerate(fact_devl_mths):
                if fact_devl_mth == fact_devl_mths[0]:
                    fact_df.iloc[0, 0] = 0
                if fact_devl_mth == fact_devl_mths[1]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 1])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 0])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[1, 0] = numerator / denominator
                if fact_devl_mth == fact_devl_mths[2]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 2])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 1])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[2, 0] = numerator / denominator

            fact_transposed_df = fact_df.T
            fact_transposed_df.columns = [str(int(col)) if pd.notna(col) else '' for col in fact_transposed_df.columns]
            fact_transposed_df_fmt = fact_transposed_df.map(lambda x: '' if x == 0 else '{:,.3f}'.format(x))
            fact_transposed_df_fmt.iloc[0, 1] = '<span class="red-text">' + fact_transposed_df_fmt.iloc[0, 1] + '</span>'
            fact_transposed_df_fmt.iloc[0, 2] = '<span class="red-text">' + fact_transposed_df_fmt.iloc[0, 2] + '</span>'
            # project to ultimate
            transposed_df.iloc[3, 2] = transposed_df.iloc[3, 1] * fact_df.iloc[2, 0]
            transposed_df.iloc[4, 1] = transposed_df.iloc[4, 0] * fact_df.iloc[1, 0]
            transposed_df.iloc[4, 2] = transposed_df.iloc[4, 1] * fact_df.iloc[2, 0]
            transposed_df_fmt = transposed_df.map(lambda x: '' if x == 0 else '{:,.0f}'.format(x))
            transposed_incd_df_fmt = transposed_incd_df.map(lambda x: '' if x == 0 else '{:,.0f}'.format(x))

            transposed_df_fmt.iloc[3, 2] = '<span class="red-text">' + transposed_df_fmt.iloc[3, 2] + '</span>'
            transposed_df_fmt.iloc[4, 1] = '<span class="red-text">' + transposed_df_fmt.iloc[4, 1] + '</span>'
            transposed_df_fmt.iloc[4, 2] = '<span class="red-text">' + transposed_df_fmt.iloc[4, 2] + '</span>'

            paid_data_table = transposed_df_fmt.to_html(classes='my-financial-table', border=0, justify='initial',
                                                 index=True, escape=False)

            incd_data_table = transposed_incd_df_fmt.to_html(classes='my-financial-table', border=0, justify='initial',
                                                        index=True, escape=False)

            factor_data_table = fact_transposed_df_fmt.to_html(classes='my-financial-table', border=0, justify='initial',
                                                    index=True, escape=False)

            booked_error_data_table = transposed_booked_error_df_fmt.to_html(classes='my-financial-table', border=0, justify='initial',
                                                    index=True, escape=False)
        else:
            paid_data_table = '<p>No detailed financial data to display for the selected years.</p>'
            incd_data_table = None
            factor_data_table = None
            booked_error_data_table = None
    else:
        paid_data_table = '<p>No financial data available.</p>'
        incd_data_table = None
        factor_data_table = None
        booked_error_data_table = None
        latest_year = None

    context = {
        'title': ' - Claim Development Report',
        'game': game,
        'paid_data_table': paid_data_table,
        'incurred_data_table': incd_data_table,
        'factor_data_table': factor_data_table,
        'booked_error_data_table': booked_error_data_table,
        'has_financial_data': triangle_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': selected_year,
        'coverage_options': coverage_options,
        'selected_coverage': selected_coverage,
    }

    return render(request, template_name, context)


@login_required()
def claim_trend_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    default_coverage_id = 2
    coverage_id_list = []
    coverage_list = []
    coverages = ['Bodily Injury', 'Collision', 'Total']
    for count_id, coverage in enumerate(coverages):
        coverage_list.append(coverage)
        coverage_id_list.append(count_id)
    coverage_options = list(zip(coverage_id_list, coverage_list))

    selected_coverage = request.POST.get('coverage')
    selected_coverage = int(selected_coverage) if selected_coverage else default_coverage_id

    template_name = 'Pricing/claim_trend_report.html'

    triangle_data = Triangles.objects.filter(game_id=game, player_id=user)
    financial_data = Financials.objects.filter(game_id=game, player_id=user)
    claimtrend_data = ClaimTrends.objects.filter(game_id=game)

    unique_years = triangle_data.order_by('-year').values_list('year', flat=True).distinct()
    if unique_years:  # Proceed if there are any financial years available
        financial_data_list = list(financial_data.values('year', 'in_force', 'clm_bi', 'clm_cl'))
        financial_df = pd.DataFrame(financial_data_list)
        triangle_data_list = list(triangle_data.values('id', 'player_name', 'year', 'triangles'))
        triangle_df = pd.DataFrame(triangle_data_list)


    # Creating a DataFrame from the obtained data
        if not triangle_df.empty:
            all_data_years = triangle_df['year'].unique()  # Get all unique years
            latest_year = all_data_years.max()
            if selected_year not in unique_years:
                selected_year = unique_years[0]
            triangle_df = triangle_df[triangle_df['year'] == selected_year].reset_index(drop=True)
            financial_df = financial_df[financial_df['year'] > (selected_year - 5)]
            financial_df = financial_df.sort_values('year', ascending=True)
            claimtrend_obj = claimtrend_data.filter(year=selected_year).first()
            if claimtrend_obj:
                claimtrend_dict = claimtrend_obj.claim_trends

            claim_data = triangle_df['triangles'][0]['triangles']
            clm_yrs = [acc_yr for acc_yr in claim_data['acc_yrs']]
            acc_yrs = [f'Acc Yr {acc_yr}' for acc_yr in claim_data['acc_yrs']]
            devl_mths = [(yr + 1)*12 for yr in claim_data['devl_yrs']]
            covg = ['paid_bi', 'paid_cl', 'paid_to'][selected_coverage]

            reform_fact = []
            for yr in reversed(clm_yrs):
                if selected_coverage == 2:
                    reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'] or claimtrend_dict['cl_reform'][f'{yr}'])
                elif selected_coverage == 1:
                    reform_fact.append(claimtrend_dict['cl_reform'][f'{yr}'])
                elif selected_coverage == 0:
                    reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'])

            df = pd.DataFrame(columns=acc_yrs, index=devl_mths)
            for i, devl_mth in enumerate(devl_mths):
                df.loc[devl_mth] = claim_data[covg][i]

            transposed_df = df.T

            fact_labels = ['Age-to-Age']
            fact_devl_mths = copy.deepcopy(devl_mths)
            fact_devl_mths[0] = None
            fact_df = pd.DataFrame(columns=fact_labels, index=fact_devl_mths)

            for i, fact_devl_mth in enumerate(fact_devl_mths):
                if fact_devl_mth == fact_devl_mths[0]:
                    fact_df.iloc[0, 0] = 0
                if fact_devl_mth == fact_devl_mths[1]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 1])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 0])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[1, 0] = numerator / denominator
                if fact_devl_mth == fact_devl_mths[2]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 2])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 1])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[2, 0] = numerator / denominator
                    fact_df.iloc[1, 0] = fact_df.iloc[1, 0] * fact_df.iloc[2, 0]

            cols = ['Actual Paid', 'Devl Factor', 'Ultimate Incurred', get_force_term(game), 'Loss Cost', 'Claim Count', 'Frequency', 'Severity', 'Product Reform']
            proj_cols = ['Est Loss Cost', 'Est LC Trend', 'Est LC Reform', 'Est Frequency', 'Est Freq Trend',
                         'Est Freq Reform', 'Est Severity', 'Est Sev Trend', 'Est Sev Reform']
            display_yrs = [f'Acc Yr {acc_yr}' for acc_yr in claim_data['acc_yrs']]
            display_yrs.reverse()
            proj_display_yrs = copy.deepcopy(display_yrs)
            proj_display_yrs.insert(0, f'Est Acc Yr {max(claim_data["acc_yrs"]) + 1}')
            display_df = pd.DataFrame(columns=display_yrs, index=cols)
            display_df_fmt = pd.DataFrame(columns=display_yrs, index=cols)

            proj_display_df = pd.DataFrame(columns=proj_display_yrs, index=proj_cols)
            proj_display_df_fmt = pd.DataFrame(columns=proj_display_yrs, index=proj_cols)
            i = 0
            est_values = dict()
            for categ, row in display_df.iterrows():
                if categ == 'Actual Paid':
                    for j in range(len(acc_yrs)):
                        display_df.iloc[i, j] = df.iloc[min(j, len(devl_mths) - 1), len(acc_yrs) - j - 1]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.0f}'.format(x))
                elif categ == 'Devl Factor':
                    for k in range(len(acc_yrs)):
                        if k < 2:
                            display_df.iloc[i, k] = fact_df.iloc[k + 1].values[0]
                        else:
                            display_df.iloc[i, k] = 1
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.3f}'.format(x))
                elif categ == 'Ultimate Incurred':
                    for l in range(len(acc_yrs)):
                        display_df.iloc[i, l] = display_df.iloc[i - 2, l] * display_df.iloc[i - 1, l]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.0f}'.format(x))
                elif categ == get_force_term(game):
                    for m in range(len(acc_yrs)):
                        display_df.iloc[i, m] = financial_df.iloc[len(financial_df) - m - 1 - (max(unique_years) - selected_year), 1]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.0f}'.format(x))
                elif categ == 'Loss Cost':
                    for n in range(len(acc_yrs)):
                        denom = display_df.iloc[i - 1, n]
                        if denom != 0:
                            display_df.iloc[i, n] = decimal.Decimal(display_df.iloc[i - 2, n]) / denom
                        else:
                            display_df.iloc[i, n] = 0
                    lcost = [(clm_yrs[len(clm_yrs) - q - 1], float(lc)) for q, lc in enumerate(display_df.iloc[i].values)]
                    est_values['reform'], est_values['proj_lcost_est'], est_values['proj_lcost'] = perform_logistic_regression(lcost, reform_fact)
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Claim Count':
                    for o in range(len(acc_yrs)):
                        if selected_coverage in [1, 2]: # collision or total
                            display_df.iloc[i, o] = financial_df.iloc[len(financial_df) - o - 1 - (max(unique_years) - selected_year), 3]
                        else:
                            display_df.iloc[i, o] = financial_df.iloc[len(financial_df) - o - 1 - (max(unique_years) - selected_year), 2]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.0f}'.format(x))
                elif categ == 'Frequency':
                    for p in range(len(acc_yrs)):
                        denom = display_df.iloc[i - 3, p]
                        if denom != 0:
                            display_df.iloc[i, p] = 100 * decimal.Decimal(display_df.iloc[i - 1, p]) / denom
                        else:
                            display_df.iloc[i, p] = 0
                    freq = [(clm_yrs[len(clm_yrs) - q - 1], float(freq)) for q, freq in enumerate(display_df.iloc[i].values)]
                    _, est_values['proj_freq_est'], est_values['proj_freq'] = perform_logistic_regression(freq, reform_fact)
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(x))
                elif categ == 'Severity':
                    for q in range(len(acc_yrs)):
                        denom = display_df.iloc[i - 2, q]
                        if denom != 0:
                            display_df.iloc[i, q] = decimal.Decimal(display_df.iloc[i - 5, q]) / denom
                        else:
                            display_df.iloc[i, q] = 0
                    sev = [(clm_yrs[len(clm_yrs) - q - 1], float(sev)) for q, sev in enumerate(display_df.iloc[i].values)]
                    _, est_values['proj_sev_est'], est_values['proj_sev'] = perform_logistic_regression(sev, reform_fact)
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Product Reform':
                    for r in range(len(acc_yrs)):
                        if reform_fact[r] == 1: # note that reform fact not reversed (this is done in prediction util)
                            display_df.iloc[i, r] = '<span class="red-text">' + 'Yes' + '</span>'
                        else:
                            display_df.iloc[i, r] = '<span class="blue-text">' + 'No' + '</span>'
                    display_df_fmt.iloc[i] = display_df.iloc[i]
                i += 1

            z = 0
            for categ, row in proj_display_df.iterrows():
                if categ == 'Est Loss Cost':
                    for j in range(len(acc_yrs) + 1):
                        proj_display_df.iloc[z, j] = est_values['proj_lcost'][len(acc_yrs) - j]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Est LC Trend':
                    proj_display_df.iloc[z] = 0
                    proj_display_df.iloc[z, 0] = est_values['proj_lcost_est'][0]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100*x))
                elif categ == 'Est LC Reform':
                    proj_display_df.iloc[z] = 0
                    if est_values['reform']:
                        proj_display_df.iloc[z, 0] = est_values['proj_lcost_est'][1]
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100 * x))
                    else:
                        proj_display_df.iloc[z, 0] = 'N/A'
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else x)
                elif categ == 'Est Frequency':
                    for j in range(len(acc_yrs) + 1):
                        proj_display_df.iloc[z, j] = est_values['proj_freq'][len(acc_yrs) - j]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(x))
                elif categ == 'Est Freq Trend':
                    proj_display_df.iloc[z] = 0
                    proj_display_df.iloc[z, 0] = est_values['proj_freq_est'][0]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100 * x))
                elif categ == 'Est Freq Reform':
                    proj_display_df.iloc[z] = 0
                    if est_values['reform']:
                        proj_display_df.iloc[z, 0] = est_values['proj_freq_est'][1]
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100 * x))
                    else:
                        proj_display_df.iloc[z, 0] = 'N/A'
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else x)
                elif categ == 'Est Severity':
                    for j in range(len(acc_yrs) + 1):
                        proj_display_df.iloc[z, j] = est_values['proj_sev'][len(acc_yrs) - j]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Est Sev Trend':
                    proj_display_df.iloc[z] = 0
                    proj_display_df.iloc[z, 0] = est_values['proj_sev_est'][0]
                    proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100 * x))
                elif categ == 'Est Sev Reform':
                    proj_display_df.iloc[z] = 0
                    if est_values['reform']:
                        proj_display_df.iloc[z, 0] = est_values['proj_sev_est'][1]
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else '{:,.1f}%'.format(100 * x))
                    else:
                        proj_display_df.iloc[z, 0] = 'N/A'
                        proj_display_df_fmt.iloc[z] = proj_display_df.iloc[z].map(lambda x: '' if x == 0 else x)
                z += 1

            display_df_fmt.insert(0, ' ', '')

            index_list = [3, 5, 7, 9]  # insert blank rows
            proj_index_list = [3, 7]
            blank_row = pd.DataFrame([['' for _ in display_df_fmt.columns]], columns=display_df_fmt.columns)
            for index in index_list:
                display_df_fmt = pd.concat([display_df_fmt.iloc[:index], blank_row, display_df_fmt.iloc[index:]])
                display_df_fmt.index = display_df_fmt.index.where(display_df_fmt.index != 0, ' ')

            proj_blank_row = pd.DataFrame([['' for _ in proj_display_df_fmt.columns]], columns=proj_display_df_fmt.columns)
            for index in proj_index_list:
                proj_display_df_fmt = pd.concat([proj_display_df_fmt.iloc[:index], proj_blank_row, proj_display_df_fmt.iloc[index:]])
                proj_display_df_fmt.index = proj_display_df_fmt.index.where(proj_display_df_fmt.index != 0, ' ')

            trend_data_table = display_df_fmt.to_html(classes='my-financial-table',
                                                      border=0, justify='initial',
                                                      index=True, escape=False)

            trend_est_table = proj_display_df_fmt.to_html(classes='my-financial-table',
                                                      border=0, justify='initial',
                                                      index=True, escape=False)
        else:
            trend_data_table = '<p>No detailed financial data to display for the selected years.</p>'
            trend_est_table = None
    else:
        trend_data_table = '<p>No financial data available.</p>'
        trend_est_table = None
        latest_year = None

    context = {
        'title': ' - Claim Trend Report',
        'game': game,
        'trend_data_table': trend_data_table,
        'trend_est_table': trend_est_table,
        'has_financial_data': triangle_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': selected_year,
        'coverage_options': coverage_options,
        'selected_coverage': selected_coverage,
        'chart_data': prepare_claim_trend_chart_data(triangle_df, financial_df, claimtrend_dict, clm_yrs, unique_years, selected_year) if not triangle_df.empty else None,
        }
    return render(request, template_name, context)


def prepare_claim_trend_chart_data(triangle_df, financial_df, claimtrend_dict, clm_yrs, unique_years, selected_year):
    """Prepare chart data for all three coverages"""
    
    chart_data = {
        'years': clm_yrs,
        'coverages': {}
    }
    
    # Process each coverage type
    coverages = ['Bodily Injury', 'Collision', 'Total']
    coverage_keys = ['paid_bi', 'paid_cl', 'paid_to']
    
    for coverage_idx, (coverage_name, coverage_key) in enumerate(zip(coverages, coverage_keys)):
        
        # Get claim data for this coverage
        claim_data = triangle_df['triangles'][0]['triangles']
        acc_yrs = [f'Acc Yr {acc_yr}' for acc_yr in claim_data['acc_yrs']]
        devl_mths = [(yr + 1)*12 for yr in claim_data['devl_yrs']]
        
        # Build reform factor for this coverage
        reform_fact = []
        for yr in reversed(clm_yrs):
            if coverage_idx == 2:  # Total
                reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'] or claimtrend_dict['cl_reform'][f'{yr}'])
            elif coverage_idx == 1:  # Collision
                reform_fact.append(claimtrend_dict['cl_reform'][f'{yr}'])
            elif coverage_idx == 0:  # Bodily Injury
                reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'])
        
        # Create dataframe for this coverage
        df = pd.DataFrame(columns=acc_yrs, index=devl_mths)
        for i, devl_mth in enumerate(devl_mths):
            df.loc[devl_mth] = claim_data[coverage_key][i]
        
        transposed_df = df.T
        
        # Calculate development factors
        fact_labels = ['Age-to-Age']
        fact_devl_mths = copy.deepcopy(devl_mths)
        fact_devl_mths[0] = None
        fact_df = pd.DataFrame(columns=fact_labels, index=fact_devl_mths)
        
        for i, fact_devl_mth in enumerate(fact_devl_mths):
            if fact_devl_mth == fact_devl_mths[0]:
                fact_df.iloc[0, 0] = 0
            if fact_devl_mth == fact_devl_mths[1]:
                numerator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 1])
                denominator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 0])
                if denominator == 0:
                    denominator = 1
                fact_df.iloc[1, 0] = numerator / denominator
            if fact_devl_mth == fact_devl_mths[2]:
                numerator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 2])
                denominator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 1])
                if denominator == 0:
                    denominator = 1
                fact_df.iloc[2, 0] = numerator / denominator
                fact_df.iloc[1, 0] = fact_df.iloc[1, 0] * fact_df.iloc[2, 0]
        
        # Create display dataframe
        cols = ['Actual Paid', 'Devl Factor', 'Ultimate Incurred', 'In-Force', 'Loss Cost', 'Claim Count', 'Frequency', 'Severity', 'Product Reform']
        display_yrs = [f'Acc Yr {acc_yr}' for acc_yr in claim_data['acc_yrs']]
        display_yrs.reverse()
        display_df = pd.DataFrame(columns=display_yrs, index=cols)
        
        # Calculate all the metrics
        for i, categ in enumerate(cols):
            if categ == 'Actual Paid':
                for j in range(len(acc_yrs)):
                    display_df.iloc[i, j] = df.iloc[min(j, len(devl_mths) - 1), len(acc_yrs) - j - 1]
            elif categ == 'Devl Factor':
                for k in range(len(acc_yrs)):
                    if k < 2:
                        display_df.iloc[i, k] = fact_df.iloc[k + 1].values[0]
                    else:
                        display_df.iloc[i, k] = 1
            elif categ == 'Ultimate Incurred':
                for l in range(len(acc_yrs)):
                    display_df.iloc[i, l] = display_df.iloc[i - 2, l] * display_df.iloc[i - 1, l]
            elif categ == 'In-Force':
                for m in range(len(acc_yrs)):
                    display_df.iloc[i, m] = financial_df.iloc[len(financial_df) - m - 1 - (max(unique_years) - selected_year), 1]
            elif categ == 'Loss Cost':
                for n in range(len(acc_yrs)):
                    denom = display_df.iloc[i - 1, n]
                    if denom != 0:
                        display_df.iloc[i, n] = decimal.Decimal(display_df.iloc[i - 2, n]) / denom
                    else:
                        display_df.iloc[i, n] = 0
                # Calculate projections using logistic regression
                lcost = [(clm_yrs[len(clm_yrs) - q - 1], float(lc)) for q, lc in enumerate(display_df.iloc[i].values)]
                reform, proj_lcost_est, proj_lcost = perform_logistic_regression(lcost, reform_fact)
            elif categ == 'Claim Count':
                for o in range(len(acc_yrs)):
                    if coverage_idx in [1, 2]: # collision or total
                        display_df.iloc[i, o] = financial_df.iloc[len(financial_df) - o - 1 - (max(unique_years) - selected_year), 3]
                    else:
                        display_df.iloc[i, o] = financial_df.iloc[len(financial_df) - o - 1 - (max(unique_years) - selected_year), 2]
            elif categ == 'Frequency':
                for p in range(len(acc_yrs)):
                    denom = display_df.iloc[i - 3, p]
                    if denom != 0:
                        display_df.iloc[i, p] = 100 * decimal.Decimal(display_df.iloc[i - 1, p]) / denom
                    else:
                        display_df.iloc[i, p] = 0
                # Calculate projections
                freq = [(clm_yrs[len(clm_yrs) - q - 1], float(freq)) for q, freq in enumerate(display_df.iloc[i].values)]
                _, proj_freq_est, proj_freq = perform_logistic_regression(freq, reform_fact)
            elif categ == 'Severity':
                for q in range(len(acc_yrs)):
                    denom = display_df.iloc[i - 2, q]
                    if denom != 0:
                        display_df.iloc[i, q] = decimal.Decimal(display_df.iloc[i - 5, q]) / denom
                    else:
                        display_df.iloc[i, q] = 0
                # Calculate projections
                sev = [(clm_yrs[len(clm_yrs) - q - 1], float(sev)) for q, sev in enumerate(display_df.iloc[i].values)]
                _, proj_sev_est, proj_sev = perform_logistic_regression(sev, reform_fact)
            elif categ == 'Product Reform':
                for r in range(len(acc_yrs)):
                    display_df.iloc[i, r] = reform_fact[r]  # Store as boolean/int for chart
        
        # Store chart data for this coverage
        chart_data['coverages'][coverage_name] = {
            'actual_loss_cost': [float(x) for x in display_df.loc['Loss Cost'].values],
            'projected_loss_cost': [float(x) for x in proj_lcost],
            'actual_frequency': [float(x) for x in display_df.loc['Frequency'].values],
            'projected_frequency': [float(x) for x in proj_freq],
            'actual_severity': [float(x) for x in display_df.loc['Severity'].values],
            'projected_severity': [float(x) for x in proj_sev],
            'reform_years': [list(reversed(clm_yrs))[i] for i, reform in enumerate(reform_fact) if reform],
            'reform_fact': reform_fact,
            'reform_details': get_reform_details_for_years(claimtrend_dict, clm_yrs, reform_fact, coverage_idx)
        }
    
    return chart_data


def get_reform_details_for_years(claimtrend_dict, clm_yrs, reform_fact, coverage_idx):
    """Determine specific reform types for each reform year based on coverage"""
    reform_details = {}
    
    # CRITICAL FIX: reform_fact was built using reversed(clm_yrs)
    # So reform_fact[0] corresponds to the LAST year in clm_yrs, not the first
    # We need to map the indices correctly
    reversed_clm_yrs = list(reversed(clm_yrs))
    
    for i, reform in enumerate(reform_fact):
        if reform:  # If there's a reform in this position
            # Get the year from reversed_clm_yrs, not clm_yrs
            year = reversed_clm_yrs[i]
            
            bi_reform = claimtrend_dict['bi_reform'][f'{year}']
            cl_reform = claimtrend_dict['cl_reform'][f'{year}']
            
            if coverage_idx == 0:  # Bodily Injury coverage
                # Only show if BI reform actually occurred
                if bi_reform:
                    reform_details[year] = 'Bodily Injury'
            elif coverage_idx == 1:  # Collision coverage  
                # Only show if CL reform actually occurred
                if cl_reform:
                    reform_details[year] = 'Collision'
            elif coverage_idx == 2:  # Total coverage
                # Show what actually happened - could be BI, CL, or both
                if bi_reform and cl_reform:
                    reform_details[year] = 'Bodily Injury + Collision'
                elif bi_reform:
                    reform_details[year] = 'Bodily Injury'
                elif cl_reform:
                    reform_details[year] = 'Collision'
    
    return reform_details


@login_required()
def decision_input(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = None
    sel_profit_margin = None
    mct_ratio = None
    mct_label = None
    mct_pass = None
    profit_margins = None
    mktg_expenses = None
    trend_loss_margins = None
    osfi_alert = None
    current_prem = None
    indicated_prem = None
    rate_chg = None
    froze_lock = False
    decisions_locked = False
    is_novice_game = False
    osfi_intervention = False  # New flag to track actual OSFI intervention

    # Determine game difficulty
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass

    selected_year = request.POST.get('year')
    selected_year = int(selected_year) if selected_year else None

    sel_profit_margin = request.POST.get('profit')
    sel_profit_margin = int(float(sel_profit_margin) * 10) if sel_profit_margin else None

    sel_mktg_expense = request.POST.get('mktg')
    sel_mktg_expense = int(float(sel_mktg_expense) * 10) if sel_mktg_expense else None

    if not is_novice_game:
        sel_trend_loss_margin = request.POST.get('loss')
        sel_trend_loss_margin = int(float(sel_trend_loss_margin) * 10) if sel_trend_loss_margin else None
    else:
        sel_trend_loss_margin = 0  # Changed from 2 to 0 for Novice games

    template_name = 'Pricing/decision_input.html'

    indication_obj = Indications.objects.filter(game_id=game, player_id=user)
    claimtrend_data = ClaimTrends.objects.filter(game_id=game)

    unique_years = indication_obj.order_by('-year').values_list('year', flat=True).distinct()
    if unique_years:
        if selected_year not in unique_years:
            selected_year = unique_years[0]

        financial_data = Financials.objects.filter(game_id=game, player_id=user)
        financial_data_list = list(financial_data.values('year', 'in_force', 'written_premium'))
        financial_df = pd.DataFrame(financial_data_list)
        financial_df = financial_df[financial_df['year'] > (selected_year - 5)]
        financial_df = financial_df.sort_values('year', ascending=True)

        if not financial_df.empty:
            indication_data_dict = list(indication_obj.filter(year=selected_year).values('indication_data'))[0]['indication_data']
            devl_data = indication_data_dict['devl_data']
            wts = indication_data_dict['indic_wts']
            fixed_exp = decimal.Decimal(indication_data_dict['fixed_exp'])
            prem_var_cost = decimal.Decimal(indication_data_dict['prem_var_cost'])
            expos_var_cost = decimal.Decimal(indication_data_dict['expos_var_cost'])
            mct_ratio = decimal.Decimal(indication_data_dict['mct_ratio'])
            mct_capital_reqd = indication_data_dict['mct_capital_reqd']
            pass_capital_test = indication_data_dict['pass_capital_test']
            mct_label = f'MCT Ratio (Target @ {100*mct_capital_reqd:,.1f}%):'

            clm_yrs = indication_data_dict['acc_yrs']
            acc_yrs = [f'Acc Yr {acc_yr}' for acc_yr in clm_yrs]
            devl_mths = indication_data_dict['devl_mths']

            # CRITICAL: Ensure we get the current user's decision object
            decision_obj = Decisions.objects.filter(game_id=game, player_id=user, year=selected_year).first()
            if not decision_obj:
                messages.error(request, f"Decision object not found for user {user} in year {selected_year}")
                return redirect('Pricing-game_dashboard', game_id=game_id)
            
            decision_obj_last = Decisions.objects.filter(game_id=game, player_id=user, year=selected_year-1).first()

            # Check if decisions are locked (historical)
            if decision_obj.decisions_locked == True:
                decisions_locked = True

            # Determine OSFI intervention based on capital test
            if pass_capital_test != 'Pass':
                osfi_intervention = True
                froze_lock = True  # Only freeze for actual OSFI intervention

            # Get min/max ranges from server-side configuration - no hard-coded fallbacks
            profit_min = decision_obj.sel_profit_margin_min
            profit_max = decision_obj.sel_profit_margin_max
            mktg_min = decision_obj.sel_exp_ratio_mktg_min
            mktg_max = decision_obj.sel_exp_ratio_mktg_max
            
            if profit_min is None or profit_max is None:
                messages.error(request, f"Server error: Missing profit margin ranges for year {selected_year}")
                return redirect('Pricing-game_dashboard', game_id=game_id)
                
            if mktg_min is None or mktg_max is None:
                messages.error(request, f"Server error: Missing marketing expense ranges for year {selected_year}")
                return redirect('Pricing-game_dashboard', game_id=game_id)
            
            if not is_novice_game:
                trend_loss_min = decision_obj.sel_loss_trend_margin_min
                trend_loss_max = decision_obj.sel_loss_trend_margin_max
                if trend_loss_min is None or trend_loss_max is None:
                    messages.error(request, f"Server error: Missing trend loss margin ranges for year {selected_year}")
                    return redirect('Pricing-game_dashboard', game_id=game_id)
            
            # Generate dropdown options from server-provided ranges
            profit_margins = [f"{x/10:.1f}" for x in range(profit_min, profit_max + 1, 2)]  # 0.2% steps
            mktg_expenses = [f"{x/10:.1f}" for x in range(mktg_min, mktg_max + 1, 2)]     # 0.2% steps

            if not is_novice_game:
                trend_loss_margins = [f"{x/10:.1f}" for x in range(trend_loss_min, trend_loss_max + 1, 2)]  # 0.2% steps
            else:
                trend_loss_margins = []
            
            ret_from_confirm = request.session.get('ret_from_confirm', False)
            if ret_from_confirm is True or decisions_locked is True:
                # Use stored values when returning from confirm or locked
                sel_profit_margin = decision_obj.sel_profit_margin
                sel_mktg_expense = decision_obj.sel_exp_ratio_mktg
                if not is_novice_game:
                    sel_trend_loss_margin = decision_obj.sel_loss_trend_margin
                else:
                    sel_trend_loss_margin = 0
                request.session['ret_from_confirm'] = False
            else:
                # This block handles initial GET requests or POSTs not from the confirm page.
                # sel_profit_margin, sel_mktg_expense are from POST attempts or None.
                # sel_trend_loss_margin is from POST, or 0 if novice_game and no POST.

                if request.method == 'GET':
                    # For GET requests, logic depends on osfi_intervention status.
                    # osfi_intervention is True if pass_capital_test != 'Pass'.

                    if osfi_intervention:
                        # MCT Failure: Load from current year's DB, then midpoint. Ignore prior year.
                        sel_profit_margin = decision_obj.sel_profit_margin
                        sel_mktg_expense = decision_obj.sel_exp_ratio_mktg
                        if not is_novice_game:
                            sel_trend_loss_margin = decision_obj.sel_loss_trend_margin
                        # For novice, sel_trend_loss_margin is already 0 from initial processing.
                    else:
                        # No MCT Failure: Load from prior year, then current year's DB, then midpoint.
                        pm_from_last = None
                        me_from_last = None
                        tlm_from_last = None # For non-novice

                        if decision_obj_last:
                            pm_from_last = decision_obj_last.sel_profit_margin
                            me_from_last = decision_obj_last.sel_exp_ratio_mktg
                            if not is_novice_game:
                                tlm_from_last = decision_obj_last.sel_loss_trend_margin
                        
                        sel_profit_margin = pm_from_last
                        sel_mktg_expense = me_from_last
                        if not is_novice_game:
                            sel_trend_loss_margin = tlm_from_last
                        # For novice, sel_trend_loss_margin is already 0.

                        # If values are still None after trying decision_obj_last (or it didn't exist),
                        # try current year's decision_obj.
                        if sel_profit_margin is None:
                            sel_profit_margin = decision_obj.sel_profit_margin
                        if sel_mktg_expense is None:
                            sel_mktg_expense = decision_obj.sel_exp_ratio_mktg
                        if not is_novice_game and sel_trend_loss_margin is None:
                            sel_trend_loss_margin = decision_obj.sel_loss_trend_margin
                        # For novice, sel_trend_loss_margin remains 0.
                
                # Fallback to midpoint default if still None after all attempts (applies to GET and POST if values were missing and DB was None).
                if sel_profit_margin is None:
                    sel_profit_margin = (profit_min + profit_max) // 2
                
                if sel_mktg_expense is None:
                    sel_mktg_expense = (mktg_min + mktg_max) // 2
                
                if not is_novice_game:
                    if sel_trend_loss_margin is None:
                        sel_trend_loss_margin = (trend_loss_min + trend_loss_max) // 2
                else: # Novice game
                    if sel_trend_loss_margin is None: # Safeguard, should be 0 from initial POST processing for GET.
                        sel_trend_loss_margin = 0
            
            # Determine OSFI alert status from server-side pass_capital_test
            if pass_capital_test == 'Pass':
                mct_pass = '<span class="green-text"><b>' + pass_capital_test + '</b></span>'
                osfi_alert = False
            else:
                mct_pass = '<span class="red-text"><b>' + pass_capital_test + '</b></span>'
                osfi_alert = True
                # Note: OSFI intervention values should already be set by server-side game logic
                # GUI just reads and displays the server-mandated values

            # DEBUG: Print final selected values after all logic is complete
            # print(f"DEBUG: Final selected values - profit: {sel_profit_margin/10:.1f}%, mktg: {sel_mktg_expense/10:.1f}%, trend: {sel_trend_loss_margin/10:.1f}% (novice: {is_novice_game})")

            claimtrend_obj = claimtrend_data.filter(year=selected_year).first()
            if claimtrend_obj:
                claimtrend_dict = claimtrend_obj.claim_trends
                reform_fact = []
                for yr in reversed(clm_yrs):
                    reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'] or claimtrend_dict['cl_reform'][f'{yr}'])
            else:
                reform_fact = [False] * len(clm_yrs)

            df = pd.DataFrame(columns=acc_yrs, index=devl_mths)
            for i, devl_mth in enumerate(devl_mths):
                df.loc[devl_mth] = devl_data[i]

            transposed_df = df.T

            fact_labels = ['Age-to-Age']
            fact_devl_mths = copy.deepcopy(devl_mths)
            fact_devl_mths[0] = None
            fact_df = pd.DataFrame(columns=fact_labels, index=fact_devl_mths)

            for i, fact_devl_mth in enumerate(fact_devl_mths):
                if fact_devl_mth == fact_devl_mths[0]:
                    fact_df.iloc[0, 0] = 0
                if fact_devl_mth == fact_devl_mths[1]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 1])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-1])][:, 0])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[1, 0] = numerator / denominator
                if fact_devl_mth == fact_devl_mths[2]:
                    numerator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 2])
                    denominator = sum(transposed_df.values[0:len(acc_yrs[:-2])][:, 1])
                    if denominator == 0:
                        denominator = 1
                    fact_df.iloc[2, 0] = numerator / denominator
                    fact_df.iloc[1, 0] = fact_df.iloc[1, 0] * fact_df.iloc[2, 0]

            cols = ['Actual Paid', 'Devl Factor', 'Ultimate Incurred', get_force_term(game), 'Loss Cost', 'Trend Adj', 'Reform Adj', 'Weights',
                    'Adj Loss Cost', 'Fixed Expenses', 'Expos Var Expenses', 'Prem Var Expenses', 'Marketing Expenses', 'Profit Margin',
                    'Current Premium', 'Indicated Premium', 'Rate Change']
            display_yrs = [f'Acc Yr {acc_yr}' for acc_yr in clm_yrs]
            display_yrs.reverse()
            display_df = pd.DataFrame(columns=display_yrs, index=cols)
            display_df_fmt = pd.DataFrame(columns=display_yrs, index=cols)
            i = 0
            est_values = None
            wtd_lcost = None
            for categ, row in display_df.iterrows():
                if categ == 'Actual Paid':
                    for j in range(len(acc_yrs)):
                        display_df.iloc[i, j] = df.iloc[min(j, len(devl_mths) - 1), len(acc_yrs) - j - 1]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.0f}'.format(x))
                elif categ == 'Devl Factor':
                    for k in range(len(acc_yrs)):
                        if k < 2:
                            display_df.iloc[i, k] = fact_df.iloc[k + 1].values[0]
                        else:
                            display_df.iloc[i, k] = 1
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.3f}'.format(x))
                elif categ == 'Ultimate Incurred':
                    for l in range(len(acc_yrs)):
                        display_df.iloc[i, l] = display_df.iloc[i - 2, l] * display_df.iloc[i - 1, l]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.0f}'.format(x))
                elif categ == get_force_term(game):
                    for m in range(len(acc_yrs)):
                        display_df.iloc[i, m] = financial_df.iloc[len(financial_df) - m - 1 - (max(unique_years) - selected_year), 1]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.0f}'.format(x))
                    in_force = display_df.iloc[i, 0]
                elif categ == 'Loss Cost':
                    for n in range(len(acc_yrs)):
                        denom = display_df.iloc[i - 1, n]
                        if denom != 0:
                            display_df.iloc[i, n] = decimal.Decimal(display_df.iloc[i - 2, n]) / denom
                        else:
                            display_df.iloc[i, n] = 0
                    lcost = [(clm_yrs[len(clm_yrs) - q - 1], float(lc)) for q, lc in enumerate(display_df.iloc[i].values)]
                    est_values = perform_logistic_regression_indication(lcost, reform_fact, sel_trend_loss_margin)
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Trend Adj':
                    for o in range(len(acc_yrs)):
                        display_df.iloc[i, o] = est_values['trend'][o]
                        if int(sel_trend_loss_margin) > 0:
                            prefix = '<span class="blue-text">'
                            postfix = '</span>'
                        elif int(sel_trend_loss_margin) < 0:
                            prefix = '<span class="red-text">'
                            postfix = '</span>'
                        else:
                            prefix = ''
                            postfix = ''
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else prefix + '{:,.3f}'.format(x) + postfix)
                elif categ == 'Reform Adj':
                    for p in range(len(acc_yrs)):
                        display_df.iloc[i, p] = est_values['reform'][p]
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.3f}'.format(x))
                elif categ == 'Weights':
                    for q in range(len(acc_yrs)):
                        display_df.iloc[i, q] = decimal.Decimal(wts[q])
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '{:,.0f}%'.format(100 * x))
                elif categ == 'Adj Loss Cost':
                    for r in range(len(acc_yrs)):
                        display_df.iloc[i, r] = decimal.Decimal(display_df.iloc[i-4, r]) * decimal.Decimal(display_df.iloc[i-3, r]) * decimal.Decimal(display_df.iloc[i-2, r])
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))

                    wtd_lcost = sum(display_df.iloc[i] * display_df.iloc[i-1])
                    wtd_ind = i
                elif categ in ['Fixed Expenses', 'Expos Var Expenses', 'Prem Var Expenses', 'Marketing Expenses', 'Profit Margin', 'Indicated Premium', 'Current Premium', 'Rate Change']:
                    for s in range(len(acc_yrs)):
                        display_df.iloc[i, s] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                i += 1

            display_df_fmt.insert(0, f'Proj AY {max(clm_yrs) + 1}', '')
            display_df_fmt.iloc[wtd_ind, 0] = f'${wtd_lcost:,.2f}'
            if in_force != 0:
                fixed_cost = fixed_exp / in_force
                display_df_fmt.iloc[wtd_ind + 1, 0] = f'${round(fixed_exp/in_force,2):,.2f}'
                current_prem = float(round(financial_df.iloc[len(financial_df) - 1 - (max(unique_years) - selected_year)]['written_premium'] / in_force, 2))
            else:
                display_df_fmt.iloc[wtd_ind + 1, 0] = 0
                current_prem = 0
            display_df_fmt.iloc[wtd_ind + 2, 0] = f'${round(expos_var_cost, 2):,.2f}'
            display_df_fmt.iloc[wtd_ind + 3, 0] = f'{round(prem_var_cost * 100, 1):,.1f}%'
            display_df_fmt.iloc[wtd_ind + 4, 0] = f'{round(int(sel_mktg_expense) / 10, 1):,.1f}%'
            display_df_fmt.iloc[wtd_ind + 5, 0] = f'{round(int(sel_profit_margin) / 10, 1):,.1f}%'
            indicated_prem = float(round(((wtd_lcost + expos_var_cost + fixed_cost) / (1 - prem_var_cost - (decimal.Decimal(int(sel_mktg_expense)) / 1000) -
                                                                          (decimal.Decimal(int(sel_profit_margin)) / 1000))), 2))
            if request.POST.get('Submit') == 'Submit':
                test_prem = request.session.get('indicated_prem', 0)
                if test_prem != indicated_prem:
                    messages.warning(request, "Premium re-calculated due to changed parameters.  Please review and submit again.")
                else:
                    if not Lock.acquire_lock(game_id, request.user):
                        messages.warning(request, "Another team-member is in the submission page.  Cannot submit.")
                        return redirect('Pricing-game_dashboard', game_id=game_id)
                    else:
                        # CRITICAL FIX: Use atomic transaction to ensure consistency
                        with transaction.atomic():
                            decision_obj.sel_profit_margin = int(sel_profit_margin)
                            decision_obj.sel_exp_ratio_mktg = int(sel_mktg_expense)
                            if not is_novice_game:
                                decision_obj.sel_loss_trend_margin = int(sel_trend_loss_margin)
                            else:
                                decision_obj.sel_loss_trend_margin = 0  # Changed from 2 to 0 for Novice games
                            decision_obj.sel_avg_prem = indicated_prem
                            decision_obj.save()
                            
                        request.session['locked_game_id'] = game_id
                        request.session['indicated_prem'] = indicated_prem
                        request.session['selected_year'] = selected_year
                        return redirect('Pricing-decision_confirm', game_id=game_id)
            request.session['indicated_prem'] = indicated_prem
            display_df_fmt.iloc[wtd_ind + 6, 0] = f'${current_prem:,.2f}'
            if current_prem != 0:
                rate_chg = indicated_prem / current_prem - 1
            else:
                rate_chg = 0
            display_df_fmt.iloc[wtd_ind + 7, 0] = f'${indicated_prem:,.2f}'
            display_df_fmt.iloc[wtd_ind + 8, 0] = f'{round(100 * rate_chg, 1):,.1f}%'

            index_list = [8, 12, 16, 19]  # insert blank rows
            blank_row = pd.DataFrame([['' for _ in display_df_fmt.columns]], columns=display_df_fmt.columns)
            for index in index_list:
                display_df_fmt = pd.concat([display_df_fmt.iloc[:index], blank_row, display_df_fmt.iloc[index:]])
                display_df_fmt.index = display_df_fmt.index.where(display_df_fmt.index != 0, ' ')

            financial_data_table = display_df_fmt.to_html(classes='my-financial-table',
                                                          border=0, justify='initial',
                                                          index=True, escape=False)

            # All data is ready - create context and render
            context = {
                'title': ' - Decision Input',
                'game': game,
                'financial_data_table': financial_data_table,
                'has_financial_data': indication_obj.exists(),
                'unique_years': unique_years,
                'selected_year': selected_year,
                'mct_label': mct_label,
                'mct_ratio': f'{round(100 * mct_ratio if mct_ratio is not None else 0, 1)}%',
                'mct_pass': mct_pass,
                'profit_margins': profit_margins,
                'sel_profit_margin': f'{sel_profit_margin/10:.1f}',
                'mktg_expenses': mktg_expenses,
                'sel_mktg_expense': f'{sel_mktg_expense/10:.1f}',
                'trend_loss_margins': trend_loss_margins,
                'sel_trend_loss_margin': f'{sel_trend_loss_margin/10:.1f}' if not is_novice_game else None,
                'froze_lock': froze_lock,
                'osfi_alert': osfi_alert,
                'osfi_intervention': osfi_intervention,  # New flag to distinguish OSFI intervention from historical locks
                'decisions_locked': decisions_locked,
                'is_novice_game': is_novice_game,
                'current_prem': f'${current_prem if current_prem is not None else 0:,.2f}',
                'indicated_prem': f'${indicated_prem if indicated_prem is not None else 0:,.2f}',
                'rate_chg': f'<span class="violet-text">{round(100 * rate_chg if rate_chg is not None else 0,1):,.1f}% </span>',
            }
            return render(request, template_name, context)
        else:
            # Financial data not ready
            messages.warning(request, "Financial data not yet available. Please wait for data processing to complete.")
            return redirect('Pricing-game_dashboard', game_id=game_id)
    else:
        # Indication data not ready
        messages.warning(request, "Indication data processing not yet complete. Please await notification in the Message Centre.")
        return redirect('Pricing-game_dashboard', game_id=game_id)


@login_required
def decision_confirm(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames, Q(game_id=game_id))
    players_list = game.players.all()
    human_players = []
    for player in players_list:
        if player.player_type == 'user':
            human_players.append(player.player_name)
    if game.game_observable is False and user.username not in human_players:
        raise Http404("You are not permitted to view the game.")
    
    # Determine game difficulty
    is_novice_game = False
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            is_novice_game = True
    except GamePrefs.DoesNotExist:
        pass

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        # Release the lock
        try:
            Lock.release_lock(game_id, request.user)
            del request.session['locked_game_id']
        except:
            pass

        return redirect('Pricing-game_dashboard', game_id=game_id)

    if request.POST.get('Return to Indication') == 'Return to Indication':
        request.session['ret_from_confirm'] = True
        # Release the lock
        try:
            Lock.release_lock(game_id, request.user)
            del request.session['locked_game_id']
        except:
            pass

        return redirect('Pricing-decision_input', game_id=game_id)

    selected_year = request.session.get('selected_year', 0)
    decision_obj = Decisions.objects.filter(game_id=game, player_id=user, year=selected_year).first()
    indication_obj = Indications.objects.filter(game_id=game, player_id=user, year=selected_year)
    unique_years = indication_obj.order_by('-year').values_list('year', flat=True).distinct()

    indication_data_dict = list(indication_obj.values('indication_data'))[0]['indication_data']
    mct_ratio = decimal.Decimal(indication_data_dict['mct_ratio'])
    mct_capital_reqd = indication_data_dict['mct_capital_reqd']
    pass_capital_test = indication_data_dict['pass_capital_test']
    mct_label = f'MCT Ratio (Target @ {100 * mct_capital_reqd:,.1f}%):'

    if pass_capital_test == 'Pass':
        mct_pass = '<span class="green-text"><b>' + pass_capital_test + '</b></span>'
        osfi_alert = False
    else:
        mct_pass = '<span class="red-text"><b>' + pass_capital_test + '</b></span>'
        osfi_alert = True
        froze_lock = True

    if request.POST.get('Confirm Decisions') == 'Confirm Decisions':
        if decision_obj.decisions_locked is True:
            messages.warning(request, f'Decisions already submitted for year: {decision_obj.year}')
            return redirect('Pricing-game_dashboard', game_id=game_id)
        
        # Lock decisions and save - server-side logic handles any OSFI constraints
        with transaction.atomic():
            decision_obj.decisions_locked = True
            decision_obj.save()
            
            # Create the approval message AFTER locking decisions
            # This ensures proper sequencing for the server simulation
            message = ChatMessage(
                from_user=None,
                game_id=IndivGames.objects.get(game_id=game_id),
                content=f'Regulatory filing for {request.user} approved.',
            )
            message.save()

        # Release the lock after successful submission
        try:
            Lock.release_lock(game_id, request.user)
            del request.session['locked_game_id']
        except:
            pass
            
        request.session['ret_from_confirm'] = False
        messages.success(request, f'Decisions submitted for year: {decision_obj.year}')

        return redirect('Pricing-game_dashboard', game_id=game_id)

    template_name = 'Pricing/decision_confirm.html'
    curr_avg_prem = decision_obj.curr_avg_prem
    final_avg_prem = decision_obj.sel_avg_prem
    if curr_avg_prem != 0:
        rate_chg = final_avg_prem / curr_avg_prem -1
    else:
        rate_chg = 0

    context = {
        'title': ' - Confirm Decisions',
        'game': game,
        'mct_label': mct_label,
        'mct_pass': mct_pass,
        'mct_ratio': f'{round(100 * mct_ratio, 1)}%',
        'current_prem': f'${curr_avg_prem:,.2f}',
        'indicated_prem': f'${final_avg_prem:,.2f}',
        'rate_chg': f'<span class="violet-text">{round(100 * rate_chg, 1):,.1f}% </span>',
        'sel_profit_margin': f'{decision_obj.sel_profit_margin/10:.1f}',
        'sel_trend_loss_margin': f'{decision_obj.sel_loss_trend_margin/10:.1f}',
        'sel_mktg_expense': f'{decision_obj.sel_exp_ratio_mktg/10:.1f}',
        'is_novice_game': is_novice_game,
        'osfi_alert': osfi_alert,
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
        ).order_by('sequence_number')

        message_list = []
        review_cnt = 0
        for msg in messages:
            # Perform timezone conversion to Django's default timezone
            timestamp_with_timezone = timezone.localtime(msg.timestamp)
            from_sender = msg.from_user.username if msg.from_user else "game_server"
            if msg.content == 'Review decisions.' and from_sender == 'game_server':
                review_cnt += 1
            message_list.append({
                'from_sender': from_sender,
                'time': timestamp_with_timezone.strftime('%H:%M:%S'),
                'content': msg.content,
                'sequence_number': msg.sequence_number
            })

        message_list = message_list[-50:]

        return JsonResponse({"messages": message_list, "review_cnt": review_cnt})


@login_required
def fetch_game_list(request):
    if request.method == 'GET':
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
                filter=Q(players__player_type='user')))

        for game in all_games:
            game.additional_players_needed = game.human_player_cnt - game.current_human_player_cnt

        active_games = [
            game for game in all_games if game.status in ['active', 'waiting for players']
        ]
        accessible_games = [
            game for game in all_games if game.status in ['running', 'completed']
        ]

        # Convert games to JSON-serializable format
        active_games_data = []
        for game in active_games:
            local_timestamp = timezone.localtime(game.timestamp)
            active_games_data.append({
                'game_id': game.game_id,
                'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'status': game.status,
                'game_type': game.game_type,
                'additional_players_needed': game.additional_players_needed if game.game_type != 'individual' else 0
            })

        accessible_games_data = []
        for game in accessible_games:
            local_timestamp = timezone.localtime(game.timestamp)
            accessible_games_data.append({
                'game_id': game.game_id,
                'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'status': game.status,
                'game_type': game.game_type
            })

        return JsonResponse({
            "active_games": active_games_data,
            "accessible_games": accessible_games_data
        })