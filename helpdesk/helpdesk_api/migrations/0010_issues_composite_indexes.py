from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('helpdesk_api', '0009_issues_assigned_to_resolved_by'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='issues',
            index=models.Index(fields=['reported_by', 'status'], name='issues_reported_by_status_idx'),
        ),
        migrations.AddIndex(
            model_name='issues',
            index=models.Index(fields=['assigned_to', 'status'], name='issues_assigned_to_status_idx'),
        ),
    ]
