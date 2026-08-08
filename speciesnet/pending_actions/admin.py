import logging
import os
from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone
from django_celery_results.admin import TaskResultAdmin as BaseTaskResultAdmin
from django_celery_results.models import TaskResult

from .models import ActionType, PendingAction
from .tasks import send_action_email

logger = logging.getLogger(__name__)


@admin.register(ActionType)
class ActionTypeAdmin(admin.ModelAdmin):
    list_display = ('slug', 'display_name', 'email_template', 'default_ttl_hours', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('slug', 'display_name', 'email_template')


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'action_type', 'status', 'user', 'created_at', 'expires_at', 'responded_at')
    list_filter = ('status', 'action_type')
    search_fields = ('token_hash', 'action_type__slug', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'responded_at', 'token_hash')
    actions = ['run_send_action_email_now', 'force_expire', 'reset_to_pending']

    @admin.action(description='Run send_action_email now (synchronous, no worker needed)')
    def run_send_action_email_now(self, request, queryset):
        success = 0
        failure = 0
        for action in queryset:
            try:
                # Use .apply() (synchronous, in-process) so this works even with
                # zero Celery workers running — useful for debugging and manual testing.
                result = send_action_email.apply(args=[action.id])
                # Use propagate=False so exceptions from the task are captured as
                # a failure result rather than propagating out of this try block.
                task_return = result.get(propagate=False)
                if result.successful() and task_return:
                    success += 1
                else:
                    failure += 1
                    self.message_user(
                        request,
                        f'Action #{action.id} ({action.action_type}): task returned {task_return!r} (check logs).',
                        level=messages.WARNING,
                    )
            except Exception as exc:
                failure += 1
                logger.exception('Admin run_send_action_email_now failed for action_id=%s', action.id)
                self.message_user(
                    request,
                    f'Action #{action.id} ({action.action_type}): error — {exc}',
                    level=messages.ERROR,
                )
        if success:
            self.message_user(request, f'Successfully sent email for {success} action(s).', level=messages.SUCCESS)
        if failure:
            self.message_user(request, f'{failure} action(s) failed — see above for details.', level=messages.ERROR)

    @admin.action(description='Force expire selected pending actions')
    def force_expire(self, request, queryset):
        updated = queryset.update(status=PendingAction.Status.EXPIRED)
        self.message_user(request, f'{updated} action(s) forced to EXPIRED status.', level=messages.SUCCESS)

    @admin.action(description='Reset selected actions to PENDING (clears responded_at/response_data)')
    def reset_to_pending(self, request, queryset):
        updated = queryset.update(
            status=PendingAction.Status.PENDING,
            responded_at=None,
            response_data=None,
        )
        self.message_user(request, f'{updated} action(s) reset to PENDING status.', level=messages.SUCCESS)


# TaskResult is the bounded Celery task-activity log (default retention: 30 days, swept by # sweep_old_task_results).
# django_celery_results auto-registers TaskResult with its own TaskResultAdmin when its app config's admin module is imported.
# Since this module extends that default admin, unregister it first to avoide Django raising AlreadyRegistered at startup

if admin.site.is_registered(TaskResult):
    admin.site.unregister(TaskResult)

@admin.register(TaskResult)
class BoundedTaskResultAdmin(BaseTaskResultAdmin):
    # Extend the default TaskResult admin with a manual "clear old results" action.
    actions = [*list(BaseTaskResultAdmin.actions or []), 'clear_old_task_results_now']

    @admin.action(description='Clear task results older than retention window (30 days) now')
    def clear_old_task_results_now(self, request, queryset):
        cutoff = timezone.now() - timedelta(
            days=int(os.environ.get('TASK_RESULT_RETENTION_DAYS', '30'))
        )
        deleted, _ = queryset.filter(date_done__lt=cutoff).delete()
        self.message_user(
            request,
            f'Deleted {deleted} TaskResult row(s) older than the retention window.',
            level=messages.SUCCESS,
        )
