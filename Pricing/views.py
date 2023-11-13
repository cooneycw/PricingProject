import uuid
import pytz
import pandas as pd
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
from .models import GamePrefs, IndivGames, Players, MktgSales, Financials, ChatMessage


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


@login_required()
def mktgsales_report(request, game_id):
    user = request.user
    game = get_object_or_404(IndivGames,
                             Q(game_id=game_id, initiator=user) | Q(game_id=game_id, game_observable=True))

    financial_data = MktgSales.objects.filter(game_id=game, player_id=user)
    unique_years = financial_data.order_by('-year').values_list('year', flat=True).distinct()[:4]
    latest_year = unique_years[0] if unique_years else None
    template_name = 'Pricing/mktgsales_report.html'

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.GET.get('year')  # Get the selected year from the query parameters

    if unique_years:  # Proceed if there are any financial years available
        # Querying the database
        financial_data_list = list(
            financial_data.values('year', 'beg_in_force', 'mktg_expense', 'mktg_expense_ind', 'end_in_force'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(financial_data_list)

        if not df.empty:
            # Filter out only the rows belonging to the latest four years
            latest_years = df['year'].unique()  # Get all unique years
            latest_years = sorted(latest_years, reverse=True)[:4]  # Sort and pick the latest four years
            df_latest = df[df['year'].isin(latest_years)]  # Filter the DataFrame based on the latest four years

            # Transposing the DataFrame to get years as columns and metrics as rows
            transposed_df = df_latest.set_index('year').T  # Set 'year' as index before transposing
            percentage_data = {}

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
                elif index == 'end_in_force':
                    # Rename and format the 'in_force' row
                    new_row_name = 'Ending-In-force'
                    transposed_df.loc[index] = row.apply(lambda x: f"{int(x):,}")  # formatting as an integer

                # Apply renaming to make the index/rows human-readable
                transposed_df.rename(index={index: new_row_name}, inplace=True)

                # Continue with additional conditions for more rows as needed

            for year in transposed_df.columns:
                # Convert the marketing expenses from string to float for calculation
                marketing_expense = float(transposed_df.at['Marketing Expense', year].replace('$', '').replace(',', ''))
                industry_marketing_expense = float(
                    transposed_df.at['Industry Marketing Expense', year].replace('$', '').replace(',', ''))

                # Calculate the percentage (ensuring not to divide by zero)
                if industry_marketing_expense > 0:
                    percentage = (marketing_expense / industry_marketing_expense) * 100
                else:
                    percentage = 0  # or None, or however you wish to represent this edge case

                # Store the calculated percentage in our dictionary
                percentage_data[year] = f"{percentage:.2f}%"  # formatted to two decimal places
            percentage_df = pd.DataFrame(percentage_data, index=['Marketing Spend as % of Industry'])
            insert_position = transposed_df.index.get_loc('Industry Marketing Expense') + 1
            # Split the original DataFrame
            df_top = transposed_df.iloc[:insert_position]
            df_bottom = transposed_df.iloc[insert_position:]

            # Concatenate everything: the top part, the new row, and the bottom part
            transposed_df_new = pd.concat([df_top, percentage_df, df_bottom])

            # Convert the final, formatted DataFrame to HTML for rendering
            if len(transposed_df_new.columns) < 4:
                # If there are fewer than four years of data, we'll simulate the rest as empty columns
                missing_years = 4 - len(transposed_df_new.columns)
                for i in range(missing_years):
                    transposed_df_new[f'{latest_year - i - 1} '] = ['' for _ in range(len(transposed_df_new.index))]

            financial_data_table = transposed_df_new.to_html(classes='my-financial-table', border=0, justify='initial',
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
    unique_years = financial_data.order_by('-year').values_list('year', flat=True).distinct()[:4]
    latest_year = unique_years[0] if unique_years else None
    template_name = 'Pricing/financials_report.html'

    # Check for 'Back to Game Select' POST request
    if request.POST.get('Back to Dashboard') == 'Back to Dashboard':
        return redirect('Pricing-game_dashboard', game_id=game_id)

    selected_year = request.GET.get('year')  # Get the selected year from the query parameters

    if unique_years:  # Proceed if there are any financial years available
        # Querying the database
        financial_data_list = list(
            financial_data.values('year', 'written_premium', 'in_force', 'inv_income', 'annual_expenses',
                                  'ay_losses', 'py_devl', 'profit', 'dividend_paid',
                                  'capital', 'capital_ratio', 'capital_test'))  # add more fields as necessary

        # Creating a DataFrame from the obtained data
        df = pd.DataFrame(financial_data_list)

        if not df.empty:
            # Filter out only the rows belonging to the latest four years
            latest_years = df['year'].unique()  # Get all unique years
            latest_years = sorted(latest_years, reverse=True)[:4]  # Sort and pick the latest four years
            df_latest = df[df['year'].isin(latest_years)]  # Filter the DataFrame based on the latest four years

            # Transposing the DataFrame to get years as columns and metrics as rows
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
                    transposed_df[f'{latest_year - i - 1} '] = ['' for _ in range(len(transposed_df.index))]

            index = 2
            blank_row = pd.DataFrame([['' for _ in transposed_df.columns]], columns=transposed_df.columns)
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
