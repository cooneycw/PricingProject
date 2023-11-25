from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class GamePrefs(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    sel_type_01 = models.IntegerField()
    sel_type_02 = models.IntegerField()
    sel_type_03 = models.IntegerField()
    human_player_cnt = models.IntegerField(default=1)
    game_observable = models.BooleanField()
    timestamp = models.DateTimeField(auto_now=True)  # This field will be updated every time the model is saved.


class IndivGames(models.Model):
    game_id = models.CharField(max_length=128, primary_key=True)
    initiator = models.ForeignKey(User, on_delete=models.CASCADE)
    initiator_name = models.CharField(max_length=128, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=19, default="active")
    human_player_cnt = models.IntegerField(default=1)
    game_observable = models.BooleanField(default=False)


class Players(models.Model):
    game = models.ForeignKey(IndivGames, db_column='game_id', related_name='players', on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, related_name='participating_games', null=True, blank=True, on_delete=models.CASCADE)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    player_id_display = models.IntegerField()
    player_type = models.CharField(max_length=16)
    profile = models.CharField(max_length=16)


class MktgSales(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    beg_in_force = models.DecimalField(max_digits=16, decimal_places=0)
    mktg_expense = models.DecimalField(max_digits=18, decimal_places=2)
    mktg_expense_ind = models.DecimalField(max_digits=18, decimal_places=2)
    quotes = models.DecimalField(max_digits=16, decimal_places=0)
    sales = models.DecimalField(max_digits=16, decimal_places=0)
    canx = models.DecimalField(max_digits=16, decimal_places=0)
    avg_prem = models.DecimalField(max_digits=18, decimal_places=2)
    end_in_force = models.DecimalField(max_digits=16, decimal_places=0)


class Financials(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    written_premium = models.DecimalField(max_digits=18, decimal_places=2)
    in_force = models.DecimalField(max_digits=16, decimal_places=0)
    inv_income = models.DecimalField(max_digits=18, decimal_places=2)
    annual_expenses = models.DecimalField(max_digits=18, decimal_places=2)
    ay_losses = models.DecimalField(max_digits=18, decimal_places=2)
    py_devl = models.DecimalField(max_digits=18, decimal_places=2)
    profit = models.DecimalField(max_digits=18, decimal_places=2)
    dividend_paid = models.DecimalField(max_digits=18, decimal_places=2)
    capital = models.DecimalField(max_digits=18, decimal_places=2)
    capital_ratio = models.DecimalField(max_digits=18, decimal_places=5)
    capital_test = models.CharField(max_length=4, null=True, blank=True)


class ChatMessage(models.Model):
    sequence_number = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    from_user = models.ForeignKey(User, null=True, blank=True, related_name='from_user', on_delete=models.SET_NULL)
    game_id = models.ForeignKey(IndivGames, db_column='game_id', related_name='chat_messages', on_delete=models.CASCADE)
    content = models.TextField()

    class Meta:
        ordering = ['-sequence_number']  # Negative sign to order by descending