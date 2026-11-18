import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:smart_bazaar/core/constants/colors.dart';
import 'package:smart_bazaar/core/services/api_service.dart';

enum ScannerMode {
  productBarcode,
  upiQr,
  smartBazaarQr,
}

class ScannerScreen extends StatefulWidget {
  final ScannerMode initialMode;
  final bool returnBarcodeOnScan;

  const ScannerScreen({
    super.key,
    this.initialMode = ScannerMode.productBarcode,
    this.returnBarcodeOnScan = false,
  });

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen> with SingleTickerProviderStateMixin {
  late MobileScannerController _cameraController;
  late ScannerMode _currentMode;
  late AnimationController _laserController;
  late Animation<double> _laserAnimation;

  bool _isFlashOn = false;
  bool _isFrontCamera = false;
  bool _isProcessing = false;
  final _manualCodeController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _currentMode = widget.initialMode;
    _cameraController = MobileScannerController(
      detectionSpeed: DetectionSpeed.normal,
      facing: CameraFacing.back,
      torchEnabled: false,
    );

    _laserController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat(reverse: true);

    _laserAnimation = Tween<double>(begin: 0.05, end: 0.95).animate(
      CurvedAnimation(parent: _laserController, curve: Curves.easeInOut),
    );
  }

  void _onBarcodeDetected(BarcodeCapture capture) {
    if (_isProcessing) return;
    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;

    final rawValue = barcodes.first.rawValue;
    if (rawValue == null || rawValue.isEmpty) return;

    _handleScannedCode(rawValue);
  }

  Future<void> _handleScannedCode(String code) async {
    setState(() => _isProcessing = true);
    HapticFeedback.mediumImpact();

    if (widget.returnBarcodeOnScan) {
      if (mounted) {
        Navigator.of(context).pop(code);
      }
      return;
    }

    if (_currentMode == ScannerMode.productBarcode) {
      // Lookup product details
      final res = await ApiService().lookupBarcode(code);
      if (!mounted) return;
      if (res['found'] == true) {
        _showProductBottomSheet(res['product'], res['available_stock']);
      } else {
        _showScannedResultDialog('Product Not Found', 'No product matching barcode $code exists.');
      }
    } else if (_currentMode == ScannerMode.upiQr) {
      _showScannedResultDialog('UPI Payment QR Detected', 'Payload: $code\nReady to initiate payment intent.');
    } else {
      _showScannedResultDialog('Smart Bazaar Entity', 'Entity ID: $code');
    }
    setState(() => _isProcessing = false);
  }

