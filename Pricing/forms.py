import numpy as np
from django import forms
from django.utils.html import format_html
from PricingProject.settings import CONFIG_MAX_TYPES, CONFIG_AVG_PLAYERS, CONFIG_STD_DEV, CONFIG_OBSERVABLE
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div
from .models import GamePrefs


class GamePrefsForm(forms.ModelForm):

    CHOICES = [(i, str(i)) for i in range(CONFIG_MAX_TYPES + 1)]
    HUMAN_CHOICES = [(i, str(i)) for i in range(2, CONFIG_MAX_TYPES + 1)]
    DIFFICULTY_CHOICES = [('Novice', 'Novice'), ('Expert', 'Expert')]

    def __init__(self, *args, **kwargs):
        super(GamePrefsForm, self).__init__(*args, **kwargs)

        mean_val = CONFIG_AVG_PLAYERS
        std_dev = round(mean_val * CONFIG_STD_DEV)

        self.fields['human_player_cnt'].initial = int(2)
        self.fields['sel_type_01'].initial = 2 # int(np.random.normal(mean_val, std_dev))
        self.fields['sel_type_02'].initial = 3 # int(np.random.normal(mean_val, std_dev))
        self.fields['sel_type_03'].initial = 4 # int(np.random.normal(mean_val, std_dev))
        self.fields['game_difficulty'].initial = 'Novice'

    human_player_cnt = forms.ChoiceField(choices=HUMAN_CHOICES, label="Human Players:", required=False)
    sel_type_01 = forms.ChoiceField(choices=CHOICES, label="CPU w Growth profile:")
    sel_type_02 = forms.ChoiceField(choices=CHOICES, label="CPU w Profitability profile:")
    sel_type_03 = forms.ChoiceField(choices=CHOICES, label="CPU w Balanced profile:")
    # Hidden field - game_observable checkbox removed from UI but field kept for backend compatibility
    game_observable = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput())

    default_selection_type = forms.ChoiceField(
        choices=[('Growth', 'Growth'), ('Profit', 'Profit'), ('Balanced', 'Balanced')],
        label=format_html(
            "<b>Default Player Profile</b> (to be used if decisions are not input before timer expiry) {}",
            format_html("<b>:</b>")),
        initial='Balanced'  # Set 'Y' as the default
    )

    game_difficulty = forms.ChoiceField(
        choices=DIFFICULTY_CHOICES,
        label="Game Difficulty:",
        initial='Novice'
    )

    class Meta:
        model = GamePrefs
        fields = ['human_player_cnt', 'sel_type_01', 'sel_type_02', 'sel_type_03', 'game_observable',
                  'default_selection_type', 'game_difficulty']
