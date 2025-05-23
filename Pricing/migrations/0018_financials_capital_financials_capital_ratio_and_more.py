# Generated by Django 4.1 on 2023-11-11 16:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Pricing', '0017_financials_profit'),
    ]

    operations = [
        migrations.AddField(
            model_name='financials',
            name='capital',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='financials',
            name='capital_ratio',
            field=models.DecimalField(decimal_places=5, default=0, max_digits=18),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='financials',
            name='capital_test',
            field=models.CharField(blank=True, max_length=4, null=True),
        ),
        migrations.AddField(
            model_name='financials',
            name='dividend',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
            preserve_default=False,
        ),
    ]
