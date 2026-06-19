from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, IssuesViewSet, ConversationsViewSet, microsoft_login, issue_stats
)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'issues', IssuesViewSet)
router.register(r'messages', ConversationsViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', issue_stats, name='issue_stats'),
    path("auth/microsoft/", microsoft_login, name="microsoft_login"),
]