from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate

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

class IssuesSerializer(serializers.ModelSerializer):
    conversations = serializers.SerializerMethodField()
    assigned_to_details = UserBasicSerializer(source='assigned_to', read_only=True)
    resolved_by_details = UserBasicSerializer(source='resolved_by', read_only=True)

    class Meta:
        model = Issues
        fields = [
            'id', 'title', 'description', 'status', 'created_at',
            'reported_by', 'resolved_on',
            'assigned_to', 'assigned_to_details',
            'resolved_by', 'resolved_by_details',
            'conversations',
        ]

    def get_conversations(self, obj):
        qs = obj.conversations.all().order_by('timestamp')
        return ConversationsSerializer(qs, many=True).data

class ConversationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversations
        fields = ['id', 'issue', 'message', 'sender', 'mentioned_users', 'timestamp']
