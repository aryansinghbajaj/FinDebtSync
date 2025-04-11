from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm, PaymentModeSelectionForm, TransactionForm, DebtSettlementForm, PaymentModeManagementForm
from .models import PaymentMode, BankCustomer, PaymentCompatibility, DebtSettlement, Transaction
from .utils import minimize_transactions
from django.db import transaction
from django.db.models import Q
from django.db import models
from decimal import Decimal

def home(request):
    return render(request, 'home.html')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save() #user is saved in database
            # User is created, BankCustomer is created via signal
            login(request, user) #the user is logged in automatically
            # Redirect to payment mode selection
            return redirect('payment_modes')
        else:
            for error in form.errors.values():
                messages.error(request, error)#error if occuring is added to Django message framework and displayed to user
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})

@login_required #only logged in users can see this view
def payment_modes(request):
    customer = request.user.bank_profile #retrieves the bank customer profile for the logged in user
    
    # Initialize payment modes if none exist
    if PaymentMode.objects.count() == 0:
        default_modes = [
            ('Bank Transfer', 'BANK', 'Standard bank transfers between accounts'),
            ('PayPal', 'DIGITAL', 'PayPal digital wallet'),
            ('Venmo', 'DIGITAL', 'Venmo mobile payment service'),
            ('Credit Card', 'CARD', 'Major credit cards accepted'),
            ('Debit Card', 'CARD', 'Direct debit from banking account'),
            ('Bitcoin', 'CRYPTO', 'Bitcoin cryptocurrency'),
            ('Ethereum', 'CRYPTO', 'Ethereum cryptocurrency'),
            ('Cash', 'OTHER', 'Physical cash payment')
        ]
        
        for name, category, description in default_modes:
            PaymentMode.objects.create(
                name=name,
                category=category,
                description=description
            ) #the payment mode are saved if the do not exist already
    
    if request.method == 'POST':
        form = PaymentModeSelectionForm(request.POST)
        if form.is_valid():
            form.save_preferences(customer)
            messages.success(request, "Payment preferences saved successfully!")
            return redirect('home')
    else:
        # Pre-select any existing preferences
        initial_data = {}
        existing_modes = PaymentCompatibility.objects.filter(customer=customer)
        if existing_modes.exists():
            initial_data['payment_modes'] = [pm.compatible_mode.id for pm in existing_modes]
        
        form = PaymentModeSelectionForm(initial=initial_data) # a form is created with prefilled data
    
    return render(request, 'payment_modes.html', {'form': form})


@login_required #ensuring only authenticated(logged-in) users can access the dashboard view
def dashboard(request):
    customer = request.user.bank_profile #retrieving the customer profile
    
    # Getting the payment modes that are compatible with customer
    payment_modes = PaymentCompatibility.objects.filter(customer=customer)
    
    # Get 5 recent transactions
    recent_transactions = customer.get_recent_transactions(limit=5)
    
    # Financial overview data
    net_position = customer.get_net_position()
    total_debt = customer.get_total_debt_owed()
    total_credit = customer.get_total_credit_received()
    pending_settlements = customer.get_pending_settlements_count()
    
    context = {
        'customer': customer,
        'payment_modes': payment_modes,
        'recent_transactions': recent_transactions,
        'net_position': net_position,
        'total_debt': total_debt,
        'total_credit': total_credit,
        'pending_settlements': pending_settlements,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def create_transaction(request):
    customer = request.user.bank_profile
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, sender=customer)
        if form.is_valid():
            transaction = form.save()
            messages.success(request, f"Transaction of ${transaction.amount} created successfully!")
            return redirect('dashboard')
    else:
        form = TransactionForm(sender=customer)
    
    return render(request, 'create_transaction.html', {
        'form': form,
        'customer': customer
    })

@login_required
def initiate_settlement(request):
    customer = request.user.bank_profile
    
    if request.method == 'POST':
        form = DebtSettlementForm(request.POST, initiator=customer)
        if form.is_valid():
            participants = form.cleaned_data['participants']
            participants = list(participants) + [customer]  # Include initiator
            
            # Get optimized transactions
            optimized_transactions, organizations = minimize_transactions(participants)
            
            if optimized_transactions:
                # Create a new debt settlement
                with transaction.atomic():
                    debt_settlement = DebtSettlement.objects.create(
                        initiator=customer,
                        participant=participants[0],  # First participant
                        net_amount=sum(t[1] for t in optimized_transactions)
                    )
                    
                    # Update transaction statuses and link to settlement
                    for path, amount, modes in optimized_transactions:
                        # Get all pending transactions between these participants
                        transactions = Transaction.objects.filter(
                            Q(sender__in=participants, receiver__in=participants),
                            status='PENDING'
                        )
                        
                        # Update transactions
                        for t in transactions:
                            t.status = 'SETTLED'
                            t.settlement = debt_settlement
                            t.save()
                
                messages.success(request, "Debt settlement created successfully!")
                return redirect('dashboard')
            else:
                messages.warning(request, "No transactions could be optimized.")
    else:
        form = DebtSettlementForm(initiator=customer)
    
    return render(request, 'initiate_settlement.html', {
        'form': form,
        'customer': customer
    })

@login_required
def transaction_history(request):
    customer = request.user.bank_profile
    
    # Get all transactions where the customer is either sender or receiver
    transactions = Transaction.objects.filter(
        Q(sender=customer) | Q(receiver=customer)
    ).order_by('-created_at')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply filters
    if status_filter:
        transactions = transactions.filter(status=status_filter)
    
    if date_from:
        transactions = transactions.filter(created_at__gte=date_from)
    
    if date_to:
        transactions = transactions.filter(created_at__lte=date_to)
    
    # Get transaction statistics
    total_transactions = transactions.count()
    total_amount = transactions.aggregate(
        total=models.Sum('amount')
    )['total'] or Decimal('0')
    
    context = {
        'customer': customer,
        'transactions': transactions,
        'total_transactions': total_transactions,
        'total_amount': total_amount,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'transaction_history.html', context)

@login_required
def manage_payment_modes(request):
    customer = request.user.bank_profile
    
    if request.method == 'POST':
        form = PaymentModeManagementForm(request.POST, customer=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Payment modes updated successfully!")
            return redirect('dashboard')
    else:
        form = PaymentModeManagementForm(customer=customer)
    
    # Get current payment modes with compatibility scores
    current_modes = PaymentCompatibility.objects.filter(
        customer=customer
    ).select_related('compatible_mode')
    
    context = {
        'customer': customer,
        'form': form,
        'current_modes': current_modes,
    }
    
    return render(request, 'manage_payment_modes.html', context)