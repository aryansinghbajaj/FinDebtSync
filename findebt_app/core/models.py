from django.db import models
from django.contrib.auth.models import User #django built in user for authentication (login and registraton)
from django.core.validators import MinValueValidator, MaxValueValidator #making sure the range is fine
from django.utils import timezone # for created_at and updated_at
from django.db.models.signals import post_save #triggering the mechanism after saving the model
from django.dispatch import receiver #use to define the function that responds to the signal
from decimal import Decimal #precision in decimal operation , for financial transaction
from django.db.models import Sum,Q #aggreagate functions used for complex queries operations including AND , OR
# Create your models here.
class PaymentMode(models.Model):
    """
    representing different modes that can by supported by the user
    """
    PAYMENT_CATEGORIES = [
        ('BANK', 'Bank Transfer'),
        ('DIGITAL', 'Digital Wallet'),
        ('CARD', 'Credit/Debit Card'),
        ('CRYPTO', 'Cryptocurrency'),
        ('OTHER', 'Other Methods')
    ]

    name = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=PAYMENT_CATEGORIES, default='OTHER')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
class BankCustomer(models.Model):
    """
    extend user profile for bank customers
    """
    CREDIT_RATINGS = [
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bank_profile') #creates a one to one relationship with django built in user , related name means we can retrieve the bank customer data using user.bank_profile
    
    # Personal Information
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Financial Information
    credit_rating = models.CharField(
        max_length=20, 
        choices=CREDIT_RATINGS, 
        default='FAIR'
    )
    total_debt_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],#ensuring that the value can never be negative
        default=0
    )
    
    # Calculated Fields
    net_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)#cannot be modified
    updated_at = models.DateTimeField(auto_now=True)#can be modified

    def __str__(self):
        return self.user.username

    def get_net_position(self):
        """
        Calculate the overall financial position of the customer
        """
        # Calculate based on all active transactions (PENDING, COMPLETED)
        sent = Transaction.objects.filter(
            sender=self,
            status__in=['PENDING', 'COMPLETED']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        received = Transaction.objects.filter(
            receiver=self,
            status__in=['PENDING', 'COMPLETED']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return received - sent

    def get_total_debt_owed(self):
        """
        Get total debt this customer owes to others
        """
        return Transaction.objects.filter(
            sender=self,
            status__in=['PENDING', 'COMPLETED']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    def get_total_credit_received(self):
        """
        Get total credit this customer has received from others
        """
        return Transaction.objects.filter(
            receiver=self,
            status__in=['PENDING', 'COMPLETED']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    def get_pending_settlements_count(self):
        """
        Get count of pending settlements that involve this customer
        """
        # First, get all settlements involving this customer
        settlements = DebtSettlement.objects.filter(
            Q(initiator=self) | Q(participant=self)
        )
        
        # Filter for pending settlements that have pending transactions
        pending_count = 0
        for settlement in settlements:
            pending_transactions = settlement.transactions.filter(status='PENDING').exists()
            if settlement.status == 'PENDING' and pending_transactions:
                pending_count += 1
        
        return pending_count

    def get_recent_transactions(self, limit=5):
        """
        Get recent transactions for this customer
        """
        return Transaction.objects.filter(
            Q(sender=self) | Q(receiver=self)
        ).order_by('-created_at')[:limit]

# signal to create Bank Customer profile as soon as the User is created
@receiver(post_save, sender=User)
def create_bank_customer(sender, instance, created, **kwargs):
    if created:
        BankCustomer.objects.create(user=instance)
#PaymentCompatibility establishes the one to many relationship between BankCustomer and Payment Mode
class PaymentCompatibility(models.Model):
    """
    Defines payment mode compatibility between different customers
    """
    customer = models.ForeignKey(
        BankCustomer, 
        related_name='payment_compatibilities', 
        on_delete=models.CASCADE
    ) #links the Payment Compatibiliy to the Bank Customer , if the customer is deleted the PaymentCompatibility is also deleted
    compatible_mode = models.ForeignKey(
        PaymentMode, 
        related_name='compatible_customers', 
        on_delete=models.CASCADE
    ) #linking the payment compatibility with payment mode so if a payment mode is also deleted
    compatibility_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=50
    )#determining how will the customer can use a specific payment mode

    class Meta:
        unique_together = ('customer', 'compatible_mode')#preventing duplicate records of customer with compatible modes

    def __str__(self):
        return f"{self.customer} - {self.compatible_mode}"#displaying the customer name and payment mode

class Transaction(models.Model):
    """
    represents a financial transaction between bank customers
    """
    TRANSACTION_STATUS = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('SETTLED', 'Settled via Settlement')
    ]
    
    sender = models.ForeignKey(
        BankCustomer,
        related_name='sent_transactions',
        on_delete=models.CASCADE
    )#representing the bank customers who are sending the money in the transactios
    
    receiver = models.ForeignKey(
        BankCustomer,
        related_name='received_transactions',
        on_delete=models.CASCADE
    )#represents the bank customer who recieves money in the transactions
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )#amount involved in transaction with minimum value being 0.01
    
    payment_mode = models.ForeignKey(
        PaymentMode,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transactions'
    )#linking to the payment mode model , if the payment mode is deleted ,it is set to NULL
    
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)#cannot be updated later
    updated_at = models.DateTimeField(auto_now=True)#can be updated later
    
    def __str__(self):
        return f"{self.sender} -> {self.receiver}: ${self.amount}"
    
    def save(self, *args, **kwargs):
        # Update net amounts when transaction is created or updated
        if self.pk is None:  # New transaction
            self.sender.net_amount -= self.amount
            self.receiver.net_amount += self.amount
            self.sender.save()
            self.receiver.save()
        super().save(*args, **kwargs)

class DebtSettlement(models.Model):
    """
    Represents a settlement of debts between customers
    """
    SETTLEMENT_STATUS = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled')
    ]

    initiator = models.ForeignKey(
        BankCustomer,
        related_name='initiated_settlements',
        on_delete=models.CASCADE
    )
    
    participant = models.ForeignKey(
        BankCustomer,
        related_name='participated_settlements',
        on_delete=models.CASCADE
    )
    
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    
    status = models.CharField(
        max_length=20,
        choices=SETTLEMENT_STATUS,
        default='PENDING'
    )
    
    # many to many represent the  many transactions that will be settled in on debt settlement
    transactions = models.ManyToManyField(Transaction, related_name='settlements')
    
    created_at = models.DateTimeField(auto_now_add=True)
    payment_mode = models.ForeignKey(
        PaymentMode,
        on_delete=models.SET_NULL,
        null=True,
        related_name='settlements'
    )
    
    def __str__(self):
        return f"Settlement between {self.initiator} and {self.participant}: ${self.net_amount}"