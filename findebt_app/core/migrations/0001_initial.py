# Generated by Django 4.2.20 on 2025-03-29 13:36

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BankCustomer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(blank=True, max_length=15, null=True)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('credit_rating', models.CharField(choices=[('EXCELLENT', 'Excellent'), ('GOOD', 'Good'), ('FAIR', 'Fair'), ('POOR', 'Poor')], default='FAIR', max_length=20)),
                ('total_debt_limit', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('net_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='bank_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PaymentMode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('category', models.CharField(choices=[('BANK', 'Bank Transfer'), ('DIGITAL', 'Digital Wallet'), ('CARD', 'Credit/Debit Card'), ('CRYPTO', 'Cryptocurrency'), ('OTHER', 'Other Methods')], default='OTHER', max_length=20)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='PaymentCompatibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('compatibility_score', models.FloatField(default=50, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('compatible_mode', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compatible_customers', to='core.paymentmode')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_compatibilities', to='core.bankcustomer')),
            ],
            options={
                'unique_together': {('customer', 'compatible_mode')},
            },
        ),
    ]
