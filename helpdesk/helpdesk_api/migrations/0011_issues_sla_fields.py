from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('helpdesk_api', '0010_issues_composite_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='issues',
            name='severity',
            field=models.CharField(
                choices=[('critical', 'Critical'), ('high', 'High'), ('low', 'Low'), ('minor', 'Minor')],
                default='low',
                db_index=True,
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='issues',
            name='sla_resolve_by',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='issues',
            name='sla_acknowledged',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='issues',
            name='escalation_tier',
            field=models.IntegerField(default=0),
        ),
    ]
