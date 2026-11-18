import 'dart:math';
import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/core/services/api_service.dart';
import 'package:smart_bazaar/screens/scanner/scanner_screen.dart';
import 'package:smart_bazaar/screens/billing/receipt_screen.dart';
import 'package:smart_bazaar/screens/auth/customer_gmail_login_screen.dart';

class PosBillingScreen extends StatefulWidget {
  const PosBillingScreen({super.key});

  @override
  State<PosBillingScreen> createState() => _PosBillingScreenState();
}

class _PosBillingScreenState extends State<PosBillingScreen> {
  final ApiService _api = ApiService();

  // Customer State
  String? _customerId;
  String _customerDisplayName = 'Guest Walk-in';
  String _customerPhone = '';
  bool _isGuest = true;

  // Cart State: List of Maps
  final List<Map<String, dynamic>> _cartItems = [];
  List<Map<String, dynamic>> _lowStockAlerts = [];
  String _selectedPaymentMethod = 'CASH';
  bool _isCheckingOut = false;
  final _phoneSearchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadLowStockAlerts();
    // Prompt cashier for customer mobile identification first
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _showCustomerLookupDialog();
    });
  }

  Future<void> _loadLowStockAlerts() async {
    final alerts = await _api.getLowStockAlerts();
    if (mounted) {
      setState(() => _lowStockAlerts = alerts);
    }
  }

  void _showWorkerLowStockDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: AppColors.warning),
            const SizedBox(width: 8),
            Text('Low Stock (< 15) • ${_lowStockAlerts.length}', style: const TextStyle(fontSize: 16)),
          ],
        ),
        content: _lowStockAlerts.isEmpty
            ? const Text('All products currently have 15 or more units in stock.')
            : SizedBox(
                width: double.maxFinite,
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: _lowStockAlerts.length,
                  separatorBuilder: (context, index) => const Divider(height: 12),
                  itemBuilder: (context, idx) {
                    final al = _lowStockAlerts[idx];
                    final isZero = (al['current_stock'] ?? 0) <= 0;
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        isZero ? Icons.error : Icons.warning_amber_rounded,
                        color: isZero ? AppColors.error : AppColors.warning,
                      ),
                      title: Text(al['product_name'] ?? '', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                      subtitle: Text('Barcode: ${al['barcode'] ?? ''}', style: const TextStyle(fontSize: 11)),
                      trailing: Text(
                        '${(al['current_stock'] ?? 0).toStringAsFixed(0)} ${al['unit'] ?? 'PCS'} left',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: isZero ? AppColors.error : Colors.amber.shade900),
                      ),
                    );
                  },
                ),
              ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Close')),
        ],
      ),
    );
  }

  void _addProductToCart(Map<String, dynamic> product, {double qty = 1.0}) {
    final barcode = product['primary_barcode'] ?? product['sku'] ?? product['id'];
    final existingIdx = _cartItems.indexWhere((it) => it['barcode'] == barcode);

    setState(() {
      if (existingIdx >= 0) {
        _cartItems[existingIdx]['quantity'] += qty;
      } else {
        _cartItems.add({
          'product_id': product['id'] ?? 'prod-${Random().nextInt(9999)}',
          'name': product['name'] ?? 'Product Item',
          'barcode': barcode,
          'unit_price': double.tryParse(product['selling_price'].toString()) ?? 100.0,
          'mrp': double.tryParse(product['mrp'].toString()) ?? 110.0,
          'tax_rate': double.tryParse(product['tax_rate'].toString()) ?? 5.0,
          'quantity': qty,
          'discount': 0.0,
        });
      }
    });
  }

  double get _subtotal {
    return _cartItems.fold(0.0, (sum, it) => sum + (it['unit_price'] * it['quantity']));
  }

  double get _totalTax {
    return _cartItems.fold(0.0, (sum, it) {
      final linePrice = (it['unit_price'] * it['quantity']) - it['discount'];
      return sum + (linePrice * (it['tax_rate'] / 100.0));
    });
  }

  double get _totalDiscount {
    return _cartItems.fold(0.0, (sum, it) => sum + it['discount']);
  }

  double get _finalTotal {
    return (_subtotal - _totalDiscount + _totalTax).roundToDouble();
  }

  Future<void> _handleScanProduct() async {
    final scannedCode = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (_) => const ScannerScreen(
          initialMode: ScannerMode.productBarcode,
          returnBarcodeOnScan: true,
        ),
      ),
    );

    if (scannedCode != null && scannedCode.isNotEmpty) {
      final res = await _api.lookupBarcode(scannedCode);
      if (res['found'] == true) {
        _addProductToCart(res['product'], qty: 1);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Added "${res['product']['name']}" to cart'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 1),
          ),
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(res['message'] ?? 'Product not found'), backgroundColor: AppColors.error),
        );
      }
    }
  }

  void _showCustomerLookupDialog() {
    String? dialogError;
    bool searching = false;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.person_search, color: AppColors.primary),
                SizedBox(width: 8),
                Text('Customer Search'),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('Enter customer mobile number to attach to bill:'),
                const SizedBox(height: 12),
                TextField(
                  controller: _phoneSearchController,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(
                    labelText: 'Mobile Number',
                    hintText: 'e.g. 9831098310',
                    prefixIcon: Icon(Icons.phone_android),
                  ),
                ),
                if (dialogError case final err?) ...[
                  const SizedBox(height: 8),
                  Text(err, style: const TextStyle(color: AppColors.error, fontSize: 12)),
                ],
              ],
            ),
            actions: [
              TextButton(
                onPressed: () {
                  setState(() {
                    _isGuest = true;
                    _customerDisplayName = 'Guest Walk-in';
                    _customerId = null;
                  });
                  Navigator.of(ctx).pop();
                },
                child: const Text('Guest Mode'),
              ),
              TextButton(
                onPressed: () {
                  Navigator.of(ctx).pop();
                  _showNewCustomerRegistrationDialog();
                },
                child: const Text('New Registration'),
              ),
              ElevatedButton(
                onPressed: searching
                    ? null
                    : () async {
                        final phone = _phoneSearchController.text.trim();
                        if (phone.length < 10) {
                          setDialogState(() => dialogError = 'Enter a valid 10-digit mobile number.');
                          return;
                        }
                        setDialogState(() {
                          dialogError = null;
                          searching = true;
                        });
                        final res = await _api.searchCustomer(phone);
                        if (!ctx.mounted) return;
                        setDialogState(() => searching = false);

                        if (res['exists'] == true) {
                          final cust = res['customer'];
                          setState(() {
                            _customerId = cust['id'];
                            _customerDisplayName = cust['full_name'];
                            _customerPhone = cust['masked_phone'];
                            _isGuest = false;
                          });
                          Navigator.of(ctx).pop();
                        } else {
                          // Automatically open worker-assisted registration
                          Navigator.of(ctx).pop();
                          _showNewCustomerRegistrationDialog(prefillPhone: phone);
                        }
                      },
                child: const Text('Search'),
              ),
            ],
          );
        },
      ),
    );
  }

  void _showNewCustomerRegistrationDialog({String? prefillPhone}) {
    final nameController = TextEditingController();
    final phoneController = TextEditingController(text: prefillPhone ?? _phoneSearchController.text);
    final emailController = TextEditingController();
    final otpController = TextEditingController();
    bool otpSent = false;
    bool loading = false;
    String? regError;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setRegState) {
          return AlertDialog(
            title: const Text('Worker-Assisted Registration'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Consent-based customer registration. No password required.', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  const SizedBox(height: 12),
                  TextField(
                    controller: nameController,
                    decoration: const InputDecoration(labelText: 'Customer Full Name'),
                    enabled: !otpSent,
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: phoneController,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(labelText: 'Mobile Number'),
                    enabled: !otpSent,
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Customer Gmail'),
                    enabled: !otpSent,
                  ),
                  if (otpSent) ...[
                    const SizedBox(height: 12),
                    TextField(
                      controller: otpController,
                      keyboardType: TextInputType.number,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18, letterSpacing: 4),
                      decoration: const InputDecoration(labelText: 'Enter Customer Gmail OTP'),
                    ),
                  ],
                  if (regError != null) ...[
                    const SizedBox(height: 8),
                    Text(regError!, style: const TextStyle(color: AppColors.error, fontSize: 12)),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
              ElevatedButton(
                onPressed: loading
                    ? null
                    : () async {
                        if (!otpSent) {
                          setRegState(() => loading = true);
                          final res = await _api.workerRegisterCustomer(
                            name: nameController.text.trim(),
                            phone: phoneController.text.trim(),
                            email: emailController.text.trim(),
                          );
                          setRegState(() => loading = false);
                          if (res['error'] != null) {
                            setRegState(() => regError = res['error']);
                          } else {
                            setRegState(() {
                              otpSent = true;
                              if (res['dev_otp'] != null) otpController.text = res['dev_otp'];
                            });
                          }
                        } else {
                          // Verify OTP
                          setRegState(() => loading = true);
                          final res = await _api.verifyOtp(
                            email: emailController.text.trim(),
                            otp: otpController.text.trim(),
                            fullName: nameController.text.trim(),
                            phone: phoneController.text.trim(),
                          );
                          setRegState(() => loading = false);
                          if (res['error'] != null) {
                            setRegState(() => regError = res['error']);
                          } else {
                            final cust = res['customer_profile'] ?? {};
                            setState(() {
                              _customerId = cust['id'];
                              _customerDisplayName = cust['full_name'] ?? nameController.text;
                              _customerPhone = cust['phone_number'] ?? phoneController.text;
                              _isGuest = false;
                            });
                            Navigator.of(ctx).pop();
                          }
                        }
                      },
                child: Text(otpSent ? 'Verify & Link' : 'Send Gmail OTP'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _handleCompleteBill() async {
    if (_cartItems.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cannot complete bill with empty cart!')),
      );
      return;
    }

    setState(() => _isCheckingOut = true);

    final payload = {
      'shop_id': _api.currentShop?['id'] ?? '00000000-0000-0000-0000-000000000001',
      'customer_id': _customerId,
      'is_guest': _isGuest,
      'items': _cartItems.map((it) => {
        'product_id': it['product_id'],
        'quantity': it['quantity'],
        'discount': it['discount'],
      }).toList(),
      'payment_method': _selectedPaymentMethod,
      'idempotency_key': 'IDEM-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(99999)}',
      'final_total': _finalTotal.toStringAsFixed(2),
      'subtotal': _subtotal.toStringAsFixed(2),
      'tax_amount': _totalTax.toStringAsFixed(2),
    };

    final res = await _api.checkoutBill(payload);
    setState(() => _isCheckingOut = false);

    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ReceiptScreen(
          billData: res,
          items: List.from(_cartItems),
        ),
      ),
    );

    // Refresh low-stock (< 15) alerts automatically after checkout
    final serverAlerts = (res['low_stock_alerts'] as List<dynamic>?)
        ?.map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    if (serverAlerts != null) {
      setState(() => _lowStockAlerts = serverAlerts);
      if (serverAlerts.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('⚠️ Low Stock Alert (< 15): ${serverAlerts.length} product(s) need restocking!'),
            backgroundColor: Colors.orange.shade800,
          ),
        );
      }
    } else {
      _loadLowStockAlerts();
    }

    // Reset cart for next customer
    setState(() {
      _cartItems.clear();
      _isGuest = true;
      _customerDisplayName = 'Guest Walk-in';
      _customerId = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final shopName = _api.currentShop?['name'] ?? 'Smart Bazaar Superstore';
    final cashier = _api.currentUser?['username'] ?? 'cashier_arun';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(shopName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Text('Cashier: $cashier', style: TextStyle(fontSize: 12, color: Colors.white.withValues(alpha: 0.8))),
          ],
        ),
        actions: [
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_active),
                tooltip: 'Low Stock (< 15) Alerts',
                onPressed: _showWorkerLowStockDialog,
              ),
              if (_lowStockAlerts.isNotEmpty)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
                    child: Text(
                      '${_lowStockAlerts.length}',
                      style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: () async {
              await _api.logout();
              if (!mounted) return;
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const CustomerGmailLoginScreen()),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // 1. Customer Identification Card
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            color: Colors.white,
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: _isGuest ? Colors.grey.shade200 : AppColors.primaryLight,
                  child: Icon(
                    _isGuest ? Icons.person_outline : Icons.verified_user,
                    color: _isGuest ? Colors.grey : AppColors.primary,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _customerDisplayName,
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                      ),
                      Text(
                        _isGuest ? 'Guest Checkout (Tap to link)' : 'Phone: $_customerPhone',
                        style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  ),
                  icon: const Icon(Icons.search, size: 16),
                  label: Text(_isGuest ? 'Find' : 'Change', style: const TextStyle(fontSize: 12)),
                  onPressed: _showCustomerLookupDialog,
                ),
              ],
            ),
          ),

          if (_lowStockAlerts.isNotEmpty)
            InkWell(
              onTap: _showWorkerLowStockDialog,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                color: Colors.amber.shade100,
                child: Row(
                  children: [
                    Icon(Icons.warning_amber_rounded, color: Colors.amber.shade900, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '⚠️ ${_lowStockAlerts.length} product(s) below 15 stock (${_lowStockAlerts.first['product_name']}: ${(_lowStockAlerts.first['current_stock'] ?? 0).toStringAsFixed(0)} left)',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.amber.shade900),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text('View All', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.amber.shade900)),
                  ],
                ),
              ),
            ),

          const Divider(height: 1),

          // 2. Action Toolbar: Big Scan Product Button + Manual Add
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    icon: const Icon(Icons.qr_code_scanner, size: 22),
                    label: const Text('Scan Product Barcode'),
                    onPressed: _handleScanProduct,
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  icon: const Icon(Icons.playlist_add),
                  tooltip: 'Add Fast Demo Items',
                  onPressed: () {
                    _addProductToCart({
                      'id': 'prod-8901030383700',
                      'name': 'Aashirvaad Chakki Atta 5kg',
                      'selling_price': 255.0,
                      'mrp': 275.0,
                      'tax_rate': 0.0,
                      'primary_barcode': '8901030383700',
                    });
                  },
                ),
              ],
            ),
          ),

          // 3. Cart Items List
          Expanded(
            child: _cartItems.isEmpty
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.shopping_cart_outlined, size: 64, color: Colors.grey.shade300),
                        const SizedBox(height: 12),
                        const Text('Cart is empty', style: TextStyle(color: AppColors.textSecondary, fontSize: 16)),
                        const SizedBox(height: 4),
                        const Text('Scan a retail barcode to add items', style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
                      ],
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: _cartItems.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (context, index) {
                      final item = _cartItems[index];
                      final lineTotal = (item['unit_price'] * item['quantity']) - item['discount'];

                      return Card(
                        margin: EdgeInsets.zero,
                        elevation: 1,
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      item['name'],
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '₹${item['unit_price']} each | GST ${item['tax_rate']}%',
                                      style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      'Total: ₹${lineTotal.toStringAsFixed(2)}',
                                      style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary),
                                    ),
                                  ],
                                ),
                              ),
                              // Quantity Controls
                              Row(
                                children: [
                                  IconButton(
                                    icon: const Icon(Icons.remove_circle_outline, color: AppColors.error),
                                    onPressed: () {
                                      setState(() {
                                        if (item['quantity'] > 1) {
                                          item['quantity'] -= 1;
                                        } else {
                                          _cartItems.removeAt(index);
                                        }
                                      });
                                    },
                                  ),
                                  Text(
                                    '${item['quantity'].toInt()}',
                                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                                  ),
                                  IconButton(
                                    icon: const Icon(Icons.add_circle_outline, color: AppColors.success),
                                    onPressed: () {
                                      setState(() {
                                        item['quantity'] += 1;
                                      });
                                    },
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),

          // 4. Billing Bottom Bar & Checkout
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.08),
                  blurRadius: 10,
                  offset: const Offset(0, -4),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Subtotal: ₹${_subtotal.toStringAsFixed(2)}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    Text('GST/Tax: ₹${_totalTax.toStringAsFixed(2)}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    Text('Discount: ₹${_totalDiscount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    // Payment Selector
                    DropdownButton<String>(
                      value: _selectedPaymentMethod,
                      underline: const SizedBox(),
                      items: const [
                        DropdownMenuItem(value: 'CASH', child: Text('Cash')),
                        DropdownMenuItem(value: 'UPI', child: Text('UPI / PhonePe')),
                        DropdownMenuItem(value: 'CARD', child: Text('Card')),
                      ],
                      onChanged: (val) => setState(() => _selectedPaymentMethod = val!),
                    ),
                    Row(
                      children: [
                        const Text('Net: ', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                        Text(
                          '₹${_finalTotal.toStringAsFixed(2)}',
                          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.primary),
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      backgroundColor: AppColors.success,
                    ),
                    onPressed: _isCheckingOut ? null : _handleCompleteBill,
                    child: _isCheckingOut
                        ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                        : const Text('Complete & Generate Invoice', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
