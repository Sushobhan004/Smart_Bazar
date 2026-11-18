import 'package:flutter_test/flutter_test.dart';
import 'package:smart_bazaar/main.dart';

void main() {
  testWidgets('SmartBazaar app smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const SmartBazaarApp());
    expect(find.text('Smart Bazaar'), findsWidgets);
    // Let splash timer and animation complete
    await tester.pumpAndSettle(const Duration(seconds: 3));
  });
}
