import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/theme/app_theme.dart';
import 'package:smart_bazaar/core/services/api_service.dart';
import 'package:smart_bazaar/screens/splash/splash_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ApiService().init();
  runApp(const SmartBazaarApp());
}

class SmartBazaarApp extends StatelessWidget {
  const SmartBazaarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Bazaar',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const SplashScreen(),
    );
  }
}
