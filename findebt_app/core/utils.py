from decimal import Decimal
from collections import deque
from django.db import models
from .models import BankCustomer, Transaction, PaymentMode

class Organization:
    def __init__(self, bank_customer):
        self.bank_customer = bank_customer
        self.net_amount = Decimal('0')
        self.payment_modes = set(
            pm.compatible_mode.name 
            for pm in bank_customer.payment_compatibilities.all()
        )

class TransactionPath:
    def __init__(self, path, amount, payment_modes):
        self.path = path
        self.amount = amount
        self.payment_modes = payment_modes

def find_path_bfs(debtor_index, creditor_index, organizations, num_orgs):
    queue = deque([debtor_index])
    visited = [False] * num_orgs
    parent = [-1] * num_orgs
    mode_used = [None] * num_orgs
    
    visited[debtor_index] = True
    
    while queue:
        current = queue.popleft()
        
        if current == creditor_index:
            path = []
            modes = []
            node = creditor_index
            
            while node != debtor_index:
                path.insert(0, node)
                modes.insert(0, mode_used[node])
                node = parent[node]
            path.insert(0, debtor_index)
            
            min_amount = min(
                abs(organizations[debtor_index].net_amount),
                organizations[creditor_index].net_amount
            )
            
            return TransactionPath(path, min_amount, modes)
        
        for next_node in range(num_orgs):
            if visited[next_node] or next_node == current:
                continue
                
            common_modes = organizations[current].payment_modes.intersection(
                organizations[next_node].payment_modes
            )
            
            if common_modes:
                queue.append(next_node)
                visited[next_node] = True
                parent[next_node] = current
                mode_used[next_node] = next(iter(common_modes))
    
    return None

def get_common_payment_mode(org1, org2):
    common = org1.payment_modes.intersection(org2.payment_modes)
    return next(iter(common)) if common else None

def minimize_transactions(participants):
    organizations = [Organization(participant) for participant in participants]
    num_orgs = len(organizations)
    
    # Calculate net amounts
    for i, org in enumerate(organizations):
        amount = Decimal('0')
        
        # Calculate incoming transactions
        incoming = Transaction.objects.filter(
            receiver=org.bank_customer,
            status='PENDING'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        
        # Calculate outgoing transactions
        outgoing = Transaction.objects.filter(
            sender=org.bank_customer,
            status='PENDING'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        
        org.net_amount = incoming - outgoing

    all_transactions = []

    while True:
        debtors = [i for i in range(num_orgs) if organizations[i].net_amount < 0]
        creditors = [i for i in range(num_orgs) if organizations[i].net_amount > 0]
        
        if not debtors or not creditors:
            break
        
        path_found = False
        
        for debtor in debtors:
            if path_found:
                break
                
            for creditor in creditors:
                path = find_path_bfs(debtor, creditor, organizations, num_orgs)
                
                if path:
                    amount = path.amount
                    organizations[debtor].net_amount += amount
                    organizations[creditor].net_amount -= amount
                    
                    all_transactions.append((path.path, amount, path.payment_modes))
                    path_found = True
                    break
        
        if not path_found:
            break

    return all_transactions, organizations 