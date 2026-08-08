from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.module_loading import import_string

from .tokens import generate_signed_token, hash_token


class ActionType(models.Model):
    slug = models.SlugField(unique=True, max_length=100)
    display_name = models.CharField(max_length=255)
    email_template = models.CharField(max_length=255)
    response_form_class = models.CharField(max_length=255, blank=True)
    default_ttl_hours = models.PositiveSmallIntegerField(default=72)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.display_name

    def get_response_form_class(self):
        if not self.response_form_class:
            return None
        return import_string(self.response_form_class)


class PendingAction(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    action_type = models.ForeignKey(ActionType, on_delete=models.PROTECT, related_name="pending_actions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="pending_actions"
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    payload = models.JSONField(default=dict)
    payload_schema_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "expires_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type.slug}#{self.pk} ({self.status})"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    def mark_expired(self, save=True):
        if self.status == self.Status.PENDING and self.is_expired:
            self.status = self.Status.EXPIRED
            if save:
                self.save(update_fields=["status"])

    def issue_token(self):
        token = generate_signed_token(self.pk)
        self.token_hash = hash_token(token)
        self.save(update_fields=["token_hash"])
        return token
