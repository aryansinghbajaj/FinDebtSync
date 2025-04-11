from django.db import models
from django.contrib.auth.models import User #django built in User model to manage authentication(login and registration)
from django.core.validators import MinValueValidator, MaxValueValidator #making sure the range is fine
from django.utils import timezone # for created_at updated_at
from django.db.models.signals import post_save #triggering the mechansim after saving the model
from django.dispatch import receiver #used to define a function that responds to signals
from decimal import Decimal #precision in decimal operation , useful for financial operations
from django.db.models import Sum,Q #aggregate function used to create complex query conditions with or(|) and And(&)
# Create your models here.
class PaymentMode(models.Model):
    """
    Represents different payment modes/methods supported by the system
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
    Extended user profile for bank customers
    """
    CREDIT_RATINGS = [
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bank_profile') #creates a one to one relationship with django buil in user  , related_name help us to access this from user model using user_profile
    
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
        return self.net_amount

    def get_total_debt_owed(self):
        """
        Get total debt this customer owes to others
        """
        return Transaction.objects.filter(
            sender=self, 
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
#here the aggregate function sums up the total debt_owed , if no transaction exists it returns 0 instead of one

#the next function fetches the transactions where the user is the receiver
    def get_total_credit_received(self):
        """
        Get total credit this customer has received from others
        """
        return Transaction.objects.filter(
            receiver=self, 
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

#counts the number of pending transactions where the customer is either hte sender or reciever
    def get_pending_settlements_count(self):
        """
        Get count of pending settlements that involve this customer
        """
        return Transaction.objects.filter(
            Q(sender=self) | Q(receiver=self),
            status='PENDING'
        ).count()

#get the recent most transactions where the customer is either the sender or the receiver
    def get_recent_transactions(self, limit=5):
        """
        Get recent transactions for this customer
        """
        return Transaction.objects.filter(
            Q(sender=self) | Q(receiver=self)
        ).order_by('-created_at')[:limit]

# Signal to create BankCustomer profile when User is created using post_save
@receiver(post_save, sender=User)
def create_bank_customer(sender, instance, created, **kwargs):
    if created:
        BankCustomer.objects.create(user=instance)
#payment compatibility establishes many to one relationship between BankCustomer and PaymentMode model
class PaymentCompatibility(models.Model):
    """
    Defines payment mode compatibility between different customers
    """
    customer = models.ForeignKey(
        BankCustomer, 
        related_name='payment_compatibilities', 
        on_delete=models.CASCADE
    ) #links the payment compatibility to BankCustomer .if the customer is deleted ,their compatibiliy data is also deleted
    compatible_mode = models.ForeignKey(
        PaymentMode, 
        related_name='compatible_customers', 
        on_delete=models.CASCADE
    ) #linking payment_compatibility with payment mode , if the payment mode is deleted , all the related paymentcompatibility records are deleted
    compatibility_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=50
    )#determining how will the customer can use a specific payment mode

    class Meta:
        unique_together = ('customer', 'compatible_mode')#preventing duplicate entries

    def __str__(self):
        return f"{self.customer} - {self.compatible_mode}"#displaying the customer name and payment mode

class Transaction(models.Model):
    """
    Represents a financial transaction between bank customers
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
    )#represents the customer(foreign key) who is sending money from transactions
    
    receiver = models.ForeignKey(
        BankCustomer,
        related_name='received_transactions',
        on_delete=models.CASCADE
    )#representing the customer who is receiving money in the transaction
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )#
    
    payment_mode = models.ForeignKey(
        PaymentMode,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transactions'
    )
    
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.sender} -> {self.receiver}: ${self.amount}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update net amounts for both sender and receiver if transaction is completed
        if self.status == 'COMPLETED':
            self.update_net_amounts()

#function updating the net amount whenever a transaction has been done     
    def update_net_amounts(self):
        # Decrease sender's net amount
        self.sender.net_amount -= self.amount
        self.sender.save()
        
        # Increase receiver's net amount
        self.receiver.net_amount += self.amount
        self.receiver.save()
class DebtSettlement(models.Model):
    """
    Represents a settlement of debts between customers
    """
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
    
    # many to many relationship with Transaction representing all the transactions that were settled in the debt settlement
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