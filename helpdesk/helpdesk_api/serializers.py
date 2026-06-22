from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.utils import timezone

from .models import User, Issues, Conversations

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

class SLAMixin:
    """Shared SLA status computation for list and detail serializers."""
    def get_sla_status(self, obj):
        if obj.status == 'completed':
            return 'resolved'
        if not obj.sla_resolve_by:
            return None
        now = timezone.now()
        if now >= obj.sla_resolve_by:
            return 'breached'
        elapsed = (now - obj.created_at).total_seconds()
        total = (obj.sla_resolve_by - obj.created_at).total_seconds()
        if total > 0 and elapsed / total >= 0.75:
            return 'warning'
        return 'on_track'

class IssuesListSerializer(SLAMixin, serializers.ModelSerializer):
    """Lightweight serializer for list views — no conversation payloads."""
    assigned_to_details = UserBasicSerializer(source='assigned_to', read_only=True)
    resolved_by_details = UserBasicSerializer(source='resolved_by', read_only=True)
    reported_by_details = UserBasicSerializer(source='reported_by', read_only=True)
    conversation_count = serializers.IntegerField(read_only=True)  # from queryset annotation
    sla_status = serializers.SerializerMethodField()

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

class IssuesSerializer(SLAMixin, serializers.ModelSerializer):
    conversations = serializers.SerializerMethodField()
    assigned_to_details = UserBasicSerializer(source='assigned_to', read_only=True)
    resolved_by_details = UserBasicSerializer(source='resolved_by', read_only=True)
    reported_by_details = UserBasicSerializer(source='reported_by', read_only=True)
    sla_status = serializers.SerializerMethodField()

    class Meta:
        model = Issues
        fields = [
            'id', 'title', 'description', 'status', 'severity', 'created_at',
            'reported_by', 'reported_by_details', 'resolved_on',
            'assigned_to', 'assigned_to_details',
            'resolved_by', 'resolved_by_details',
            'conversations',
            'sla_resolve_by', 'sla_acknowledged', 'sla_status',
        ]

    def get_conversations(self, obj):
        qs = obj.conversations.all().order_by('timestamp')
        return ConversationsSerializer(qs, many=True).data

class ConversationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversations
        fields = ['id', 'issue', 'message', 'sender', 'mentioned_users', 'timestamp']
