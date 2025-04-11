from django import forms
from django.contrib.auth.forms import UserCreationForm #built in form for userregistration
from django.contrib.auth.models import User #imported User Model from Django authentication system 
from .models import BankCustomer, PaymentMode, PaymentCompatibility, Transaction
from django.db.models import Q

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True) #adds an email field
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
    #function for email validation
    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email
    #function for saving the user
    def save(self, commit=True):
        user = super().save(commit=False)#calling the default save() method but not commiting to the database yet
        user.email = self.cleaned_data['email'] #assigning the email to the user
        if commit:
            user.save()
        return user #if the commit is true the user is saved

class PaymentModeSelectionForm(forms.Form):
    payment_modes = forms.ModelMultipleChoiceField(
        queryset=PaymentMode.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Select your preferred payment modes"
    )
    
    def save_preferences(self, customer):
        # Clear existing payment compatibilities
        PaymentCompatibility.objects.filter(customer=customer).delete()
        
        # Create new entries for selected payment modes
        for payment_mode in self.cleaned_data['payment_modes']:
            PaymentCompatibility.objects.create(
                customer=customer,
                compatible_mode=payment_mode,
                compatibility_score=50  # Default compatibility score
            )

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['receiver', 'amount', 'payment_mode', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.sender = kwargs.pop('sender', None)
        super().__init__(*args, **kwargs)
        
        # Filter payment modes to only show compatible ones
        if self.sender:
            compatible_modes = PaymentCompatibility.objects.filter(
                customer=self.sender
            ).values_list('compatible_mode', flat=True)
            self.fields['payment_mode'].queryset = PaymentMode.objects.filter(
                id__in=compatible_modes
            )
            
            # Filter receivers to exclude self
            self.fields['receiver'].queryset = BankCustomer.objects.exclude(
                id=self.sender.id
            )

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def save(self, commit=True):
        transaction = super().save(commit=False)
        transaction.sender = self.sender
        if commit:
            transaction.save()
        return transaction

class DebtSettlementForm(forms.Form):
    participants = forms.ModelMultipleChoiceField(
        queryset=BankCustomer.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Select participants for settlement"
    )
    
    def __init__(self, *args, **kwargs):
        self.initiator = kwargs.pop('initiator', None)
        super().__init__(*args, **kwargs)
        
        if self.initiator:
            # Get all customers with pending transactions with the initiator
            participants = BankCustomer.objects.filter(
                Q(sent_transactions__receiver=self.initiator, sent_transactions__status='PENDING') |
                Q(received_transactions__sender=self.initiator, received_transactions__status='PENDING')
            ).distinct()
            
            self.fields['participants'].queryset = participants

class PaymentModeManagementForm(forms.Form):
    payment_modes = forms.ModelMultipleChoiceField(
        queryset=PaymentMode.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Select your preferred payment modes"
    )
    
    def __init__(self, *args, **kwargs):
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        
        if self.customer:
            # Pre-select existing payment modes
            existing_modes = PaymentCompatibility.objects.filter(
                customer=self.customer
            ).values_list('compatible_mode', flat=True)
            
            self.fields['payment_modes'].initial = existing_modes
    
    def save(self):
        if self.customer:
            # Clear existing payment compatibilities
            PaymentCompatibility.objects.filter(customer=self.customer).delete()
            
            # Create new entries for selected payment modes
            for payment_mode in self.cleaned_data['payment_modes']:
                PaymentCompatibility.objects.create(
                    customer=self.customer,
                    compatible_mode=payment_mode,
                    compatibility_score=50  # Default compatibility score
                )