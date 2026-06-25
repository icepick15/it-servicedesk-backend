import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('helpdesk_api', '0011_issues_sla_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='attachments/%Y/%m/')),
                ('original_name', models.CharField(max_length=255)),
                ('file_size', models.PositiveIntegerField()),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='helpdesk_api.issues')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_attachments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['uploaded_at'],
            },
        ),
    ]
