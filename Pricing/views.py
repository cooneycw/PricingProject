import uuid
import copy
import pytz
import numpy as np
import pandas as pd
import decimal
from .utils import reverse_pv_index, calculate_growth_rate, calculate_avg_profit, calculate_future_value, perform_logistic_regression
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Case, When, Value, CharField, Max, Sum
from datetime import timedelta
from PricingProject.settings import CONFIG_FRESH_PREFS, CONFIG_MAX_HUMAN_PLAYERS
from .forms import GamePrefsForm
from .models import GamePrefs, IndivGames, Players, MktgSales, Financials, Industry, Valuation, Triangles, ClaimTrends, Indications, Decisions, ChatMessage
pd.set_option('display.max_columns', None)  # None means show all columns

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
    green_list = ['Government officials', 'Injury reform', 'product reform', 'after observing']
    context = {
        'title': ' - Dashboard',
        'game': game,
        'green_list': green_list
    }
    return render(request, template_name, context)


@login_required()
def mktgsales_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

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
                    new_row_name = 'Beginning-In-Force'
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
                    new_row_name = 'Ending-In-Force'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer
                elif index == 'in_force_ind':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Industry-In-Force'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer

                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)

                # Continue with additional conditions for more rows as needed

            for year in transposed_df.columns:
                # Convert the marketing expenses from string to float for calculation
                quotes = float(transposed_df.at['Quotes', year].replace(',', ''))
                sales = float(transposed_df.at['Sales', year].replace(',', ''))
                canx = float(transposed_df.at['Cancellations', year].replace(',', ''))
                in_force = float(transposed_df.at['Beginning-In-Force', year].replace(',', ''))
                in_force_ind = float(transposed_df.at['Industry-In-Force', year].replace(',', ''))
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
                if in_force_ind > 0:
                    mkt_share = (in_force / in_force_ind) * 100
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

            insert_position_mktshare = transposed_df_retention.index.get_loc('Industry-In-Force') + 1
            df_top_mktshare = transposed_df_retention.iloc[:insert_position_mktshare]
            df_bottom_mktshare = transposed_df_close.iloc[insert_position_mktshare:]
            transposed_df = pd.concat([df_top_mktshare, mkt_share_ratio_df, df_bottom_mktshare])

            # Convert the final, formatted DataFrame to HTML for rendering
            if len(transposed_df.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df.columns)
                for i in range(missing_years):
                    transposed_df[f'{selected_year - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

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
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

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
                    new_row_name = 'In-force'
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

            # Convert the final, formatted DataFrame to HTML for rendering
            if len(transposed_df.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df.columns)
                for i in range(missing_years):
                    transposed_df[f'{selected_year - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

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
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

    template_name = 'Pricing/industry_reports.html'
    industry_data = Industry.objects.filter(game_id=game)
    unique_years = industry_data.order_by('-year').values_list('year', flat=True).distinct()
    latest_year = unique_years[0] if unique_years else None

    ordered_data = industry_data.order_by('id', 'player_name')

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
    for count_id, unique_player in enumerate(distinct_players):
        player_name = f"{1 + count_id:02d} - {unique_player}"
        if unique_player == request.user.username:
            default_player_id = count_id
        player_list.append(player_name)
        player_id_list.append(count_id)

    industry_id = len(player_list)
    player_list.append(f"{1 + len(player_list):02d} - Total Industry")
    player_id_list.append(len(player_id_list))
    distinct_players.append('Total Industry')

    player_options = list(zip(player_id_list, player_list))

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.GET.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    selected_player = request.GET.get('player')
    selected_player = int(selected_player) if selected_player else default_player_id

    if unique_years:  # Proceed if there are any financial years available
        if selected_player == industry_id:
            # Create a DataFrame for the total view, excluding 'capital_test' and 'capital_ratio'
            company_data = Industry.objects.filter(game_id=game).values('year').annotate(
                written_premium=Sum('written_premium'),
                annual_expenses=Sum('annual_expenses'),
                cy_losses=Sum('cy_losses'),
                profit=Sum('profit'),
                capital=Sum('capital')
            )
            company_data_list = list(
                company_data.values('year', 'written_premium', 'annual_expenses',
                                'cy_losses', 'profit',
                                'capital'))  # add more fields as necessary

        else:
            company_data = Industry.objects.filter(game_id=game, player_name=distinct_players[selected_player])
            company_data_list = list(
                company_data.values('year', 'written_premium', 'annual_expenses',
                                'cy_losses', 'profit',
                                'capital', 'capital_ratio', 'capital_test'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(company_data_list)

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
                elif index == 'capital_ratio' and industry_id != selected_player:
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Ratio'
                    transposed_df.loc[index] = row.apply(lambda x: f"{round(x * 100, 1)}%")  # formatting as an integer
                elif index == 'capital_test' and industry_id != selected_player:
                    # Rename and format the 'in_force' row
                    new_row_name = 'MCT Test'

                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)

            for year in transposed_df.columns:
                # Convert the marketing expenses from string to float for calculation
                wprem = float(transposed_df.at['Written Premium', year].replace('$', '').replace(',', ''))
                annual_expenses = float(transposed_df.at['Annual Expenses', year].replace('$', '').replace(',', ''))
                cy_losses = float(transposed_df.at['Calendar Year Losses', year].replace('$', '').replace(',', ''))
                # canx = float(transposed_df.at['Cancellations', year].replace(',', ''))
                #in_force = float(transposed_df.at['Beginning-In-Force', year].replace(',', ''))
                # in_force_ind = float(transposed_df.at['Industry-In-Force', year].replace(',', ''))


                # Calculate the percentage (ensuring not to divide by zero)
                if wprem > 0:
                    expense_ratio = (annual_expenses / wprem) * 100
                else:
                    expense_ratio = 0  # or None, or however you wish to represent this edge case

                expense_ratio_data[year] = f"{expense_ratio:.1f}%"  # formatted to one decimal places

                if wprem > 0:
                    loss_ratio = (cy_losses / wprem) * 100
                else:
                    loss_ratio = 0  # or None, or however you wish to represent this edge case

                loss_ratio_data[year] = f"{loss_ratio:.1f}%"  # formatted to one decimal places


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
            if len(transposed_df.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df.columns)
                for i in range(missing_years):
                    transposed_df[f'{selected_year - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

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
            if selected_player != industry_id:
                index = 9
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
        'company_selected': distinct_players[selected_player],
        'unique_years': unique_years,
        'latest_year': latest_year,
        'selected_year': selected_year,
        'player_options': player_options,
        'selected_player': selected_player,
    }
    return render(request, template_name, context)


@login_required()
def valuation_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.POST.get('year')  # Get the selected year from the query parameters
    selected_year = int(selected_year) if selected_year else None

    curr_pos = request.session.get('curr_pos', 0)
    template_name = 'Pricing/valuation_report.html'

    valuation_data = Valuation.objects.filter(game_id=game)
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
            val_df = val_df[val_df['year'] <= selected_year]
            val_df = val_df.sort_values(by=['player_name', 'year'])
            all_data_years = val_df['year'].unique()  # Get all unique years
            latest_year = all_data_years.max()
            earliest_year = max((latest_year - 10), all_data_years.min())
            valuation_period = f'Valuation Report utilizing: {earliest_year} - {latest_year} '

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
            for count_id, unique_player in enumerate(distinct_players):
                # player_name = f"{1 + count_id:02d} - {unique_player}"
                player_name = f"{unique_player}"
                if unique_player == request.user.username:
                    default_player_id = count_id
                player_list.append(player_name)
                player_id_list.append(count_id)

            max_pos = max(len(player_id_list) - 4, 0)

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

            # print(f'companies: {companies} max_pos: {max_pos} curr_pos: {curr_pos}  default_pos: {default_pos}  start_pos: {start_pos}  displayed: {displayed_players}')
            val_df = val_df.groupby('player_name').apply(reverse_pv_index).reset_index(drop=True)
            val_df['dividend_pv'] = val_df['new_pv_index'] * val_df['dividend_paid']
            val_df['excess_capital'] = np.where(val_df['year'] == selected_year, val_df['excess_capital'], 0)
            val_df['in_force'] = np.where(val_df['year'] == selected_year, val_df['in_force'], 0)
            val_df['tot_in_force'] = val_df['beg_in_force']
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
            df['avg_profit'] = df.apply(lambda row: calculate_avg_profit(row, latest_year, earliest_year),  axis=1)
            df['future_value'] = df.apply(lambda row: calculate_future_value(row, latest_year, earliest_year, irr_rate_scalar), axis=1)
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
                    new_row_name = 'In-Force'
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
                        lambda x: f"${.1 * round(x/100000):.1f}")  # formatting as currency without decimals
                elif index == 'dividend_pv':
                    # Rename and format the 'written_premium' row
                    new_row_name = 'P.V. Dividends (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):.1f}")  # formatting as currency without decimals
                elif index == 'excess_capital':
                    new_row_name = f'Excess Capital (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):.1f}")  # formatting as currency without decimals
                elif index == 'total_valuation':
                    new_row_name = 'Total Valuation (MM)'
                    transposed_df.loc[index] = row.apply(
                        lambda x: f"${.1 * round(x/100000):.1f}")  # formatting as currency without decimals
                elif index == 'Valuation Rank':
                    new_row_name = 'Valuation Rank'

                transposed_df.rename(index={index: new_row_name}, inplace=True)
            row_order = {
                'In-Force': 0,
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
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

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

    selected_coverage = request.GET.get('coverage')
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
            triangle_df = triangle_df[triangle_df['year'] == selected_year]

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
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

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

    selected_coverage = request.GET.get('coverage')
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
            triangle_df = triangle_df[triangle_df['year'] == selected_year]
            financial_df = financial_df[financial_df['year'] >= (selected_year - 5)]
            claimtrend_obj = claimtrend_data.filter(year=selected_year).first()
            if claimtrend_obj:
                claimtrend_dict = claimtrend_obj.claim_trends


            claim_data = triangle_df.triangles[0]['triangles']
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

            cols = ['Actual Paid', 'Devl Factor', 'Ultimate Incurred', 'In-Force', 'Loss Cost', 'Claim Count', 'Frequency', 'Severity', 'Product Reform']
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
                elif categ == 'In-Force':
                    for m in range(len(acc_yrs)):
                        display_df.iloc[i, m] = financial_df.iloc[len(acc_yrs) - m - 1, 1]
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
                            display_df.iloc[i, o] = financial_df.iloc[len(acc_yrs) - o - 1, 3]
                        else:
                            display_df.iloc[i, o] = financial_df.iloc[len(acc_yrs) - o - 1, 2]
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
                            display_df.iloc[i, r] = 'Yes'
                        else:
                            display_df.iloc[i, r] = 'No'
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
        'title': ' - Claim Development Report',
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
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

    template_name = 'Pricing/decision_input.html'
    indication_data = Indications.objects.filter(game_id=game)
    unique_players = indication_data.order_by('player_id').values_list('player_name', flat=True).distinct()

    selected_player = None
    financial_data_table = None

    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)
    valuation_data = None
    context = {
        'title': ' - Decision Input',
        'game': game,
        'financial_data_table': financial_data_table,
        'has_financial_data': valuation_data.exists(),
        'unique_players': unique_players,
        'selected_player': selected_player,
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
            from_sender = msg.from_user.username if msg.from_user else "game_server"
            message_list.append({
                'from_sender': from_sender,
                'time': timestamp_with_timezone.strftime('%H:%M:%S'),
                'content': msg.content,
                'sequence_number': msg.sequence_number
            })

        return JsonResponse({"messages": message_list})
