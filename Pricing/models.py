from django.db import models
from django.contrib.auth.models import User


class GamePrefs(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    sel_type_01 = models.IntegerField()
    sel_type_02 = models.IntegerField()
    sel_type_03 = models.IntegerField()
    game_observable = models.BooleanField()
    timestamp = models.DateTimeField(auto_now=True)  # This field will be updated every time the model is saved.

