# Generated by Django 4.1 on 2024-02-19 13:51

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Pricing', '0047_lock'),
    ]

    operations = [
        migrations.AddField(
            model_name='lock',
            name='user',
            field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='lock',
            name='lock_id',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterUniqueTogether(
            name='lock',
            unique_together={('lock_id', 'user')},
        ),
    ]
