# Generated by Django 4.1 on 2023-12-31 22:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Pricing', '0035_indications_indication_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='decisions',
            name='decisions_data',
            field=models.JSONField(default=0),
            preserve_default=False,
        ),
    ]
