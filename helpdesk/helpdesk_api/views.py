import os
from django.shortcuts import render
from rest_framework import viewsets
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from helpdesk.utils.microsoft import verify_microsoft_token

from django.template.loader import render_to_string

# SMTP
import smtplib, ssl
from email.message import EmailMessage

from dotenv import load_dotenv
load_dotenv()

import random
import string

from .models import User, Issues, Conversations
from .serializers import MyTokenObtainPairSerializer, UserSerializer, IssuesSerializer, ConversationsSerializer

def get_admin_emails():
    return list(
        User.objects.filter(role__iexact='admin', is_superuser=False, is_active=True)
        .values_list('email', flat=True)
    )

def notify_all_admins(subject, context, email_type):
    for email in get_admin_emails():
        send_mail(subject=subject, to_email=email, context=context, type=email_type)
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
            else:
                return False

            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = "IThelpdesk@creditreferencenigeria.net"
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
    queryset = Issues.objects.all()
    serializer_class = IssuesSerializer
    http_method_names = ['get', 'post', 'put', 'patch']
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'reported_by', 'assigned_to']

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
            issue.assigned_to = request.user
            issue.save()
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
            if (new_user.role or '').lower() != 'admin':
                return Response(
                    {'detail': 'Issues can only be transferred to IT admins.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            issue.assigned_to = new_user
            issue.save()
            serializer = self.get_serializer(issue)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # --- RESOLVE: only the current assignee can resolve ---
        if action == 'resolve':
            if issue.assigned_to is None or issue.assigned_to.id != request.user.id:
                return Response(
                    {'detail': 'Only the assigned admin can resolve this issue.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            from django.utils import timezone
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
            send_mail(
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
                issue.save()

                context = {
                    'ticket_id': 'CRC-' + str(issue.id),
                    'title': issue.title,
                    'description': issue.description,
                    'date': issue.created_at,
                    'status': issue.status,
                }
                send_mail(
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

        response = super().create(request, *args, **kwargs)
        issue = Issues.objects.get(id=response.data['id'])
        
        reporter = issue.reported_by
        reporter_name = f"{reporter.first_name or ''} {reporter.last_name or ''}".strip() or reporter.email
        context = {
            'ticket_id': 'CRC-'+str(issue.id),
            'title': issue.title,
            'description': issue.description,
            'reported_by': reporter_name,
            'date': issue.created_at,
        }

        # To all admins
        notify_all_admins(subject="New Issue Reported", context=context, email_type="admin")
        print("Admin notifications sent.")

        # To User
        if send_mail(
            subject="Issue Reported Successfully",
            to_email=reporter.email,
            context=context,
            type="user"
        ):
            print("User notification sent successfully.")
        else:
            print("Failed to send user notification.")

        return response

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

        if sender.role == 'admin':

            context = {
                'message': message,
                'ticket_id': 'CRC-'+str(issue.id),
                'sender': sender_name,
            }

            if send_mail(
                subject="New Message on Issue (ID: CRC-"+str(issue.id)+")",
                to_email=issue.reported_by.email,
                context=context,
                type="message"
            ):
                print("Message notification sent successfully to user.")
            else:
                print("Failed to send message notification to user.")

            return super().create(request, *args, **kwargs)

        else:
            reporter = issue.reported_by
            reporter_name = f"{reporter.first_name or ''} {reporter.last_name or ''}".strip() or reporter.email
            context = {
                'message': message,
                'ticket_id': 'CRC-'+str(issue.id),
                'sender': reporter_name,
            }
            subject = "New Message on Issue (ID: CRC-"+str(issue.id)+")"

            if issue.assigned_to:
                # Notify only the assigned admin
                send_mail(subject=subject, to_email=issue.assigned_to.email, context=context, type="message")
                print("Message notification sent to assigned admin.")
            else:
                # Unassigned — notify all admins
                notify_all_admins(subject=subject, context=context, email_type="message")
                print("Message notifications sent to all admins.")

            return super().create(request, *args, **kwargs)