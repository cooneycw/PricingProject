from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings


class GamePrefs(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    sel_type_01 = models.IntegerField()
    sel_type_02 = models.IntegerField()
    sel_type_03 = models.IntegerField()
    human_player_cnt = models.IntegerField(default=1)
    game_observable = models.BooleanField()
    default_selection_type = models.CharField(max_length=8)
    game_difficulty = models.CharField(max_length=10, default='Novice')
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
    in_force_ind = models.DecimalField(max_digits=16, decimal_places=0)


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
    clm_bi = models.DecimalField(max_digits=16, decimal_places=0)
    clm_cl = models.DecimalField(max_digits=16, decimal_places=0)
    profit = models.DecimalField(max_digits=18, decimal_places=2)
    dividend_paid = models.DecimalField(max_digits=18, decimal_places=2)
    capital = models.DecimalField(max_digits=18, decimal_places=2)
    capital_ratio = models.DecimalField(max_digits=18, decimal_places=5)
    capital_test = models.CharField(max_length=4, null=True, blank=True)


class Industry(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    written_premium = models.DecimalField(max_digits=18, decimal_places=2)
    annual_expenses = models.DecimalField(max_digits=18, decimal_places=2)
    cy_losses = models.DecimalField(max_digits=18, decimal_places=2)
    profit = models.DecimalField(max_digits=18, decimal_places=2)
    capital = models.DecimalField(max_digits=18, decimal_places=2)
    capital_ratio = models.DecimalField(max_digits=18, decimal_places=5)
    capital_test = models.CharField(max_length=4, null=True, blank=True)


class Valuation(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    beg_in_force = models.DecimalField(max_digits=16, decimal_places=0)
    in_force = models.DecimalField(max_digits=16, decimal_places=0)
    start_capital = models.DecimalField(max_digits=18, decimal_places=2)
    excess_capital = models.DecimalField(max_digits=18, decimal_places=2)
    capital = models.DecimalField(max_digits=18, decimal_places=2)
    dividend_paid = models.DecimalField(max_digits=18, decimal_places=2)
    profit = models.DecimalField(max_digits=18, decimal_places=2)
    pv_index = models.DecimalField(max_digits=18, decimal_places=6)
    inv_rate = models.DecimalField(max_digits=18, decimal_places=6)
    irr_rate = models.DecimalField(max_digits=18, decimal_places=6)


class Triangles(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    triangles = models.JSONField()


class ClaimTrends(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    year = models.IntegerField()
    claim_trends = models.JSONField()


class Indications(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    indication_data = models.JSONField()


class Decisions(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    sel_aa_margin = models.IntegerField()
    sel_aa_margin_min = models.IntegerField()
    sel_aa_margin_max = models.IntegerField()
    sel_exp_ratio_mktg = models.IntegerField()
    sel_exp_ratio_mktg_min = models.IntegerField()
    sel_exp_ratio_mktg_max = models.IntegerField()
    sel_exp_ratio_data = models.IntegerField()
    sel_exp_ratio_data_min = models.IntegerField()
    sel_exp_ratio_data_max = models.IntegerField()
    sel_profit_margin = models.IntegerField()
    sel_profit_margin_min = models.IntegerField()
    sel_profit_margin_max = models.IntegerField()
    sel_loss_trend_margin = models.IntegerField()
    sel_loss_trend_margin_min = models.IntegerField()
    sel_loss_trend_margin_max = models.IntegerField()
    sel_avg_prem = models.DecimalField(max_digits=18, decimal_places=2)
    decisions_locked = models.BooleanField(default=False)
    decisions_game_stage = models.CharField(max_length=128, null=True, blank=True)
    decisions_time_stamp = models.JSONField()
    curr_avg_prem = models.DecimalField(max_digits=18, decimal_places=2)


class Decisionsns(models.Model):
    game = models.ForeignKey(IndivGames, on_delete=models.CASCADE)
    player_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    player_name = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField()
    sel_profit_margin = models.IntegerField()
    sel_loss_trend_margin = models.IntegerField()
    sel_exp_ratio_mktg = models.IntegerField()
    sel_avg_prem = models.DecimalField(max_digits=18, decimal_places=2)


class ChatMessage(models.Model):
    sequence_number = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    from_user = models.ForeignKey(User, null=True, blank=True, related_name='from_user', on_delete=models.SET_NULL)
    game_id = models.ForeignKey(IndivGames, db_column='game_id', related_name='chat_messages', on_delete=models.CASCADE)
    content = models.TextField()

    class Meta:
        ordering = ['-sequence_number']  # Negative sign to order by descending


class Lock(models.Model):
    lock_id = models.CharField(max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('lock_id', 'user')

    @staticmethod
    def acquire_lock(lock_id, user, lock_timeout=60):
        # Construct a unique lock identifier based on game_id and user
        unique_lock_id = f"{lock_id}_user_{user.pk}"

        # Check for existing lock
        current_time = timezone.now()
        expiry_time = current_time - timezone.timedelta(seconds=lock_timeout)

        existing_lock = Lock.objects.filter(lock_id=unique_lock_id, created_at__gt=expiry_time).first()
        if existing_lock is not None:
            # Lock exists and has not expired
            return False

        # Clean up expired locks
        Lock.objects.filter(lock_id=unique_lock_id, created_at__lte=expiry_time).delete()

        # Acquire new lock
        Lock.objects.create(lock_id=unique_lock_id, user=user)
        return True

    @staticmethod
    def release_lock(lock_id, user):
        unique_lock_id = f"{lock_id}_user_{user.pk}"
        Lock.objects.filter(lock_id=unique_lock_id).delete()
