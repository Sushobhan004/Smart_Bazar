import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/core/services/api_service.dart';

class CustomerHomeTab extends StatefulWidget {
  final VoidCallback onNavigateToScan;
  final VoidCallback onNavigateToShops;
  final VoidCallback onNavigateToHistory;

  const CustomerHomeTab({
    super.key,
    required this.onNavigateToScan,
    required this.onNavigateToShops,
    required this.onNavigateToHistory,
  });

  @override
  State<CustomerHomeTab> createState() => _CustomerHomeTabState();
}

class _CustomerHomeTabState extends State<CustomerHomeTab> {
  final ApiService _api = ApiService();
  Map<String, dynamic>? _summary;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSummary();
  }

  Future<void> _loadSummary() async {
    final data = await _api.getCustomerSummary();
    if (mounted) {
      setState(() {
        _summary = data;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = _summary?['full_name'] ?? _api.currentUser?['username'] ?? 'Customer';
    final totalSpent = _summary?['total_spent'] ?? 4250.0;
    final rewardPoints = _summary?['reward_points'] ?? 42;
    final walletBal = _summary?['wallet_balance'] ?? 50.0;
    final code = _summary?['customer_code'] ?? 'SB-CUST-774921';

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadSummary,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 1. PhonePe-Style Purple Gradient Top Header
                Container(
                  padding: const EdgeInsets.only(left: 20, right: 20, top: 16, bottom: 24),
                  decoration: const BoxDecoration(
                    gradient: AppColors.primaryGradient,
                    borderRadius: BorderRadius.only(
                      bottomLeft: Radius.circular(28),
                      bottomRight: Radius.circular(28),
                    ),
                  ),
                  child: Column(
                    children: [
                      // Top Row: Avatar, Name, Notification Bell, QR Icon
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 22,
                            backgroundColor: Colors.white,
                            child: Text(
                              name.isNotEmpty ? name[0].toUpperCase() : 'C',
                              style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary, fontSize: 18),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Hello, $name',
                                  style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                                ),
                                Text(
                                  'ID: $code',
                                  style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 12),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.qr_code_scanner, color: Colors.white),
                            tooltip: 'Quick Scan',
                            onPressed: widget.onNavigateToScan,
                          ),
                          IconButton(
                            icon: const Icon(Icons.notifications_none, color: Colors.white),
                            onPressed: () {},
                          ),
                        ],
                      ),

                      const SizedBox(height: 18),

                      // Search Bar
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: const TextField(
                          decoration: InputDecoration(
                            hintText: 'Search shops, products or bills...',
                            hintStyle: TextStyle(fontSize: 13, color: AppColors.textSecondary),
                            prefixIcon: Icon(Icons.search, color: AppColors.primary, size: 20),
                            border: InputBorder.none,
                            enabledBorder: InputBorder.none,
                            focusedBorder: InputBorder.none,
                            contentPadding: EdgeInsets.symmetric(vertical: 12),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 16),

                // 2. Spending & Rewards Wallet Banner (PhonePe Balance Card)
                Card(
                  elevation: 2,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('Total Spending', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                                const SizedBox(height: 4),
                                Text(
                                  '₹${totalSpent.toStringAsFixed(2)}',
                                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                                ),
                              ],
                            ),
                            Container(height: 36, width: 1, color: Colors.grey.shade300),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                const Text('Rewards & Vouchers', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                                const SizedBox(height: 4),
                                Row(
                                  children: [
                                    const Icon(Icons.stars, color: AppColors.warning, size: 20),
                                    const SizedBox(width: 4),
                                    Text(
                                      '$rewardPoints Pts (₹${walletBal.toStringAsFixed(0)})',
                                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.primary),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 14),
                        // Spend ₹15k progress toward ₹50 voucher
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('₹15,000 Milestone: ₹50 Reward', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                                Text('${((totalSpent / 15000.0) * 100).clamp(0, 100).toStringAsFixed(0)}%', style: const TextStyle(fontSize: 11, color: AppColors.primary)),
                              ],
                            ),
                            const SizedBox(height: 6),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(6),
                              child: LinearProgressIndicator(
                                value: (totalSpent / 15000.0).clamp(0.0, 1.0),
                                backgroundColor: Colors.grey.shade200,
                                color: AppColors.accent,
                                minHeight: 6,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 8),

                // 3. Quick Action Grid
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildQuickAction(
                        icon: Icons.qr_code_scanner,
                        label: 'Scan & Pay',
                        color: AppColors.primary,
                        onTap: widget.onNavigateToScan,
                      ),
                      _buildQuickAction(
                        icon: Icons.store_mall_directory_outlined,
                        label: 'Smart Shops',
                        color: AppColors.secondary,
                        onTap: widget.onNavigateToShops,
                      ),
                      _buildQuickAction(
                        icon: Icons.receipt_long,
                        label: 'My Bills',
                        color: Colors.teal,
                        onTap: widget.onNavigateToHistory,
                      ),
                      _buildQuickAction(
                        icon: Icons.card_giftcard,
                        label: 'Vouchers',
                        color: Colors.orange,
                        onTap: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Active Offer: ₹50 Flat Voucher code FESTIVE50')),
                          );
                        },
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 16),

                // 4. Promotional Banner (PhonePe-like Carousel Card)
                Card(
                  elevation: 2,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      gradient: AppColors.cardGradient,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.celebration, color: Colors.white, size: 40),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Festive Rewards Unlocked!',
                                style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Spend ₹15,000 across participating stores to earn ₹50 instant cashback vouchers.',
                                style: TextStyle(color: Colors.white.withOpacity(0.9), fontSize: 11),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 16),

                // 5. Participating Shops List
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 18),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Participating Shops',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppColors.textPrimary),
                      ),
                      TextButton(
                        onPressed: widget.onNavigateToShops,
                        child: const Text('View All'),
                      ),
                    ],
                  ),
                ),

                SizedBox(
                  height: 120,
                  child: ListView(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    scrollDirection: Axis.horizontal,
                    children: [
                      _buildShopCard('Smart Bazaar Superstore', 'Grocery & FMCG', 'Salt Lake'),
                      _buildShopCard('City Electronics & Mobile', 'Electronics', 'Park Street'),
                      _buildShopCard('Care Pharmacy & Health', 'Pharmacy', 'New Town'),
                    ],
                  ),
                ),

                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildQuickAction({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        children: [
          Container(
            width: 54,
            height: 54,
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: color, size: 26),
          ),
          const SizedBox(height: 6),
          Text(
            label,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          ),
        ],
      ),
    );
  }

  Widget _buildShopCard(String name, String category, String location) {
    return Card(
      margin: const EdgeInsets.only(right: 12),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Container(
        width: 170,
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Row(
              children: [
                const Icon(Icons.storefront, size: 20, color: AppColors.primary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(category, style: const TextStyle(color: AppColors.textSecondary, fontSize: 11)),
            const SizedBox(height: 2),
            Text(location, style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
          ],
        ),
      ),
    );
  }
}
