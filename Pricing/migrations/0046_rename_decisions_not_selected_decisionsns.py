# Generated by Django 4.1 on 2024-01-13 23:32

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Pricing', '0045_decisions_not_selected'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Decisions_Not_Selected',
            new_name='Decisionsns',
        ),
    ]
