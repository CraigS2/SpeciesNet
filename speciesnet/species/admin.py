from allauth.account.models import EmailAddress
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

# Register your models here.
from .models import (
    AquaristClub,
    AquaristClubMember,
    BapGenus,
    BapLeaderboard,
    BapSpecies,
    BapSubmission,
    CaresApprover,
    CaresRegistration,
    ImportArchive,
    PageViewCount,
    PageViewMonthlySnapshot,
    Species,
    SpeciesAdmin,
    SpeciesCollectionLocation,
    SpeciesComment,
    SpeciesFeedback,
    SpeciesInstance,
    SpeciesInstanceLabel,
    SpeciesInstanceLogEntry,
    SpeciesMaintenanceLog,
    SpeciesMaintenanceLogEntry,
    SpeciesReferenceLink,
    User,
    UserEmail,
)


class EmailAddressInline(admin.TabularInline):
    model = EmailAddress
    extra = 0
    # readonly_fields = ('email',)
    can_delete = True
    fields = ("email", "verified", "primary")

    def get_readonly_fields(self, request, obj=None):
        # Lock 'email' on existing email rows to protect verified addresses.
        # New blank rows are always editable, allowing email entry on a saved user.
        if obj and obj.pk and obj.emailaddress_set.exists():
            return ("email",)
        return ()


class UserAdmin(BaseUserAdmin):
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("Permissions", {"fields": ("is_admin", "is_species_admin")}),
        ("Privacy", {"fields": ("is_private_name", "is_private_location", "is_proxy")}),
        ("Social Media", {"fields": ("instagram_url", "facebook_url", "youtube_url")}),
    )
    # readonly_fields = ('date_joined', 'last_login')  # TODO enable when last_login is added back to the model
    readonly_fields = ("date_joined",)  # Must be readonly
    list_filter = (
        *BaseUserAdmin.list_filter,
        "is_admin",
        "is_species_admin",
        "is_private_name",
        "is_private_location",
        "is_proxy",
    )
    list_display = (*BaseUserAdmin.list_display, "is_admin", "is_species_admin", "is_proxy", "get_verified_status")
    inlines = [EmailAddressInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("emailaddress_set")

    # def get_verified_status(self, obj):
    #     email_address = next(
    #         (ea for ea in obj.emailaddress_set.all() if ea.primary), None
    #     )
    #     if email_address:
    #         return '✓ Verified' if email_address.verified else '✗ Unverified'
    #     return '- No Email'

    def get_verified_status(self, obj):
        all_user_emails = obj.emailaddress_set.all()
        primary_email = None
        for email_address in all_user_emails:
            if email_address.primary:
                primary_email = email_address
                break
        if primary_email is None:
            return "- No Email"
        if primary_email.verified:
            return "✓ Verified"
        return "✗ Unverified"

    get_verified_status.short_description = "Email Status"


class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ("email", "user", "verified", "primary")
    list_filter = ("verified", "primary")
    search_fields = ("email", "user__username", "user__email")
    readonly_fields = ("user",)
    actions = ["mark_as_verified", "mark_as_unverified"]

    def mark_as_verified(self, request, queryset):
        count = queryset.update(verified=True)
        self.message_user(request, f"{count} email(s) marked as verified.")

    mark_as_verified.short_description = "Mark selected emails as verified"

    def mark_as_unverified(self, request, queryset):
        count = queryset.update(verified=False)
        self.message_user(request, f"{count} email(s) marked as unverified.")

    mark_as_unverified.short_description = "Mark selected emails as unverified"


class SpeciesFeedbackAdmin(admin.ModelAdmin):
    list_display = ("name", "species", "user", "email", "approved", "created")
    list_filter = ("approved", "created")
    search_fields = ("name", "comment", "email")
    readonly_fields = ("name", "created", "reviewed_by", "reviewed_at")


admin.site.register(User, UserAdmin)
admin.site.register(UserEmail)
admin.site.register(AquaristClub)
admin.site.register(AquaristClubMember)
admin.site.register(Species)
admin.site.register(SpeciesComment)
admin.site.register(SpeciesAdmin)
admin.site.register(SpeciesReferenceLink)
admin.site.register(SpeciesInstance)
admin.site.register(SpeciesInstanceLabel)
admin.site.register(SpeciesInstanceLogEntry)
admin.site.register(SpeciesMaintenanceLog)
admin.site.register(SpeciesMaintenanceLogEntry)
admin.site.register(ImportArchive)
admin.site.register(BapSubmission)
admin.site.register(BapGenus)
admin.site.register(BapSpecies)
admin.site.register(BapLeaderboard)
admin.site.register(CaresRegistration)
admin.site.register(CaresApprover)
admin.site.register(SpeciesFeedback, SpeciesFeedbackAdmin)


@admin.register(SpeciesCollectionLocation)
class SpeciesCollectionLocationAdmin(admin.ModelAdmin):
    list_display = ("species", "name", "created")
    list_filter = ("species__category", "species__global_region")
    search_fields = ("name", "species__name")
    ordering = ("species__name", "name")


class PageViewCountAdmin(admin.ModelAdmin):
    list_display = ("page_type", "object_id", "visitor_type", "count")
    list_filter = ("page_type", "visitor_type")
    ordering = ("page_type", "object_id")
    readonly_fields = ("page_type", "object_id", "visitor_type", "count")


class PageViewMonthlySummaryAdmin(admin.ModelAdmin):
    list_display = ("page_type", "object_id", "visitor_type", "year", "month", "count")
    list_filter = ("page_type", "visitor_type", "year", "month")
    ordering = ("-year", "-month", "page_type")
    readonly_fields = ("page_type", "object_id", "visitor_type", "year", "month", "count")


admin.site.register(PageViewCount, PageViewCountAdmin)
admin.site.register(PageViewMonthlySnapshot, PageViewMonthlySummaryAdmin)
