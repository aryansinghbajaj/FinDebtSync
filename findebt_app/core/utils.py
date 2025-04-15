from decimal import Decimal
from collections import deque
from django.db import models #providing base classes and tools to interact with database schema
from .models import BankCustomer, Transaction, PaymentMode, PaymentCompatibility
from django.db.models import Sum
from django.contrib.auth.models import User

class Organization:
    def __init__(self, bank_customer):
        self.bank_customer = bank_customer
        self.net_amount = Decimal('0')
        self.payment_modes = set(
            pm.compatible_mode.name 
            for pm in bank_customer.payment_compatibilities.all()
        ) #creating a class Organization containing bank_customer , net_amount and payment_modes

class TransactionPath:
    def __init__(self, path, amount, payment_modes):
        self.path = path
        self.amount = amount
        self.payment_modes = payment_modes #creating a transaction path class consisting of path  , amount and the payment modes

def find_path_bfs(debtor_index, creditor_index, organizations, num_orgs):
    queue = deque([debtor_index]) #initialising the queue with the starting point 
    visited = [False] * num_orgs #initialising the visited array as false
    parent = [-1] * num_orgs #initiailsing the parent array as flase
    mode_used = [None] * num_orgs #initialising the mode_used arrays
    
    visited[debtor_index] = True #marking the starting point as visited
    
    while queue: #while !queue.isEmpty()
        current = queue.popleft() #dequeue the current node to explore its neighbours
        
        if current == creditor_index: #if we have reached the creditor the path is found
            path = []
            modes = []
            node = creditor_index #now we'll perform backtracking using the creditor_index as the starting node using parent array to build the path
            
            while node != debtor_index:#while we have not reached the beginning of the path
                path.insert(0, node) 
                modes.insert(0, mode_used[node])#inserting the nodes and the modes in the beginning of the transaction
                node = parent[node] #backtracking the pointer node
            path.insert(0, debtor_index) #finally adding the beggining of the the path , here 0 refers to the beginning
            
            min_amount = min(
                abs(organizations[debtor_index].net_amount),
                organizations[creditor_index].net_amount
            ) #transaction amount settled in this path is min of how much debitor owes and how much is creditore owed
            
            return TransactionPath(path, min_amount, modes)#returning the path , the amount and the list of the payment modes
        
        for next_node in range(num_orgs):
            if visited[next_node] or next_node == current:
                continue #skip if it is already visited or same as current
                
            common_modes = organizations[current].payment_modes.intersection(
                organizations[next_node].payment_modes
            )#get the intersection of the payment modes of the current and the next nodes
            
            if common_modes:#if they have any common nodes
                queue.append(next_node) #add it to the queue to be explored later
                visited[next_node] = True #mark it as visited
                parent[next_node] = current #record teh current as the parent of the next node
                mode_used[next_node] = next(iter(common_modes)) #save the payment mode used for this link(pick the first one from the list)
    
    return None #return none if no paht is found

def get_common_payment_mode(customer1, customer2):
    """Find a common payment mode between two customers"""
    modes1 = set(PaymentCompatibility.objects.filter(customer=customer1).values_list('compatible_mode__name', flat=True))
    modes2 = set(PaymentCompatibility.objects.filter(customer=customer2).values_list('compatible_mode__name', flat=True))
    common = modes1.intersection(modes2)
    return next(iter(common)) if common else None

def minimize_transactions(participants):
    """Optimize transactions using bank as intermediary when needed"""
    transactions = []
    net_amounts = {}
    
    # Get or create bank customer
    bank_user, _ = User.objects.get_or_create(username='bank', defaults={'email': 'bank@system.com'})
    bank_customer, _ = BankCustomer.objects.get_or_create(user=bank_user)
    
    # Add bank to participants if not already present
    if bank_customer not in participants:
        participants.append(bank_customer)
    
    # Create Organization objects for each participant
    organizations = []
    org_map = {}  # Map BankCustomer to their index in organizations list
    
    for i, p in enumerate(participants):
        # Calculate net amount
        sent = Transaction.objects.filter(sender=p, status='PENDING').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        received = Transaction.objects.filter(receiver=p, status='PENDING').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        net_amount = received - sent
        p.net_amount = net_amount
        p.save()
        
        # Create Organization object
        org = Organization(p)
        org.net_amount = net_amount
        organizations.append(org)
        org_map[p] = i
        
        # Store net amounts between participants
        for other in participants:
            if p != other:
                sent_to_other = Transaction.objects.filter(
                    sender=p, 
                    receiver=other, 
                    status='PENDING'
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                
                received_from_other = Transaction.objects.filter(
                    sender=other, 
                    receiver=p, 
                    status='PENDING'
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                
                net = received_from_other - sent_to_other
                if net != 0:
                    net_amounts[(p, other)] = net
    
    num_orgs = len(organizations)
    
    # Find debtors and creditors
    debtors = [(i, org) for i, org in enumerate(organizations) if org.net_amount < 0]
    creditors = [(i, org) for i, org in enumerate(organizations) if org.net_amount > 0]
    
    while debtors and creditors:
        debtor_idx, debtor = debtors[0]
        creditor_idx, creditor = creditors[0]
        
        # Find path using BFS
        path_result = find_path_bfs(debtor_idx, creditor_idx, organizations, num_orgs)
        
        if path_result:
            # Get the amount to transfer
            amount = min(abs(organizations[path_result.path[0]].net_amount),
                        organizations[path_result.path[-1]].net_amount)
            
            # Create transaction record
            path_customers = [organizations[i].bank_customer for i in path_result.path]
            transactions.append((path_customers, amount, path_result.payment_modes))
            
            # Update balances
            organizations[path_result.path[0]].net_amount += amount
            organizations[path_result.path[-1]].net_amount -= amount
        else:
            print(f"No valid path found between {debtor.bank_customer.user.username} and {creditor.bank_customer.user.username}")
            # Remove this pair from consideration
            debtors.pop(0)
            continue
        
        # Update debtors and creditors lists
        debtors = [(i, org) for i, org in enumerate(organizations) if org.net_amount < 0]
        creditors = [(i, org) for i, org in enumerate(organizations) if org.net_amount > 0]
    
    return transactions, net_amounts

def create_default_payment_modes():
    """Create default payment modes if they don't exist"""
    default_modes = [
        ('PayPal', 'DIGITAL'),
        ('Bank Transfer', 'BANK'),
        ('Venmo', 'DIGITAL'),
        ('Cash App', 'DIGITAL'),
        ('Credit Card', 'CARD')
    ]
    
    for name, category in default_modes:
        PaymentMode.objects.get_or_create(
            name=name,
            defaults={'category': category, 'is_active': True}
        )