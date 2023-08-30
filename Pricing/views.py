from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from PricingProject.settings import CONFIG_FRESH_PREFS
from .forms import GamePrefsForm
from .models import GamePrefs


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

    # Check for existing preferences
    try:
        game_prefs = GamePrefs.objects.get(user=user)
        delta = timezone.now() - game_prefs.timestamp
        minutes_old = delta.total_seconds() / 60

        # Delete the data if older than 60 minutes
        if minutes_old > CONFIG_FRESH_PREFS:
            game_prefs.delete()
        else:
            initial_data = {
                'sel_type_01': game_prefs.sel_type_01,
                'sel_type_02': game_prefs.sel_type_02,
                'sel_type_03': game_prefs.sel_type_03,
                'game_observable': game_prefs.game_observable,
            }
    except GamePrefs.DoesNotExist:
        pass

    if request.method == 'POST':
        form = GamePrefsForm(request.POST, initial=initial_data)
        if form.is_valid():
            GamePrefs.objects.update_or_create(
                user=user,
                defaults={
                    'sel_type_01': form.cleaned_data['sel_type_01'],
                    'sel_type_02': form.cleaned_data['sel_type_02'],
                    'sel_type_03': form.cleaned_data['sel_type_03'],
                    'game_observable': form.cleaned_data['game_observable'],
                }
            )
            return redirect('success')  # Redirect to a new page
    else:
        form = GamePrefsForm(initial=initial_data)

    context['form'] = form
    return render(request, template_name, context)

