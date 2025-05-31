# Generated manually to revert decision fields back to integers

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Pricing', '0050_alter_decisions_sel_exp_ratio_mktg_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg_max',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_exp_ratio_mktg_min',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin_max',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_loss_trend_margin_min',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin_max',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisions',
            name='sel_profit_margin_min',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_exp_ratio_mktg',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_loss_trend_margin',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='decisionsns',
            name='sel_profit_margin',
            field=models.IntegerField(),
        ),
    ] 