from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('helpdesk_api', '0008_conversations_mentioned_users_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='issues',
            name='assigned_to',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_issues',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='issues',
            name='resolved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='resolved_issues',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