  void _showProductBottomSheet(Map<String, dynamic> product, dynamic stock) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      product['name'] ?? 'Product',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.successLight,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '₹${product['selling_price']}',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.success),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Barcode: ${product['primary_barcode']} | Unit: ${product['unit'] ?? 'PCS'}',
                style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 12),
              Text(
                'Available In Stock: $stock',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: (stock > 0) ? AppColors.success : AppColors.error,
                ),
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                icon: const Icon(Icons.add_shopping_cart),
                label: const Text('Add to POS Cart'),
                onPressed: () {
                  Navigator.of(ctx).pop();
                  Navigator.of(context).pop(product['primary_barcode']);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _showScannedResultDialog(String title, String message) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              setState(() => _isProcessing = false);
            },
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _showManualEntrySheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 24,
            right: 24,
            top: 24,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Manual Code Entry',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Enter product barcode (e.g. 8901030383700) or UPI string',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _manualCodeController,
                autofocus: true,
                keyboardType: TextInputType.text,
                decoration: InputDecoration(
                  hintText: 'Enter code here...',
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.arrow_forward, color: AppColors.primary),
                    onPressed: () {
                      final code = _manualCodeController.text.trim();
                      if (code.isNotEmpty) {
                        Navigator.of(ctx).pop();
                        _handleScannedCode(code);
                      }
                    },
                  ),
                ),
                onSubmitted: (code) {
                  if (code.trim().isNotEmpty) {
                    Navigator.of(ctx).pop();
                    _handleScannedCode(code.trim());
                  }
                },
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    _cameraController.dispose();
    _laserController.dispose();
    _manualCodeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const frameSize = 260.0;

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          // Camera Preview
          MobileScanner(
            controller: _cameraController,
            onDetect: _onBarcodeDetected,
          ),

          // Translucent Dark Overlay with Clear Viewfinder Cutout
          ColorFiltered(
            colorFilter: ColorFilter.mode(
              Colors.black.withOpacity(0.55),
              BlendMode.srcOut,
            ),
            child: Stack(
              children: [
                Container(
                  decoration: const BoxDecoration(
                    color: Colors.transparent,
                  ),
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 40),
                    child: Center(
                      child: Container(
                        width: frameSize,
                        height: frameSize,
                        decoration: BoxDecoration(
                          color: Colors.black,
                          borderRadius: BorderRadius.circular(20),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Animated Corners & Moving Laser Line
          Center(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 40),
              child: SizedBox(
                width: frameSize,
                height: frameSize,
                child: Stack(
                  children: [
                    // Top-Left Corner
                    Positioned(
                      top: 0,
                      left: 0,
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          border: Border(
                            top: BorderSide(color: AppColors.accent, width: 4.5),
                            left: BorderSide(color: AppColors.accent, width: 4.5),
                          ),
                          borderRadius: BorderRadius.only(topLeft: Radius.circular(16)),
                        ),
                      ),
                    ),
                    // Top-Right Corner
                    Positioned(
                      top: 0,
                      right: 0,
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          border: Border(
                            top: BorderSide(color: AppColors.accent, width: 4.5),
                            right: BorderSide(color: AppColors.accent, width: 4.5),
                          ),
                          borderRadius: BorderRadius.only(topRight: Radius.circular(16)),
                        ),
                      ),
                    ),
                    // Bottom-Left Corner
                    Positioned(
                      bottom: 0,
                      left: 0,
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          border: Border(
                            bottom: BorderSide(color: AppColors.accent, width: 4.5),
                            left: BorderSide(color: AppColors.accent, width: 4.5),
                          ),
                          borderRadius: BorderRadius.only(bottomLeft: Radius.circular(16)),
                        ),
                      ),
                    ),
                    // Bottom-Right Corner
                    Positioned(
                      bottom: 0,
                      right: 0,
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          border: Border(
                            bottom: BorderSide(color: AppColors.accent, width: 4.5),
                            right: BorderSide(color: AppColors.accent, width: 4.5),
                          ),
                          borderRadius: BorderRadius.only(bottomRight: Radius.circular(16)),
                        ),
                      ),
                    ),

                    // Sweeping Laser Beam
                    AnimatedBuilder(
                      animation: _laserAnimation,
                      builder: (context, child) {
                        return Positioned(
                          top: frameSize * _laserAnimation.value,
                          left: 12,
                          right: 12,
                          child: Container(
                            height: 2.5,
                            decoration: BoxDecoration(
                              color: AppColors.accent,
                              boxShadow: [
                                BoxShadow(
                                  color: AppColors.accent.withOpacity(0.8),
                                  blurRadius: 10,
                                  spreadRadius: 2,
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Top App Bar Controls
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  CircleAvatar(
                    backgroundColor: Colors.black.withOpacity(0.5),
                    child: IconButton(
                      icon: const Icon(Icons.close, color: Colors.white),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ),
                  Row(
                    children: [
                      CircleAvatar(
                        backgroundColor: Colors.black.withOpacity(0.5),
                        child: IconButton(
                          icon: Icon(
                            _isFlashOn ? Icons.flash_on : Icons.flash_off,
                            color: Colors.white,
                          ),
                          onPressed: () {
                            _cameraController.toggleTorch();
                            setState(() => _isFlashOn = !_isFlashOn);
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      CircleAvatar(
                        backgroundColor: Colors.black.withOpacity(0.5),
                        child: IconButton(
                          icon: const Icon(Icons.flip_camera_ios, color: Colors.white),
                          onPressed: () {
                            _cameraController.switchCamera();
                            setState(() => _isFrontCamera = !_isFrontCamera);
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),

          // Mode Selector & Instructions at Bottom
          Positioned(
            bottom: 30,
            left: 20,
            right: 20,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Mode Tabs
                Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.65),
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      _buildModeChip('Product Barcode', ScannerMode.productBarcode),
                      _buildModeChip('UPI QR', ScannerMode.upiQr),
                      _buildModeChip('Smart Bazaar', ScannerMode.smartBazaarQr),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Manual Entry Button
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    backgroundColor: Colors.black.withOpacity(0.5),
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white54),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                  ),
                  icon: const Icon(Icons.keyboard_alt_outlined, size: 18),
                  label: const Text('Enter Code Manually'),
                  onPressed: _showManualEntrySheet,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildModeChip(String title, ScannerMode mode) {
    final isSelected = _currentMode == mode;
    return GestureDetector(
      onTap: () => setState(() => _currentMode = mode),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          title,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white70,
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

