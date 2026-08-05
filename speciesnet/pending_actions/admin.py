from django.contrib import admin

from .models import ActionType, PendingAction


@admin.register(ActionType)
class ActionTypeAdmin(admin.ModelAdmin):
    list_display = ('slug', 'display_name', 'email_template', 'default_ttl_hours', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('slug', 'display_name', 'email_template')


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'action_type', 'status', 'user', 'expires_at', 'created_at', 'responded_at')
    list_filter = ('status', 'action_type')
    search_fields = ('token_hash', 'action_type__slug', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'responded_at', 'token_hash')
