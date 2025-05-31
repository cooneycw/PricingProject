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
from django.db.models import Q, Count, Case, When, Value, CharField, Max, Sum, Exists
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
            selected_years = sorted([yr for yr in all_data_years if yr <= selected_year], reverse=True)[:4]
            df = df.sort_values('year', ascending=False)

            # Creating a copy of the filtered DataFrame
            df_latest = df[df['year'].isin(selected_years)].copy()

            # Transposing the DataFrame to get years as columns and metrics as rows
            transposed_df = df_latest.set_index('year').T  # Set 'year' as index before transposing
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

    context = {
        'title': ' - Financial Report',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': financial_data.exists(),
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': int(selected_year) if selected_year else None,  # Convert selected_year to int if it's not None
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

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
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

    if unique_years:  # Proceed if there are any financial years available
        if selected_year not in unique_years:
            selected_year = unique_years[0]
        request.session['selected_year'] = selected_year
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

            displayed_players_names = [player_list[i] for i in displayed_players]

            # Creating a new DataFrame with only the displayed players
            transposed_df = transposed_df[displayed_players_names]

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
            # if selected_player != industry_id:
            #     index = 9
            #     transposed_df = pd.concat([transposed_df.iloc[:index], blank_row, transposed_df.iloc[index:]])
            #     transposed_df.index = transposed_df.index.where(transposed_df.index != 0, ' ')

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
            # Rename the 'player_name' column to 'Company'
            df = df.rename(columns={'player_name': 'Company'})
            df['Valuation Rank'] = df['total_valuation'].rank(ascending=False, method='min').astype(int)

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
        }
    return render(request, template_name, context)


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
    loss_margins = None
    osfi_alert = None
    current_prem = None
    indicated_prem = None
    rate_chg = None
    froze_lock = False
    decisions_locked = False

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    sel_profit_margin = request.POST.get('profit')
    sel_profit_margin = sel_profit_margin if sel_profit_margin else None

    sel_mktg_expense = request.POST.get('mktg')
    sel_mktg_expense = sel_mktg_expense if sel_mktg_expense else None

    sel_loss_margin = request.POST.get('loss')
    sel_loss_margin = sel_loss_margin if sel_loss_margin else None

    template_name = 'Pricing/decision_input.html'

    indication_obj = Indications.objects.filter(game_id=game, player_id=user)
    claimtrend_data = ClaimTrends.objects.filter(game_id=game)

    unique_years = indication_obj.order_by('-year').values_list('year', flat=True).distinct()
    if unique_years:  # Proceed if there are any financial years available
        if selected_year not in unique_years:
            selected_year = unique_years[0]

        # coverages = ['Bodily Injury', 'Collision', 'Total']
        # for count_id, coverage in enumerate(coverages):
        #    coverage_list.append(coverage)
        #    coverage_id_list.append(count_id)
        # coverage_options = list(zip(coverage_id_list, coverage_list))
        financial_data = Financials.objects.filter(game_id=game, player_id=user)
        financial_data_list = list(financial_data.values('year', 'in_force', 'written_premium'))
        financial_df = pd.DataFrame(financial_data_list)
        financial_df = financial_df[financial_df['year'] > (selected_year - 5)]
        financial_df = financial_df.sort_values('year', ascending=True)

        if not financial_df.empty:
            indication_obj = Indications.objects.filter(game_id=game, player_id=user, year=selected_year)
            indication_data_dict = list(indication_obj.values('indication_data'))[0]['indication_data']
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

            all_data_years = copy.deepcopy(clm_yrs)  # Get all unique years
            all_data_years.reverse()

            decision_obj = Decisions.objects.filter(game_id=game, player_id=user, year=selected_year).first()
            decision_obj_last = Decisions.objects.filter(game_id=game, player_id=user, year=selected_year-1).first()

            if decision_obj.decisions_locked == True:
                froze_lock = True
                decisions_locked = True

            profit_margins = [f'{x/10:.1f}' for x in range(decision_obj.sel_profit_margin_min,
                                               1 + decision_obj.sel_profit_margin_max)]

            mktg_expenses = [f'{x/10:.1f}' for x in range(decision_obj.sel_exp_ratio_mktg_min,
                             1 + decision_obj.sel_exp_ratio_mktg_max)]

            loss_margins = [f'{x/10:.1f}' for x in range(decision_obj.sel_loss_trend_margin_min,
                                                   1 + decision_obj.sel_loss_trend_margin_max)]

            ret_from_confirm = request.session.get('ret_from_confirm', False)
            if ret_from_confirm is True or decisions_locked is True:
                last_profit_margin = decision_obj.sel_profit_margin
                last_mktg_expense = decision_obj.sel_exp_ratio_mktg
                last_loss_margin = decision_obj.sel_loss_trend_margin
                request.session['ret_from_confirm'] = False
            elif decision_obj_last:
                last_profit_margin = decision_obj_last.sel_profit_margin
                last_mktg_expense = decision_obj_last.sel_exp_ratio_mktg
                last_loss_margin = decision_obj_last.sel_loss_trend_margin
            else:
                last_profit_margin = None
                last_mktg_expense = None
                last_loss_margin = None

            if last_profit_margin is not None and sel_profit_margin is None:
                sel_profit_margin = f'{last_profit_margin/10:.1f}'

            if last_mktg_expense is not None and sel_mktg_expense is None:
                sel_mktg_expense = f'{last_mktg_expense/10:.1f}'

            if last_loss_margin is not None and sel_loss_margin is None:
                sel_loss_margin = f'{last_loss_margin/10:.1f}'

            # pass_capital_test = 'Fail'
            if pass_capital_test == 'Pass':
                mct_pass = '<span class="green-text"><b>' + pass_capital_test + '</b></span>'
                osfi_alert = False
            else:
                mct_pass = '<span class="red-text"><b>' + pass_capital_test + '</b></span>'
                sel_profit_margin = '7.0'  # Instead of '0.7'
                sel_mktg_expense = '0.0'
                sel_loss_margin = '2.0'    # Instead of '0.2'
                osfi_alert = True
                froze_lock = True

            claimtrend_obj = claimtrend_data.filter(year=selected_year).first()
            if claimtrend_obj:
                claimtrend_dict = claimtrend_obj.claim_trends

            reform_fact = []
            for yr in reversed(clm_yrs):
                reform_fact.append(claimtrend_dict['bi_reform'][f'{yr}'] or claimtrend_dict['cl_reform'][f'{yr}'])

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
                    est_values = perform_logistic_regression_indication(lcost, reform_fact, int(float(sel_loss_margin) * 10))
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Trend Adj':
                    for o in range(len(acc_yrs)):
                        display_df.iloc[i, o] = est_values['trend'][o]
                        if float(sel_loss_margin) > 0:
                            prefix = '<span class="blue-text">'
                            postfix = '</span>'
                        elif float(sel_loss_margin) < 0:
                            prefix = '<span class="red-text">'
                            postfix = '</span>'
                        else:
                            prefix = ''
                            postfix = ''
                    display_df_fmt.iloc[i] = prefix + display_df.iloc[i].map(lambda x: '' if x == 0 else prefix + '{:,.3f}'.format(x) + postfix)
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
                elif categ == 'Fixed Expenses':
                    for s in range(len(acc_yrs)):
                        display_df.iloc[i, s] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Expos Var Expenses':
                    for t in range(len(acc_yrs)):
                        display_df.iloc[i, t] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Prem Var Expenses':
                    for u in range(len(acc_yrs)):
                        display_df.iloc[i, u] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Marketing Expenses':
                    for v in range(len(acc_yrs)):
                        display_df.iloc[i, v] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Profit Margin':
                    for w in range(len(acc_yrs)):
                        display_df.iloc[i, w] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Indicated Premium':
                    for x in range(len(acc_yrs)):
                        display_df.iloc[i, x] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Current Premium':
                    for y in range(len(acc_yrs)):
                        display_df.iloc[i, y] = 0
                    display_df_fmt.iloc[i] = display_df.iloc[i].map(lambda x: '' if x == 0 else '${:,.2f}'.format(x))
                elif categ == 'Rate Change':
                    for z in range(len(acc_yrs)):
                        display_df.iloc[i, z] = 0
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
            display_df_fmt.iloc[wtd_ind + 4, 0] = f'{round(int(float(sel_mktg_expense))/10, 1):,.1f}%'
            display_df_fmt.iloc[wtd_ind + 5, 0] = f'{round(int(float(sel_profit_margin))/10, 1):,.1f}%'
            indicated_prem = float(round(((wtd_lcost + expos_var_cost + fixed_cost) / (1 - prem_var_cost - (decimal.Decimal(int(float(sel_mktg_expense))) / 1000) -
                                                                          (decimal.Decimal(int(float(sel_profit_margin))) / 1000))), 2))
            if request.POST.get('Submit') == 'Submit':
                test_prem = request.session.get('indicated_prem', 0)
                if test_prem != indicated_prem:
                    messages.warning(request, "Premium re-calculated due to changed parameters.  Please review and submit again.")
                else:
                    if not Lock.acquire_lock(game_id, request.user):
                        messages.warning(request, "Another team-member is in the submission page.  Cannot submit.")
                        return redirect('Pricing-game_dashboard', game_id=game_id)
                    else:
                        decision_obj.sel_profit_margin = int(float(sel_profit_margin) * 10)
                        decision_obj.sel_exp_ratio_mktg = int(float(sel_mktg_expense) * 10)
                        decision_obj.sel_loss_trend_margin = int(float(sel_loss_margin) * 10)
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

        else:
            financial_data_table = '<p>No detailed financial data to display for the selected years.</p>'
    else:
        financial_data_table = '<p>No financial data available.</p>'


    context = {
        'title': ' - Indication / Decisions',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': indication_obj.exists(),
        'unique_years': unique_years,
        'selected_year': selected_year,
        'mct_label': mct_label,
        'mct_ratio': f'{round(100 * mct_ratio if mct_ratio is not None else 0, 1)}%',
        'mct_pass': mct_pass,
        'profit_margins': profit_margins,
        'sel_profit_margin': f'{sel_profit_margin}',
        'mktg_expenses': mktg_expenses,
        'sel_mktg_expense': f'{sel_mktg_expense}',
        'loss_margins': loss_margins,
        'sel_loss_margin': f'{sel_loss_margin}',
        'froze_lock': froze_lock,
        'osfi_alert': osfi_alert,
        'decisions_locked': decisions_locked,
        'current_prem': f'${current_prem if current_prem is not None else 0:,.2f}',
        'indicated_prem': f'${indicated_prem if indicated_prem is not None else 0:,.2f}',
        'rate_chg': f'<span class="violet-text">{round(100 * rate_chg if rate_chg is not None else 0,1):,.1f}% </span>',
    }
    return render(request, template_name, context)


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
        request.session['ret_from_confirm'] = False
        decision_obj.decisions_locked = True
        decision_obj.save()

        # Release the lock
        try:
            Lock.release_lock(game_id, request.user)
            del request.session['locked_game_id']
        except:
            pass
        messages.success(request, f'Decisions submitted for year: {decision_obj.year}')
        message = ChatMessage(
            from_user=None,
            game_id=IndivGames.objects.get(game_id=game_id),
            content=f'Regulatory filing for {request.user} approved.',
        )
        message.save()

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
        'sel_mktg_expense': f'{decision_obj.sel_exp_ratio_mktg/10:.1f}',
        'sel_loss_margin': f'{decision_obj.sel_loss_trend_margin/10:.1f}',
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
