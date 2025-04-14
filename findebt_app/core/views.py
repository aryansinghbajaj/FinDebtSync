from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate #login - logs in the user and authenticate checks the user details
from django.contrib.auth.decorators import login_required #use to restrict view access to authenticate users only
from django.contrib import messages #framework for flashing messages to the user
from .forms import UserRegistrationForm, PaymentModeSelectionForm, TransactionForm, DebtSettlementForm, PaymentModeManagementForm
from .models import PaymentMode, BankCustomer, PaymentCompatibility, DebtSettlement, Transaction
from .utils import minimize_transactions
from django.db import transaction #transaction is used for atomic operations ensures that all the changes inside the block are done together or not at all
from django.db.models import Q #allowing complex queries using AND,OR,NOT
from django.db import models #use for defining model field
from decimal import Decimal # for decimal arithmetic precision
from django.db.models import Sum #use for summing up values

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
            ) #they payment modes are saved if they are not there automatically
    
    if request.method == 'POST':
        form = PaymentModeSelectionForm(request.POST)
        if form.is_valid():
            form.save_preferences(customer)
            messages.success(request, "Payment preferences saved successfully!")
            return redirect('home')
    else:
        # Pre-select any existing preferences
        initial_data = {}
        existing_modes = PaymentCompatibility.objects.filter(customer=customer) #getting any pre existing payment modes of the logged in bank customer
        if existing_modes.exists():
            initial_data['payment_modes'] = [pm.compatible_mode.id for pm in existing_modes] #if they exist they are appending in an array
        
        form = PaymentModeSelectionForm(initial=initial_data) # a blank form created with initial data
    
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
    customer = request.user.bank_profile #getting the profile of the logged in customer
    
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
    if request.method == 'POST':
        form = DebtSettlementForm(request.POST, initiator=request.user.bank_profile)
        if form.is_valid():
            participants = list(form.cleaned_data['participants'])
            participants.append(request.user.bank_profile)  # Add initiator to participants
            
            # Get optimized transactions
            transactions, net_amounts = minimize_transactions(participants)
            
            # Use database transaction to ensure all updates are atomic
            with transaction.atomic():
                # First, clean up any existing pending settlements between these participants
                DebtSettlement.objects.filter(
                    (Q(initiator=request.user.bank_profile) & Q(participant__in=participants)) |
                    (Q(participant=request.user.bank_profile) & Q(initiator__in=participants)),
                    status='PENDING'
                ).delete()
                
                # Create settlement records for each participant
                settlements = []
                for participant in participants:
                    if participant != request.user.bank_profile:  # Don't create settlement with self
                        # Calculate net amount between initiator and participant
                        net_amount = net_amounts.get((request.user.bank_profile, participant), Decimal('0.00'))
                        if net_amount == 0:
                            net_amount = net_amounts.get((participant, request.user.bank_profile), Decimal('0.00'))
                            
                        # Only create settlement if there's a non-zero net amount
                        if net_amount != 0:
                            settlement = DebtSettlement.objects.create(
                                initiator=request.user.bank_profile,
                                participant=participant,
                                status='COMPLETED',  # Create as COMPLETED directly
                                net_amount=abs(net_amount)  # Store absolute value of net amount
                            )
                            settlements.append(settlement)
                
                # Update related transactions to 'SETTLED' status and link them to settlements
                affected_transactions = Transaction.objects.filter(
                    (Q(sender__in=participants) & Q(receiver__in=participants)) &
                    Q(status='PENDING')
                )
                
                # Update each transaction and recalculate balances
                for trans in affected_transactions:
                    # Reverse the original transaction effect
                    trans.sender.net_amount += trans.amount
                    trans.receiver.net_amount -= trans.amount
                    
                    # Update transaction status
                    trans.status = 'SETTLED'
                    
                    # Save changes
                    trans.sender.save()
                    trans.receiver.save()
                    trans.save()
                    
                    # Link transaction to relevant settlements
                    for settlement in settlements:
                        if (trans.sender == settlement.initiator and trans.receiver == settlement.participant) or \
                           (trans.sender == settlement.participant and trans.receiver == settlement.initiator):
                            settlement.transactions.add(trans)
                
                # Store optimized transactions
                context = {
                    'optimized_transactions': [],
                    'settlements': settlements
                }
                
                for path, amount, modes in transactions:
                    if len(path) == 2:
                        # Direct transfer
                        transaction_str = f"{path[0].user.username} → {path[1].user.username}: ${amount} via {modes[0]}"
                    else:
                        # Via bank
                        transaction_str = f"{path[0].user.username} → bank → {path[2].user.username}: ${amount} via {modes[0]} and {modes[1]}"
                    context['optimized_transactions'].append(transaction_str)
            
            return render(request, 'settlement_result.html', context)
    else:
        form = DebtSettlementForm(initiator=request.user.bank_profile)
    
    return render(request, 'initiate_settlement.html', {'form': form})

@login_required
def transaction_history(request):
    customer = request.user.bank_profile
    
    # getting all the transactions where the user is either a sender or a receiver
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