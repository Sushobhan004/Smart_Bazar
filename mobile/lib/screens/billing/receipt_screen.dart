import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:smart_bazaar/core/constants/colors.dart';

class ReceiptScreen extends StatelessWidget {
  final Map<String, dynamic> billData;
  final List<Map<String, dynamic>> items;

  const ReceiptScreen({
    super.key,
    required this.billData,
    required this.items,
  });

  @override
  Widget build(BuildContext context) {
    final billNumber = billData['bill_number'] ?? 'SB-INV-202611-0001';
    final shopName = billData['shop_name'] ?? 'Smart Bazaar Superstore';
    final finalTotal = billData['final_total'] ?? '0.00';
    final subtotal = billData['subtotal'] ?? '0.00';
    final taxAmount = billData['tax_amount'] ?? '0.00';
    final payMode = billData['payment_method'] ?? 'CASH';
    final qrData = billData['invoice']?['qr_data'] ?? 'upi://pay?pa=smartbazaar@okaxis&pn=SmartBazaar&am=$finalTotal&cu=INR';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Invoice & Receipt'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.print),
            tooltip: 'Print Thermal Receipt',
            onPressed: () => _showThermalPreview(context, billNumber),
          ),
          IconButton(
            icon: const Icon(Icons.share),
            tooltip: 'Share Invoice',
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Invoice shared successfully.')),
              );
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            // Success Card Header
            Card(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: const BoxDecoration(
                        color: AppColors.successLight,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.check_circle, size: 48, color: AppColors.success),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Payment Completed',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.success),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Bill No: $billNumber',
                      style: const TextStyle(fontWeight: FontWeight.w600, color: AppColors.textSecondary),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '₹$finalTotal',
                      style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: AppColors.primary),
                    ),
                    Text('Paid via $payMode', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 16),

            // Store & Items Details Card
            Card(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      shopName,
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      textAlign: TextAlign.center,
                    ),
                    const Text(
                      'Plot 42, Sector V, Salt Lake City, Kolkata - 700091\nGSTIN: 19AAACB1234F1Z8',
                      style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                      textAlign: TextAlign.center,
                    ),
                    const Divider(height: 24),

                    // Items Table
                    ...items.map((it) {
                      final lineTot = (it['unit_price'] * it['quantity']) - it['discount'];
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                '${it['name']} x ${it['quantity'].toInt()}',
                                style: const TextStyle(fontSize: 13),
                              ),
                            ),
                            Text('₹${lineTot.toStringAsFixed(2)}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                          ],
                        ),
                      );
                    }),

                    const Divider(height: 24),

                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Subtotal:', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                        Text('₹$subtotal', style: const TextStyle(fontSize: 13)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('GST / Tax:', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                        Text('₹$taxAmount', style: const TextStyle(fontSize: 13)),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Final Total:', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                        Text('₹$finalTotal', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.primary)),
                      ],
                    ),

                    const SizedBox(height: 20),

                    // Dynamic UPI Verification QR
                    Center(
                      child: Column(
                        children: [
                          QrImageView(
                            data: qrData,
                            version: QrVersions.auto,
                            size: 140.0,
                          ),
                          const SizedBox(height: 6),
                          const Text(
                            'Scan with PhonePe / UPI to verify digital receipt',
                            style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 24),

            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                minimumSize: const Size.fromHeight(50),
                backgroundColor: AppColors.primary,
              ),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Back to New POS Bill'),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }

  void _showThermalPreview(BuildContext context, String billNumber) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Row(
              children: [
                Icon(Icons.receipt_long, color: AppColors.primary),
                SizedBox(width: 8),
                Text('Thermal 58mm Printer Preview', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.grey.shade300),
              ),
              child: const Text(
                "================================\n"
                "     SMART BAZAAR SUPERSTORE    \n"
                "    Plot 42, Sector V, Salt Lake\n"
                "       Phone: 9830112233        \n"
                "================================\n"
                "Bill No : SB-INV-202611-0001    \n"
                "Date    : 11-Nov-2026           \n"
                "Status  : COMPLETED             \n"
                "--------------------------------\n"
                "Thank you for shopping!         \n"
                "================================\n",
                style: TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              icon: const Icon(Icons.bluetooth_connected),
              label: const Text('Send to Bluetooth Thermal Printer'),
              onPressed: () {
                Navigator.of(ctx).pop();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Print job dispatched to ESC/POS thermal printer.')),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

