from datetime import timedelta

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.utils import timezone

from .models import User, Issues, Conversations, Attachment
from .constants import SLA_HOURS

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        credentials = {
            "email": attrs.get("email"),
            "password": attrs.get("password"),
        }
        user = authenticate(**credentials)
        if user and user.is_active:
            data = super().validate(attrs)
            return data
        raise serializers.ValidationError("Invalid email or password")

class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'department', 'floor', 'created_at', 'password', 'is_superuser']
        extra_kwargs = {
            'password': {'write_only': True},
            'is_superuser': {'read_only': True},
        }

    def validate_role(self, value):
        if value.lower() not in VALID_ROLES:
            raise serializers.ValidationError(f'Invalid role. Choose from: {", ".join(sorted(VALID_ROLES))}.')
        return value.lower()

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)

        instance.is_active = True
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'department']

class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'original_name', 'file_size', 'url', 'uploaded_at']

    def get_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

class SLAMixin:
    """Shared SLA status computation for list and detail serializers.

    Two-phase model:
      Phase 1 — unclaimed: 1-hour claim window starting at created_at.
      Phase 2 — claimed:   resolution window starting at claim time
                           (sla_resolve_by = claim_time + severity_hours).
    """
    def get_sla_status(self, obj):
        if obj.status == 'completed':
            return 'resolved'

        now = timezone.now()

        # Phase 1 — ticket not yet claimed
        if obj.assigned_to_id is None:
            one_hour_mark = obj.created_at + timedelta(hours=1)
            return 'unclaimed_breach' if now >= one_hour_mark else 'unclaimed'

        # Phase 2 — ticket claimed, resolution clock is running
        if not obj.sla_resolve_by:
            return None

        if now >= obj.sla_resolve_by:
            return 'breached'

        # Derive claim time to compute % elapsed
        total_hours = SLA_HOURS.get(obj.severity, 24)
        claim_time = obj.sla_resolve_by - timedelta(hours=total_hours)
        elapsed = (now - claim_time).total_seconds()
        total = total_hours * 3600
        if total > 0 and elapsed / total >= 0.75:
            return 'warning'
        return 'on_track'

VALID_SEVERITIES = {'critical', 'high', 'low', 'minor'}
VALID_STATUSES   = {'pending', 'completed'}
VALID_ROLES      = {'staff', 'admin'}

class IssuesListSerializer(SLAMixin, serializers.ModelSerializer):
    """Lightweight serializer for list views — no conversation payloads."""
    assigned_to_details = UserBasicSerializer(source='assigned_to', read_only=True)
    resolved_by_details = UserBasicSerializer(source='resolved_by', read_only=True)
    reported_by_details = UserBasicSerializer(source='reported_by', read_only=True)
    conversation_count = serializers.IntegerField(read_only=True)  # from queryset annotation
    sla_status = serializers.SerializerMethodField()
    description = serializers.CharField(max_length=5000)

    class Meta:
        model = Issues
        fields = [
            'id', 'title', 'description', 'status', 'severity', 'created_at',
            'reported_by', 'reported_by_details', 'resolved_on',
            'assigned_to', 'assigned_to_details',
            'resolved_by', 'resolved_by_details',
            'conversation_count',
            'sla_resolve_by', 'sla_acknowledged', 'sla_status',
        ]

    def validate_severity(self, value):
        if value not in VALID_SEVERITIES:
            raise serializers.ValidationError(f'Invalid severity. Choose from: {", ".join(sorted(VALID_SEVERITIES))}.')
        return value

    def validate_status(self, value):
        if value not in VALID_STATUSES:
            raise serializers.ValidationError(f'Invalid status. Choose from: {", ".join(sorted(VALID_STATUSES))}.')
        return value

class IssuesSerializer(SLAMixin, serializers.ModelSerializer):
    conversations = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    assigned_to_details = UserBasicSerializer(source='assigned_to', read_only=True)
    resolved_by_details = UserBasicSerializer(source='resolved_by', read_only=True)
    reported_by_details = UserBasicSerializer(source='reported_by', read_only=True)
    sla_status = serializers.SerializerMethodField()
    description = serializers.CharField(max_length=5000)

    class Meta:
        model = Issues
        fields = [
            'id', 'title', 'description', 'status', 'severity', 'created_at',
            'reported_by', 'reported_by_details', 'resolved_on',
            'assigned_to', 'assigned_to_details',
            'resolved_by', 'resolved_by_details',
            'conversations', 'attachments',
            'sla_resolve_by', 'sla_acknowledged', 'sla_status',
        ]

    def validate_severity(self, value):
        if value not in VALID_SEVERITIES:
            raise serializers.ValidationError(f'Invalid severity. Choose from: {", ".join(sorted(VALID_SEVERITIES))}.')
        return value

    def validate_status(self, value):
        if value not in VALID_STATUSES:
            raise serializers.ValidationError(f'Invalid status. Choose from: {", ".join(sorted(VALID_STATUSES))}.')
        return value

    def get_conversations(self, obj):
        qs = obj.conversations.all().order_by('timestamp')
        return ConversationsSerializer(qs, many=True).data

    def get_attachments(self, obj):
        qs = obj.attachments.all()
        return AttachmentSerializer(qs, many=True, context=self.context).data

class ConversationsSerializer(serializers.ModelSerializer):
    message = serializers.CharField(max_length=2000)

    class Meta:
        model = Conversations
        fields = ['id', 'issue', 'message', 'sender', 'mentioned_users', 'timestamp']

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError('Message cannot be blank.')
        return value
