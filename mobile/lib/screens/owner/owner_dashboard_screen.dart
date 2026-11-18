import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/core/services/api_service.dart';
import 'package:smart_bazaar/screens/billing/pos_billing_screen.dart';
import 'package:smart_bazaar/screens/main_navigation_screen.dart';
import 'package:smart_bazaar/screens/auth/customer_gmail_login_screen.dart';

class OwnerDashboardScreen extends StatefulWidget {
  const OwnerDashboardScreen({super.key});

  @override
  State<OwnerDashboardScreen> createState() => _OwnerDashboardScreenState();
}

class _OwnerDashboardScreenState extends State<OwnerDashboardScreen> {
  final ApiService _api = ApiService();
  Map<String, dynamic>? _reports;
  List<Map<String, dynamic>> _lowStockAlerts = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadReports();
  }

  Future<void> _loadReports() async {
    final results = await Future.wait([
      _api.getBusinessReports(),
      _api.getLowStockAlerts(),
    ]);
    if (mounted) {
      final data = results[0] as Map<String, dynamic>;
      final alerts = results[1] as List<Map<String, dynamic>>;
      setState(() {
        _reports = data;
        _lowStockAlerts = alerts;
        _isLoading = false;
      });
    }
  }

  void _showAlertsDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: AppColors.warning),
            const SizedBox(width: 8),
            Text('Low Stock Alerts (< 15) • ${_lowStockAlerts.length}', style: const TextStyle(fontSize: 16)),
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
                      subtitle: Text('Barcode: ${al['barcode'] ?? ''}\n${al['message'] ?? ''}', style: const TextStyle(fontSize: 11)),
                      trailing: Chip(
                        backgroundColor: isZero ? Colors.red.shade100 : Colors.amber.shade100,
                        label: Text(
                          '${(al['current_stock'] ?? 0).toStringAsFixed(0)} ${al['unit'] ?? 'PCS'}',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 11, color: isZero ? AppColors.error : Colors.amber.shade900),
                        ),
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

  @override
  Widget build(BuildContext context) {
    final shopName = _api.currentShop?['name'] ?? 'Smart Bazaar Superstore';
    final role = _api.userRole ?? 'SHOP_OWNER';

    final todayRev = _reports?['today_revenue'] ?? 18450.0;
    final todayCash = _reports?['today_cash'] ?? 7200.0;
    final todayUpi = _reports?['today_upi'] ?? 11250.0;
    final todayBills = _reports?['today_bills'] ?? 38;
    final totalRev = _reports?['total_revenue'] ?? 428900.0;
    final lowStock = _lowStockAlerts.isNotEmpty ? _lowStockAlerts.length : (_reports?['low_stock_count'] ?? 0);
    final bestSellers = (_reports?['best_sellers'] as List<dynamic>?) ?? [];

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(shopName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Text('$role Dashboard', style: TextStyle(fontSize: 11, color: Colors.white.withValues(alpha: 0.85))),
          ],
        ),
        actions: [
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_active),
                tooltip: 'Low Stock (< 15) Notifications',
                onPressed: _showAlertsDialog,
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
            icon: const Icon(Icons.point_of_sale),
            tooltip: 'Go to Cashier POS',
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const PosBillingScreen()),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign Out',
            onPressed: () async {
              await _api.logout();
              if (!context.mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const CustomerGmailLoginScreen()),
                (route) => false,
              );
            },
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadReports,
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 1. Revenue Overview Card
                    Card(
                      elevation: 2,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                      child: Padding(
                        padding: const EdgeInsets.all(18),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text("Today's Gross Sales", style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                            const SizedBox(height: 6),
                            Text(
                              '₹${todayRev.toStringAsFixed(2)}',
                              style: const TextStyle(fontSize: 30, fontWeight: FontWeight.bold, color: AppColors.primary),
                            ),
                            const SizedBox(height: 14),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                _buildMetricMini('Cash Sales', '₹${todayCash.toStringAsFixed(0)}', AppColors.success),
                                _buildMetricMini('UPI / PhonePe', '₹${todayUpi.toStringAsFixed(0)}', AppColors.secondary),
                                _buildMetricMini('Total Bills', '$todayBills', AppColors.textPrimary),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),

                    const SizedBox(height: 14),

                    // 2. Lifetime Store Metrics Row
                    Row(
                      children: [
                        Expanded(
                          child: Card(
                            elevation: 1.5,
                            child: Padding(
                              padding: const EdgeInsets.all(14),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('All-Time Revenue', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                                  const SizedBox(height: 4),
                                  Text(
                                    '₹${totalRev.toStringAsFixed(0)}',
                                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Card(
                            elevation: 1.5,
                            child: Padding(
                              padding: const EdgeInsets.all(14),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('Low Stock Alerts', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                                  const SizedBox(height: 4),
                                  Row(
                                    children: [
                                      const Icon(Icons.warning_amber_rounded, color: AppColors.warning, size: 20),
                                      const SizedBox(width: 4),
                                      Text(
                                        '$lowStock items',
                                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.warning),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),

                    const SizedBox(height: 16),

                    if (_lowStockAlerts.isNotEmpty) ...[
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.amber.shade50,
                          border: Border.all(color: Colors.amber.shade600, width: 1.5),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.notifications_active, color: Colors.deepOrange, size: 20),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    'Automatic Low-Stock Alert (< 15) • ${_lowStockAlerts.length} item(s)',
                                    style: TextStyle(fontWeight: FontWeight.bold, color: Colors.amber.shade900, fontSize: 13),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            ..._lowStockAlerts.map((al) {
                              final isZero = (al['current_stock'] ?? 0) <= 0;
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 6),
                                child: Row(
                                  children: [
                                    Icon(
                                      isZero ? Icons.error : Icons.warning_amber_rounded,
                                      size: 16,
                                      color: isZero ? AppColors.error : Colors.amber.shade800,
                                    ),
                                    const SizedBox(width: 6),
                                    Expanded(
                                      child: Text(
                                        al['product_name'] ?? '',
                                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
                                      ),
                                    ),
                                    Text(
                                      '${(al['current_stock'] ?? 0).toStringAsFixed(0)} ${al['unit'] ?? 'PCS'} left',
                                      style: TextStyle(
                                        fontWeight: FontWeight.bold,
                                        fontSize: 12,
                                        color: isZero ? AppColors.error : Colors.amber.shade900,
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            }),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // 3. Top Selling Products
                    const Text(
                      'Best-Selling Products',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                    ),
                    const SizedBox(height: 8),

                    Card(
                      elevation: 1.5,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Column(
                        children: bestSellers.map((item) {
                          return ListTile(
                            leading: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(color: AppColors.primaryLight, borderRadius: BorderRadius.circular(8)),
                              child: const Icon(Icons.inventory_2, color: AppColors.primary, size: 20),
                            ),
                            title: Text(item['product_name'] ?? 'Product', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                            subtitle: Text('Units Sold: ${item['total_qty']}', style: const TextStyle(fontSize: 11)),
                            trailing: Text(
                              '₹${item['total_amt']}',
                              style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary),
                            ),
                          );
                        }).toList(),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // 4. Quick Actions
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton.icon(
                            style: ElevatedButton.styleFrom(backgroundColor: AppColors.primary),
                            icon: const Icon(Icons.point_of_sale),
                            label: const Text('Open POS'),
                            onPressed: () {
                              Navigator.of(context).push(
                                MaterialPageRoute(builder: (_) => const PosBillingScreen()),
                              );
                            },
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: OutlinedButton.icon(
                            icon: const Icon(Icons.person),
                            label: const Text('Customer App'),
                            onPressed: () {
                              Navigator.of(context).push(
                                MaterialPageRoute(builder: (_) => const MainNavigationScreen()),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildMetricMini(String title, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
        const SizedBox(height: 2),
        Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}

