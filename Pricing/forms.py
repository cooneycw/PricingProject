import numpy as np
from django import forms
from PricingProject.settings import CONFIG_MAX_TYPES, CONFIG_AVG_PLAYERS, CONFIG_STD_DEV, CONFIG_OBSERVABLE
from .models import GamePrefs


class GamePrefsForm(forms.ModelForm):
    mean_val = CONFIG_AVG_PLAYERS
    std_dev = round(mean_val * CONFIG_STD_DEV)
    default_type_01 = int(np.random.normal(mean_val, std_dev))
    default_type_02 = int(np.random.normal(mean_val, std_dev))
    default_type_03 = int(np.random.normal(mean_val, std_dev))

    CHOICES = [(i, str(i)) for i in range(CONFIG_MAX_TYPES + 1)]

    sel_type_01 = forms.ChoiceField(choices=CHOICES, initial=default_type_01)
    sel_type_02 = forms.ChoiceField(choices=CHOICES, initial=default_type_02)
    sel_type_03 = forms.ChoiceField(choices=CHOICES, initial=default_type_03)
    game_observable = forms.BooleanField(required=False, initial=CONFIG_OBSERVABLE)

    class Meta:
        model = GamePrefs
        fields = ['sel_type_01', 'sel_type_02', 'sel_type_03', 'game_observable']
