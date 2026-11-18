import 'dart:async';
import 'package:flutter/material.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/core/services/api_service.dart';
import 'package:smart_bazaar/screens/main_navigation_screen.dart';
import 'package:smart_bazaar/screens/auth/staff_login_screen.dart';

class CustomerGmailLoginScreen extends StatefulWidget {
  const CustomerGmailLoginScreen({super.key});

  @override
  State<CustomerGmailLoginScreen> createState() => _CustomerGmailLoginScreenState();
}

class _CustomerGmailLoginScreenState extends State<CustomerGmailLoginScreen> {
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  bool _otpSent = false;
  bool _isLoading = false;
  int _cooldownSeconds = 0;
  Timer? _cooldownTimer;
  String? _statusMessage;
  String? _errorMessage;

  void _startCooldown() {
    setState(() => _cooldownSeconds = 60);
    _cooldownTimer?.cancel();
    _cooldownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_cooldownSeconds > 0) {
        setState(() => _cooldownSeconds--);
      } else {
        timer.cancel();
      }
    });
  }

  Future<void> _handleSendOtp() async {
    final email = _emailController.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(() => _errorMessage = 'Please enter a valid Gmail / Email address.');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _statusMessage = null;
    });

    final res = await ApiService().sendOtp(email, purpose: 'LOGIN');
    setState(() => _isLoading = false);

    if (res['error'] != null) {
      setState(() => _errorMessage = res['error']);
    } else {
      setState(() {
        _otpSent = true;
        _statusMessage = res['message'] ?? 'OTP sent to your Gmail.';
        if (res['dev_otp'] != null) {
          _otpController.text = res['dev_otp'];
        }
      });
      _startCooldown();
    }
  }

  Future<void> _handleVerifyOtp() async {
    final email = _emailController.text.trim();
    final otp = _otpController.text.trim();

    if (otp.length != 6) {
      setState(() => _errorMessage = 'Please enter the 6-digit verification code.');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final res = await ApiService().verifyOtp(email: email, otp: otp);
    setState(() => _isLoading = false);

    if (res['error'] != null) {
      setState(() => _errorMessage = res['error']);
    } else {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const MainNavigationScreen()),
      );
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _otpController.dispose();
    _cooldownTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Purple Brand Header
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 36),
                decoration: const BoxDecoration(
                  gradient: AppColors.primaryGradient,
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(32),
                    bottomRight: Radius.circular(32),
                  ),
                ),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.15),
                            blurRadius: 10,
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.storefront_rounded,
                        size: 40,
                        color: AppColors.primary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Smart Bazaar',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Passwordless Gmail Login',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.85),
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Login Card
              Card(
                margin: const EdgeInsets.symmetric(horizontal: 20),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                elevation: 3,
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'Welcome Back!',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Enter your registered Gmail. No password required.',
                        style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
                      ),
                      const SizedBox(height: 24),

                      // Gmail Input
                      TextField(
                        controller: _emailController,
                        keyboardType: TextInputType.emailAddress,
                        enabled: !_otpSent,
                        decoration: InputDecoration(
                          labelText: 'Gmail / Email Address',
                          hintText: 'e.g. rahul.customer@gmail.com',
                          prefixIcon: const Icon(Icons.email_outlined, color: AppColors.primary),
                          suffixIcon: _otpSent
                              ? IconButton(
                                  icon: const Icon(Icons.edit, color: AppColors.primary),
                                  onPressed: () => setState(() => _otpSent = false),
                                )
                              : null,
                        ),
                      ),

                      if (_otpSent) ...[
                        const SizedBox(height: 20),
                        TextField(
                          controller: _otpController,
                          keyboardType: TextInputType.number,
                          maxLength: 6,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 8,
                          ),
                          decoration: const InputDecoration(
                            labelText: 'Enter 6-Digit OTP',
                            counterText: '',
                            prefixIcon: Icon(Icons.lock_clock_outlined, color: AppColors.primary),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              _cooldownSeconds > 0
                                  ? 'Resend in $_cooldownSeconds s'
                                  : 'Code expires in 5 min',
                              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                            ),
                            TextButton(
                              onPressed: _cooldownSeconds == 0 ? _handleSendOtp : null,
                              child: const Text('Resend OTP'),
                            ),
                          ],
                        ),
                      ],

                      if (_errorMessage != null) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.errorLight,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            _errorMessage!,
                            style: const TextStyle(color: AppColors.error, fontSize: 13),
                          ),
                        ),
                      ],

                      if (_statusMessage != null) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.successLight,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            _statusMessage!,
                            style: const TextStyle(color: AppColors.success, fontSize: 13),
                          ),
                        ),
                      ],

                      const SizedBox(height: 24),

                      ElevatedButton(
                        onPressed: _isLoading ? null : (_otpSent ? _handleVerifyOtp : _handleSendOtp),
                        child: _isLoading
                            ? const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                              )
                            : Text(_otpSent ? 'Verify OTP & Continue' : 'Send Gmail OTP'),
                      ),

                      const SizedBox(height: 16),
                      // Quick Demo Fill for instant testing
                      OutlinedButton.icon(
                        icon: const Icon(Icons.flash_on, size: 18),
                        label: const Text('Fill Demo Customer (Rahul)'),
                        onPressed: () {
                          _emailController.text = 'rahul.customer@gmail.com';
                          _handleSendOtp();
                        },
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Staff Login Route
              Center(
                child: TextButton.icon(
                  icon: const Icon(Icons.badge_outlined, color: AppColors.secondary),
                  label: const Text(
                    'Cashier / Shop Owner / Admin Login',
                    style: TextStyle(
                      color: AppColors.secondary,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const StaffLoginScreen()),
                    );
                  },
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

