from rest_framework import serializers
from apps.business.models import Expense, CashRegister, CashShift, DailySalesSummary

class ExpenseSerializer(serializers.ModelSerializer):
    recorder_name = serializers.ReadOnlyField(source='recorded_by.username')

    class Meta:
        model = Expense
        fields = ['id', 'shop', 'title', 'category', 'amount', 'expense_date', 'recorded_by', 'recorder_name', 'notes']

class CashShiftSerializer(serializers.ModelSerializer):
    worker_name = serializers.ReadOnlyField(source='worker.username')

    class Meta:
        model = CashShift
        fields = [
            'id', 'shop', 'worker', 'worker_name', 'register', 'start_time', 'end_time',
            'opening_cash', 'cash_sales', 'upi_sales', 'cash_refunds',
            'expected_closing_cash', 'actual_closing_cash', 'difference', 'status', 'notes'
        ]
        read_only_fields = ['id', 'start_time', 'expected_closing_cash', 'difference']

class CloseShiftSerializer(serializers.Serializer):
    actual_closing_cash = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)

