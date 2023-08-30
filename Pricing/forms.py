import numpy as np
from django import forms
from PricingProject.settings import CONFIG_MAX_TYPES, CONFIG_AVG_PLAYERS, CONFIG_STD_DEV, CONFIG_OBSERVABLE
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div
from .models import GamePrefs


class GamePrefsForm(forms.ModelForm):

    CHOICES = [(i, str(i)) for i in range(CONFIG_MAX_TYPES + 1)]

    def __init__(self, *args, **kwargs):
        super(GamePrefsForm, self).__init__(*args, **kwargs)

        mean_val = CONFIG_AVG_PLAYERS
        std_dev = round(mean_val * CONFIG_STD_DEV)

        self.fields['sel_type_01'].initial = int(np.random.normal(mean_val, std_dev))
        self.fields['sel_type_02'].initial = int(np.random.normal(mean_val, std_dev))
        self.fields['sel_type_03'].initial = int(np.random.normal(mean_val, std_dev))

    sel_type_01 = forms.ChoiceField(choices=CHOICES, label="Growth profile: ")
    sel_type_02 = forms.ChoiceField(choices=CHOICES, label="Profitability profile:")
    sel_type_03 = forms.ChoiceField(choices=CHOICES, label="Balanced profile:")
    game_observable = forms.BooleanField(required=False, initial=CONFIG_OBSERVABLE,
                                         label="Check box to make game observable by others:")

    class Meta:
        model = GamePrefs
        fields = ['sel_type_01', 'sel_type_02', 'sel_type_03', 'game_observable']
