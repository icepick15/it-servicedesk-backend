from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username=None, email=None, password=None, **extra_fields):
        # accept `username` for compatibility with Django management commands
        email = email or username
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        email = email or username
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)

# Create your models here.
class User(AbstractUser):
    username = None
    objects = UserManager()
    first_name = models.CharField(max_length=30, null=True, blank=True)
    last_name = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    role = models.CharField(max_length=10, default='staff', db_index=True)
    department = models.CharField(max_length=50, null=True, blank=True)
    floor = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name="staff_user_groups",
        blank=True,
        help_text="The groups this user belongs to."
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name="staff_user_permissions",
        blank=True,
        help_text="Specific permissions for this user."
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email

class Issues(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(max_length=20, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reported_issues', db_index=True)
    resolved_on = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues', db_index=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_issues', db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reported_by', 'status'], name='issues_reported_by_status_idx'),
            models.Index(fields=['assigned_to', 'status'], name='issues_assigned_to_status_idx'),
        ]

    def __str__(self):
        return self.title

class Conversations(models.Model):
    issue = models.ForeignKey('Issues', on_delete=models.CASCADE, related_name='conversations')
    message = models.TextField()
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    mentioned_users = models.ManyToManyField(User, related_name='mentioned_in_messages', blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.message[:25]}..."