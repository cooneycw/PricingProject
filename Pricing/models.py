from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class GamePrefs(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    sel_type_01 = models.IntegerField()
    sel_type_02 = models.IntegerField()
    sel_type_03 = models.IntegerField()
    game_observable = models.BooleanField()
    timestamp = models.DateTimeField(auto_now=True)  # This field will be updated every time the model is saved.


class IndivGames(models.Model):
    game_id = models.CharField(max_length=128, unique=True)
    initiator = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, default="active")
    game_observable = models.BooleanField(default=False)


class Players(models.Model):
    game = models.ForeignKey(IndivGames, related_name='players', on_delete=models.CASCADE)
    player = models.CharField(max_length=128, null=True, blank=True)
    player_id = models.IntegerField()
    player_type = models.CharField(max_length=16)
    profile = models.CharField(max_length=16)
