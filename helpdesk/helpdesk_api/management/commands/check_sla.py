from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from helpdesk_api.models import Issues, User
from helpdesk_api.views import send_mail

IT_HEAD_EMAIL = 'doyin.abiodun@crccreditbureau.net'


class Command(BaseCommand):
    help = 'Check SLA deadlines and send escalation emails for pending tickets.'

    def handle(self, *args, **options):
        now = timezone.now()

        pending_issues = (
            Issues.objects.filter(status='pending', sla_resolve_by__isnull=False)
            .select_related('reported_by', 'assigned_to')
        )

        checked = 0
        for issue in pending_issues:
            self._check_issue(issue, now)
            checked += 1

        self.stdout.write(self.style.SUCCESS(f'SLA check complete — {checked} issue(s) evaluated.'))

    def _check_issue(self, issue, now):
        sla_resolve_by = issue.sla_resolve_by
        created_at = issue.created_at
        total_seconds = (sla_resolve_by - created_at).total_seconds()
        elapsed_seconds = (now - created_at).total_seconds()
        pct_elapsed = elapsed_seconds / total_seconds if total_seconds > 0 else 0

        ticket_id = f'CRC-{issue.id}'
        reporter_name = (
            f"{issue.reported_by.first_name or ''} {issue.reported_by.last_name or ''}".strip()
            or issue.reported_by.email
        )

        # Tier 1 — Unclaimed after 1 hour → notify 3 regular admins (not IT Head)
        one_hour_mark = created_at + timedelta(hours=1)
        if now >= one_hour_mark and issue.assigned_to is None and issue.escalation_tier < 1:
            regular_admins = list(
                User.objects.filter(role__iexact='admin', is_superuser=False, is_active=True)
                .exclude(email__iexact=IT_HEAD_EMAIL)
                .values_list('email', flat=True)
            )
            context = {
                'ticket_id': ticket_id,
                'title': issue.title,
                'description': issue.description,
                'reported_by': reporter_name,
                'severity': issue.get_severity_display(),
                'created_at': created_at,
                'sla_resolve_by': sla_resolve_by,
                'cta_url': f'https://itservicedesk.creditreferencenigeria.net/admin/issues/{issue.id}',
            }
            for email in regular_admins:
                send_mail(
                    subject=f'[SLA Alert] Ticket {ticket_id} Unclaimed After 1 Hour',
                    to_email=email,
                    context=context,
                    type='sla_unclaimed_breach',
                )
            issue.escalation_tier = 1
            issue.save(update_fields=['escalation_tier'])
            self.stdout.write(f'  Tier 1 fired for {ticket_id} → {len(regular_admins)} admin(s) notified.')

        # Tier 2 — 75 % of SLA elapsed, before breach → notify assigned admin only
        if (
            issue.assigned_to is not None
            and pct_elapsed >= 0.75
            and now < sla_resolve_by
            and issue.escalation_tier < 2
        ):
            context = {
                'ticket_id': ticket_id,
                'title': issue.title,
                'description': issue.description,
                'reported_by': reporter_name,
                'severity': issue.get_severity_display(),
                'sla_resolve_by': sla_resolve_by,
                'pct_elapsed': round(pct_elapsed * 100),
                'cta_url': f'https://itservicedesk.creditreferencenigeria.net/admin/issues/{issue.id}',
            }
            send_mail(
                subject=f'[SLA Warning] Ticket {ticket_id} — 75 % of SLA Elapsed',
                to_email=issue.assigned_to.email,
                context=context,
                type='sla_resolution_warning',
            )
            issue.escalation_tier = 2
            issue.save(update_fields=['escalation_tier'])
            self.stdout.write(f'  Tier 2 fired for {ticket_id} → {issue.assigned_to.email}.')

        # Tier 3 — Resolution deadline breached → notify assigned admin + IT Head
        if now >= sla_resolve_by and issue.escalation_tier < 3:
            hours_overdue = round((now - sla_resolve_by).total_seconds() / 3600, 1)
            context = {
                'ticket_id': ticket_id,
                'title': issue.title,
                'description': issue.description,
                'reported_by': reporter_name,
                'severity': issue.get_severity_display(),
                'sla_resolve_by': sla_resolve_by,
                'hours_overdue': hours_overdue,
                'cta_url': f'https://itservicedesk.creditreferencenigeria.net/admin/issues/{issue.id}',
            }
            # Always notify IT Head
            send_mail(
                subject=f'[SLA BREACH] Ticket {ticket_id} — Resolution Deadline Exceeded',
                to_email=IT_HEAD_EMAIL,
                context=context,
                type='sla_resolution_breach',
            )
            # Also notify the assignee if they are different from IT Head
            if issue.assigned_to and issue.assigned_to.email.lower() != IT_HEAD_EMAIL.lower():
                send_mail(
                    subject=f'[SLA BREACH] Ticket {ticket_id} — Resolution Deadline Exceeded',
                    to_email=issue.assigned_to.email,
                    context=context,
                    type='sla_resolution_breach',
                )
            issue.escalation_tier = 3
            issue.save(update_fields=['escalation_tier'])
            self.stdout.write(self.style.ERROR(f'  Tier 3 fired for {ticket_id} — BREACH.'))
