import os
import threading
from datetime import timedelta
from rest_framework import viewsets
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from helpdesk.utils.microsoft import verify_microsoft_token

from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, Q
from django.utils import timezone

# SMTP
import smtplib, ssl
from email.message import EmailMessage

from dotenv import load_dotenv
load_dotenv()

from .constants import SLA_HOURS

from .models import User, Issues, Conversations, Attachment, ALLOWED_ATTACHMENT_EXTENSIONS
from .serializers import MyTokenObtainPairSerializer, UserSerializer, IssuesSerializer, IssuesListSerializer, ConversationsSerializer, AttachmentSerializer

def is_admin_user(user):
    return user.is_superuser or (user.role or '').lower() == 'admin'

def get_admin_emails():
    return list(
        User.objects.filter(role__iexact='admin', is_superuser=False, is_active=True)
        .values_list('email', flat=True)
    )

def notify_all_admins(subject, context, email_type):
    for email in get_admin_emails():
        send_mail(subject=subject, to_email=email, context=context, type=email_type)

def send_mail_async(subject, to_email, context, type):
    thread = threading.Thread(
        target=send_mail,
        kwargs={'subject': subject, 'to_email': to_email, 'context': context, 'type': type},
        daemon=True,
    )
    thread.start()

def notify_all_admins_async(subject, context, email_type):
    thread = threading.Thread(
        target=notify_all_admins,
        kwargs={'subject': subject, 'context': context, 'email_type': email_type},
        daemon=True,
    )
    thread.start()
def send_mail(subject, to_email, context, type):
        port = 587
        smtp_server =os.getenv('SMTP_SERVER')
        username=os.getenv('EMAIL_USER')
        password =os.getenv('EMAIL_PASSWORD')
        
        try:
            if type == "admin":
                html_content = render_to_string('creation_admin.html', context)
            elif type == "user":
                html_content = render_to_string('creation_user.html', context)
            elif type == "message":
                html_content = render_to_string('message_notification.html', context)
            elif type == "status":
                html_content = render_to_string('status.html', context)
            elif type == "transfer":
                html_content = render_to_string('transfer_notification.html', context)
            elif type == "sla_unclaimed_breach":
                html_content = render_to_string('sla_unclaimed_breach.html', context)
            elif type == "sla_resolution_warning":
                html_content = render_to_string('sla_resolution_warning.html', context)
            elif type == "sla_resolution_breach":
                html_content = render_to_string('sla_resolution_breach.html', context)
            else:
                return False

            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = "itservicedesk@creditreferencenigeria.net"
            msg['To'] = [to_email]
            msg.set_content(html_content, subtype='html')

            if port == 465:
                ssl_context = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_server, port, context=ssl_context) as server:
                    server.login(username, password)
                    server.send_message(msg)
            elif port == 587:
                with smtplib.SMTP(smtp_server, port) as server:
                    server.starttls()
                    server.login(username, password)
                    server.send_message(msg)
            else:
                print("use 465 / 587 as port value")
                return False
            return True
        except Exception as e:
            print(e)
            return False

@api_view(["POST"])
@permission_classes([AllowAny])
def microsoft_login(request):
    id_token = request.data.get("id_token")

    if not id_token:
        return Response({"detail": "Missing data"}, status=400)

    try:
        payload = verify_microsoft_token(id_token)
    except Exception:
        return Response({"detail": "Invalid token"}, status=401)

    email = payload.get("preferred_username") or payload.get("email")

    if not email:
        return Response({"detail": "No email found"}, status=400)

    # Extract domain
    email_domain = email.split("@")[-1].lower()

    # 🔒 Domain restriction
    allowed_domains = {"crccreditbureau.net", "crccreditbureau.com"}
    if email_domain not in allowed_domains:
        return Response(
            {"detail": "Unauthorized email domain"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not registered for this organization"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Issue JWT
    refresh = RefreshToken.for_user(user)

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "email": email
    })

class MyTokenObtainPairView(TokenObtainPairView):
    """
    Custom TokenObtainPairView using MyTokenObtainPairSerializer.
    """
    serializer_class = MyTokenObtainPairSerializer

@api_view(['GET'])
def issue_stats(request):
    stats = Issues.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        completed=Count('id', filter=Q(status='completed')),
    )
    return Response(stats)

