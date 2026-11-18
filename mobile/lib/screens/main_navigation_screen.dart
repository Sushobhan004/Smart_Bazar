import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/screens/home/customer_home_tab.dart';
import 'package:smart_bazaar/screens/shops/shop_directory_tab.dart';
import 'package:smart_bazaar/screens/scanner/scanner_screen.dart';
import 'package:smart_bazaar/screens/history/history_tab.dart';
import 'package:smart_bazaar/screens/profile/profile_tab.dart';

class MainNavigationScreen extends StatefulWidget {
  const MainNavigationScreen({super.key});

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _currentIndex = 0;

  void _onScanPressed() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => const ScannerScreen(initialMode: ScannerMode.upiQr),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tabs = [
      CustomerHomeTab(
        onNavigateToScan: _onScanPressed,
        onNavigateToShops: () => setState(() => _currentIndex = 1),
        onNavigateToHistory: () => setState(() => _currentIndex = 3),
      ),
      const ShopDirectoryTab(),
      const SizedBox(), // Placeholder for Scan center tab
      const HistoryTab(),
      const ProfileTab(),
    ];

    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: tabs,
      ),
      // PhonePe Prominent Center Scan Button
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: FloatingActionButton(
        elevation: 4,
        backgroundColor: AppColors.primary,
        shape: const CircleBorder(),
        onPressed: _onScanPressed,
        child: const Icon(Icons.qr_code_scanner, color: Colors.white, size: 28),
      ),
      bottomNavigationBar: BottomAppBar(
        shape: const CircularNotchedRectangle(),
        notchMargin: 8.0,
        color: Colors.white,
        elevation: 8,
        child: SizedBox(
          height: 60,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNavItem(0, Icons.home_filled, 'Home'),
              _buildNavItem(1, Icons.storefront_outlined, 'Shops'),
              const SizedBox(width: 48), // Spacing for floating scanner button
              _buildNavItem(3, Icons.receipt_long_outlined, 'History'),
              _buildNavItem(4, Icons.person_outline, 'Profile'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem(int index, IconData icon, String label) {
    final isSelected = _currentIndex == index;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => setState(() => _currentIndex = index),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            icon,
            color: isSelected ? AppColors.primary : AppColors.textSecondary,
            size: 24,
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              color: isSelected ? AppColors.primary : AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

