import 'package:flutter/material.dart';

class AppColors {
  // Premium Supermarket Forest Green Palette
  static const Color primary = Color(0xFF0F5132);       // Dark green primary
  static const Color secondary = Color(0xFF15803D);     // Forest emerald
  static const Color accent = Color(0xFF22C55E);        // Light green accent
  static const Color primaryLight = Color(0xFFDCFCE7);   // Soft mint green
  static const Color primaryDark = Color(0xFF0A3622);    // Deep forest green
  
  // Background & Surface
  static const Color background = Color(0xFFF8FAFC);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color card = Color(0xFFFFFFFF);

  // Text
  static const Color textPrimary = Color(0xFF0F172A);
  static const Color textSecondary = Color(0xFF475569);
  static const Color textMuted = Color(0xFF64748B);

  // Functional Status Colors
  static const Color success = Color(0xFF15803D);
  static const Color successLight = Color(0xFFDCFCE7);
  static const Color warning = Color(0xFFD97706);
  static const Color warningLight = Color(0xFFFEF3C7);
  static const Color error = Color(0xFFDC2626);
  static const Color errorLight = Color(0xFFFEE2E2);

  // Gradients
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [Color(0xFF0F5132), Color(0xFF15803D)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient cardGradient = LinearGradient(
    colors: [Color(0xFF15803D), Color(0xFF22C55E)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}

