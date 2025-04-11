from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('payment-modes/', views.payment_modes, name='payment_modes'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create-transaction/', views.create_transaction, name='create_transaction'),
    path('initiate-settlement/', views.initiate_settlement, name='initiate_settlement'),
    path('transaction-history/', views.transaction_history, name='transaction_history'),
    path('manage-payment-modes/', views.manage_payment_modes, name='manage_payment_modes'),
]