class IssueFilter(django_filters.FilterSet):
    month = django_filters.CharFilter(method='filter_by_month')

    class Meta:
        model = Issues
        fields = ['status', 'reported_by', 'assigned_to', 'severity']

    def filter_by_month(self, queryset, name, value):
        try:
            year, month_num = value.split('-')
            return queryset.filter(created_at__year=int(year), created_at__month=int(month_num))
        except (ValueError, AttributeError):
            return queryset

class UserFilter(django_filters.FilterSet):
    # Role values in the DB have inconsistent casing ('admin' vs 'Admin'),
    # so match case-insensitively to avoid silently dropping users.
    email = django_filters.CharFilter(lookup_expr='iexact')
    role = django_filters.CharFilter(lookup_expr='iexact')

    class Meta:
        model = User
        fields = ['email', 'role', 'is_active']

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    http_method_names = ['get', 'post', 'put', 'patch']
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserFilter

    def partial_update(self, request, *args, **kwargs):
        user = self.get_object()

        is_self = request.user.id == user.id
        is_admin = is_admin_user(request.user)
        if not (is_self or is_admin):
            return Response(
                {'detail': 'You can only update your own account.'},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()
        password = data.pop('password', None)

        if password:
            user.set_password(password)
            user.save()

        if data:
            serializer = self.get_serializer(user, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({'status': 'password set'}, status=status.HTTP_200_OK)

class IssuesViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'patch']
    filter_backends = [DjangoFilterBackend]
    filterset_class = IssueFilter

    def get_queryset(self):
        base = Issues.objects.select_related('reported_by', 'assigned_to', 'resolved_by')
        if self.action == 'list':
            return base.annotate(conversation_count=Count('conversations'))
        return base.prefetch_related(
            Prefetch('conversations', queryset=Conversations.objects.select_related('sender')),
            'attachments',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return IssuesListSerializer
        return IssuesSerializer

    def partial_update(self, request, *args, **kwargs):
        issue = self.get_object()
        data = request.data.copy()
        action = data.pop('action', None)

        # --- CLAIM: any IT admin can claim an unassigned ticket ---
        if action == 'claim':
            if issue.assigned_to is not None:
                return Response(
                    {'detail': 'This issue has already been claimed.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            now = timezone.now()
            issue.assigned_to = request.user
            issue.sla_acknowledged = now <= issue.created_at + timedelta(hours=1)
            # Resolution clock starts from the moment of claiming
            hours = SLA_HOURS.get(issue.severity, 24)
            issue.sla_resolve_by = now + timedelta(hours=hours)
            issue.save(update_fields=['assigned_to', 'sla_acknowledged', 'sla_resolve_by'])
            serializer = self.get_serializer(issue)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # --- TRANSFER: only the current assignee can transfer ---
        if action == 'transfer':
            if issue.assigned_to is None or issue.assigned_to.id != request.user.id:
                return Response(
                    {'detail': 'Only the current assignee can transfer this issue.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            new_user_id = data.get('assigned_to')
            try:
                new_user = User.objects.get(id=new_user_id, is_active=True)
            except User.DoesNotExist:
                return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
            if not is_admin_user(new_user):
                return Response(
                    {'detail': 'Issues can only be transferred to IT admins.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            issue.assigned_to = new_user
            issue.save()

            from_admin = f"{request.user.first_name or ''} {request.user.last_name or ''}".strip() or request.user.email
            to_admin = f"{new_user.first_name or ''} {new_user.last_name or ''}".strip() or new_user.email
            base_context = {
                'ticket_id': 'CRC-' + str(issue.id),
                'title': issue.title,
                'description': issue.description,
                'from_admin': from_admin,
                'to_admin': to_admin,
            }
            # Notify the new assignee
            send_mail_async(
                subject='Issue CRC-' + str(issue.id) + ' Transferred to You',
                to_email=new_user.email,
                context={
                    **base_context,
                    'recipient': 'assignee',
                    'cta_url': f'https://itservicedesk.creditreferencenigeria.net/admin/issues/{issue.id}',
                },
                type='transfer'
            )
            # Notify the staff member who reported the issue
            send_mail_async(
                subject='Issue CRC-' + str(issue.id) + ' Reassigned',
                to_email=issue.reported_by.email,
                context={
                    **base_context,
                    'recipient': 'reporter',
                    'cta_url': 'https://itservicedesk.creditreferencenigeria.net/dashboard',
                },
                type='transfer'
            )

            serializer = self.get_serializer(issue)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # --- RESOLVE: only the current assignee can resolve ---
        if action == 'resolve':
            if issue.assigned_to is None or issue.assigned_to.id != request.user.id:
                return Response(
                    {'detail': 'Only the assigned admin can resolve this issue.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            issue.status = 'completed'
            issue.resolved_on = timezone.now()
            issue.resolved_by = request.user
            issue.save()

            context = {
                'ticket_id': 'CRC-' + str(issue.id),
                'title': issue.title,
                'description': issue.description,
                'date': issue.created_at,
                'status': issue.status,
            }
            send_mail_async(
                subject='Issue CRC-' + str(issue.id) + ' Resolved',
                to_email=issue.reported_by.email,
                context=context,
                type='status'
            )
            serializer = self.get_serializer(issue)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # --- REOPEN / generic status change (existing behaviour) ---
        new_status = data.pop('status', None)

        if new_status is not None and new_status != issue.status:
            if new_status == 'pending':
                issue.status = 'pending'
                issue.resolved_on = None
                issue.resolved_by = None
                issue.escalation_tier = 0
                issue.save()

                context = {
                    'ticket_id': 'CRC-' + str(issue.id),
                    'title': issue.title,
                    'description': issue.description,
                    'date': issue.created_at,
                    'status': issue.status,
                }
                send_mail_async(
                    subject='Issue CRC-' + str(issue.id) + ' Reopened',
                    to_email=issue.reported_by.email,
                    context=context,
                    type='status'
                )
            else:
                issue.status = new_status
                issue.save()

        if data:
            serializer = self.get_serializer(issue, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(issue)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = serializer.save()

        headers = self.get_success_headers(serializer.data)

        reporter = issue.reported_by
        reporter_name = f"{reporter.first_name or ''} {reporter.last_name or ''}".strip() or reporter.email
        context = {
            'ticket_id': 'CRC-' + str(issue.id),
            'title': issue.title,
            'description': issue.description,
            'reported_by': reporter_name,
            'date': issue.created_at,
            'severity': issue.get_severity_display(),
            'sla_resolve_by': issue.sla_resolve_by,
        }

        notify_all_admins_async(subject="New Issue Reported", context=context, email_type="admin")
        send_mail_async(subject="Issue Reported Successfully", to_email=reporter.email, context=context, type="user")

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='attachments')
    def upload_attachments(self, request, pk=None):
        issue = self.get_object()
        files = request.FILES.getlist('files')

        if not files:
            return Response({'detail': 'No files provided.'}, status=status.HTTP_400_BAD_REQUEST)

        MAX_SIZE = 10 * 1024 * 1024  # 10 MB
        created = []
        for f in files:
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
                return Response(
                    {'detail': f'File type ".{ext}" is not allowed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if f.size > MAX_SIZE:
                return Response(
                    {'detail': f'"{f.name}" exceeds the 10 MB limit.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            attachment = Attachment.objects.create(
                issue=issue,
                file=f,
                original_name=f.name,
                file_size=f.size,
                uploaded_by=request.user,
            )
            created.append(attachment)

        serializer = AttachmentSerializer(created, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ConversationsViewSet(viewsets.ModelViewSet):
    queryset = Conversations.objects.all()
    serializer_class = ConversationsSerializer
    http_method_names = ['get', 'post', 'put', 'patch']
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['issue']

    def create(self, request, *args, **kwargs):
        message = request.data.get('message')
        issue = Issues.objects.get(id=request.data.get('issue'))
        sender = User.objects.get(id=request.data.get('sender'))

        sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.email

        if is_admin_user(sender):
            context = {
                'message': message,
                'ticket_id': 'CRC-' + str(issue.id),
                'sender': sender_name,
            }
            send_mail_async(
                subject="New Message on Issue (ID: CRC-" + str(issue.id) + ")",
                to_email=issue.reported_by.email,
                context=context,
                type="message"
            )
            return super().create(request, *args, **kwargs)

        else:
            reporter = issue.reported_by
            reporter_name = f"{reporter.first_name or ''} {reporter.last_name or ''}".strip() or reporter.email
            context = {
                'message': message,
                'ticket_id': 'CRC-' + str(issue.id),
                'sender': reporter_name,
            }
            subject = "New Message on Issue (ID: CRC-" + str(issue.id) + ")"

            if issue.assigned_to:
                send_mail_async(subject=subject, to_email=issue.assigned_to.email, context=context, type="message")
            else:
                notify_all_admins_async(subject=subject, context=context, email_type="message")

            return super().create(request, *args, **kwargs)