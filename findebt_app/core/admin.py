from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html
from decimal import Decimal
from .models import PaymentMode, BankCustomer, PaymentCompatibility, Transaction, DebtSettlement

# Register PaymentMode
@admin.register(PaymentMode)
class PaymentModeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description')

# Register BankCustomer
@admin.register(BankCustomer)
class BankCustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'full_name', 'phone_number', 'credit_rating', 
                    'net_amount', 'total_debt_limit', 'created_at')
    list_filter = ('credit_rating', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone_number')
    readonly_fields = ('created_at', 'updated_at', 'net_amount')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone_number', 'date_of_birth')
        }),
        ('Financial Information', {
            'fields': ('credit_rating', 'total_debt_limit', 'net_amount')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def username(self, obj):
        return obj.user.username

    def full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"

# Register PaymentCompatibility
@admin.register(PaymentCompatibility)
class PaymentCompatibilityAdmin(admin.ModelAdmin):
    list_display = ('customer', 'compatible_mode', 'compatibility_score')
    list_filter = ('compatible_mode', 'compatibility_score')
    search_fields = ('customer__user__username',)

# Register Transaction
class BankIntermediaryFilter(admin.SimpleListFilter):
    title = 'Bank as Intermediary'
    parameter_name = 'bank_intermediary'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            # Define your logic for transactions where the bank acts as an intermediary
            # This is a placeholder - you'll need to adjust based on your specific logic
            return queryset.filter(description__icontains='bank intermediary')
        elif self.value() == 'no':
            return queryset.exclude(description__icontains='bank intermediary')
        return queryset

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'formatted_transaction', 'amount', 'payment_mode', 
                    'status', 'created_at', 'is_bank_intermediary')
    list_filter = ('status', 'payment_mode', 'created_at', BankIntermediaryFilter)
    search_fields = ('sender__user__username', 'receiver__user__username', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    def formatted_transaction(self, obj):
        return f"{obj.sender} → {obj.receiver}"
    formatted_transaction.short_description = 'Transaction'
    
    def is_bank_intermediary(self, obj):
        # Define your logic to identify if bank is intermediary
        # This is a placeholder - you'll need to adjust based on your specific logic
        if 'bank intermediary' in (obj.description or '').lower():
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    is_bank_intermediary.short_description = 'Bank Intermediary'
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('sender', 'receiver', 'amount', 'payment_mode', 'status')
        }),
        ('Additional Information', {
            'fields': ('description', 'created_at', 'updated_at')
        }),
    )
    
    def get_queryset(self, request):
        # Add custom queryset if needed
        return super().get_queryset(request)

# Register DebtSettlement
@admin.register(DebtSettlement)
class DebtSettlementAdmin(admin.ModelAdmin):
    list_display = ('id', 'initiator', 'participant', 'net_amount', 'payment_mode', 'created_at')
    list_filter = ('payment_mode', 'created_at')
    search_fields = ('initiator__user__username', 'participant__user__username')
    filter_horizontal = ('transactions',)  # For many-to-many field
