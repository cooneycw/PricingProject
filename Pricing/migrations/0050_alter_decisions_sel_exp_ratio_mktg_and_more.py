# Generated by Django 4.1 on 2025-05-31 00:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Pricing', '0049_gameprefs_game_difficulty'),
    ]

    operations = [
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg_max',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg_min',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin_max',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin_min',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin_max',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin_min',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_exp_ratio_mktg',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_loss_trend_margin',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_profit_margin',
            field=models.DecimalField(decimal_places=1, max_digits=5),
        ),
    ]
