import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/screens/scanner/scanner_screen.dart';

class ShopDirectoryTab extends StatefulWidget {
  const ShopDirectoryTab({super.key});

  @override
  State<ShopDirectoryTab> createState() => _ShopDirectoryTabState();
}

class _ShopDirectoryTabState extends State<ShopDirectoryTab> {
  final List<Map<String, String>> _shops = [
    {
      'name': 'Smart Bazaar Superstore',
      'code': 'SB-SHOP-001',
      'category': 'Grocery & FMCG',
      'location': 'Plot 42, Sector V, Salt Lake City, Kolkata',
      'phone': '+91 9830112233',
      'upi': 'smartbazaar@okaxis',
      'status': 'Approved',
    },
    {
      'name': 'City Electronics & Gadgets',
      'code': 'SB-SHOP-002',
      'category': 'Consumer Electronics',
      'location': '15B Park Street, Kolkata - 700016',
      'phone': '+91 9830223344',
      'upi': 'cityelectronics@icici',
      'status': 'Approved',
    },
    {
      'name': 'Care Pharmacy & Wellness',
      'code': 'SB-SHOP-003',
      'category': 'Pharmacy & Healthcare',
      'location': 'Action Area 1, New Town, Kolkata - 700156',
      'phone': '+91 9830334455',
      'upi': 'carepharmacy@okhdfcbank',
      'status': 'Approved',
    },
    {
      'name': 'Elegance Fashion & Apparel',
      'code': 'SB-SHOP-004',
      'category': 'Apparel & Clothing',
      'location': 'South City Mall, Ground Floor, Kolkata',
      'phone': '+91 9830445566',
      'upi': 'elegancefashion@okaxis',
      'status': 'Approved',
    },
  ];

  String _searchQuery = '';
  String _selectedCategory = 'All';

  @override
  Widget build(BuildContext context) {
    final filtered = _shops.where((s) {
      final matchesSearch = s['name']!.toLowerCase().contains(_searchQuery.toLowerCase()) ||
          s['location']!.toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesCat = _selectedCategory == 'All' || s['category']!.contains(_selectedCategory);
      return matchesSearch && matchesCat;
    }).toList();

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Partner Shops'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: Padding(
            padding: const EdgeInsets.only(left: 16, right: 16, bottom: 12),
            child: Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextField(
                onChanged: (val) => setState(() => _searchQuery = val),
                decoration: const InputDecoration(
                  hintText: 'Search partner stores...',
                  prefixIcon: Icon(Icons.search, color: AppColors.primary),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                ),
              ),
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // Filter Chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(
              children: ['All', 'Grocery', 'Electronics', 'Pharmacy', 'Apparel'].map((cat) {
                final isSelected = _selectedCategory == cat;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    label: Text(cat),
                    selected: isSelected,
                    selectedColor: AppColors.primaryLight,
                    labelStyle: TextStyle(
                      color: isSelected ? AppColors.primary : AppColors.textPrimary,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                    onSelected: (_) => setState(() => _selectedCategory = cat),
                  ),
                );
              }).toList(),
            ),
          ),

          // Shops List
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: filtered.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final s = filtered[index];
                return Card(
                  margin: EdgeInsets.zero,
                  elevation: 1.5,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: AppColors.primaryLight,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(Icons.storefront, color: AppColors.primary, size: 28),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    s['name']!,
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    s['category']!,
                                    style: const TextStyle(color: AppColors.primary, fontSize: 12, fontWeight: FontWeight.w600),
                                  ),
                                ],
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: AppColors.successLight,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Text('Verified', style: TextStyle(color: AppColors.success, fontSize: 11, fontWeight: FontWeight.bold)),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            const Icon(Icons.location_on_outlined, size: 16, color: Colors.grey),
                            const SizedBox(width: 4),
                            Expanded(
                              child: Text(
                                s['location']!,
                                style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            const Icon(Icons.qr_code, size: 16, color: Colors.grey),
                            const SizedBox(width: 4),
                            Text(
                              'UPI: ${s['upi']}',
                              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                            ),
                          ],
                        ),
                        const Divider(height: 20),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            OutlinedButton.icon(
                              icon: const Icon(Icons.qr_code_scanner, size: 16),
                              label: const Text('Scan & Pay Here'),
                              onPressed: () {
                                Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => const ScannerScreen(initialMode: ScannerMode.upiQr),
                                  ),
                                );
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
        ],
      ),
    );
  }
}

