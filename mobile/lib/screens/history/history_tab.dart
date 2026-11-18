import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/screens/billing/receipt_screen.dart';

class HistoryTab extends StatelessWidget {
  const HistoryTab({super.key});

  final List<Map<String, dynamic>> _bills = const [
    {
      'bill_number': 'SB-INV-202611-00042',
      'shop_name': 'Smart Bazaar Superstore',
      'date': '11 Nov 2026, 05:40 PM',
      'final_total': '565.00',
      'payment_method': 'UPI',
      'payment_status': 'COMPLETED',
      'items_count': 2,
    },
    {
      'bill_number': 'SB-INV-202611-00028',
      'shop_name': 'Smart Bazaar Express',
      'date': '08 Nov 2026, 02:15 PM',
      'final_total': '280.00',
      'payment_method': 'CASH',
      'payment_status': 'COMPLETED',
      'items_count': 1,
    },
    {
      'bill_number': 'SB-INV-202610-00194',
      'shop_name': 'City Electronics',
      'date': '29 Oct 2026, 06:10 PM',
      'final_total': '3405.00',
      'payment_method': 'UPI',
      'payment_status': 'COMPLETED',
      'items_count': 3,
    },
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Shopping History'),
      ),
      body: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: _bills.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (context, index) {
          final bill = _bills[index];
          return Card(
            elevation: 1.5,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => ReceiptScreen(
                      billData: bill,
                      items: const [
                        {'name': 'Fortune Sunlite Refined Oil 1L', 'unit_price': 149.0, 'quantity': 2.0, 'discount': 0.0},
                        {'name': 'Tata Salt Vacuum Evaporated 1kg', 'unit_price': 28.0, 'quantity': 1.0, 'discount': 0.0},
                      ],
                    ),
                  ),
                );
              },
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: const BoxDecoration(
                        color: AppColors.primaryLight,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.receipt_long, color: AppColors.primary),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            bill['shop_name'],
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            bill['bill_number'],
                            style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            bill['date'],
                            style: const TextStyle(color: AppColors.textMuted, fontSize: 11),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          '₹${bill['final_total']}',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppColors.primary),
                        ),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppColors.successLight,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            bill['payment_status'],
                            style: const TextStyle(color: AppColors.success, fontSize: 10, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

