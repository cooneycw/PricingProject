# Generated by Django 4.1 on 2023-10-22 14:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Pricing', '0008_alter_financials_in_force_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='financials',
            name='player_id',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]
