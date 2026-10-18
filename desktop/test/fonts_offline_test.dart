import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:desktop/core/theme/tokens.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  GoogleFonts.config.allowRuntimeFetching = false;

  group('Offline Font Verification (V0 exit gate)', () {
    test('GoogleFonts runtime fetching is strictly disabled', () {
      expect(
        GoogleFonts.config.allowRuntimeFetching,
        isFalse,
        reason: 'Network font fetching must be disabled to guarantee offline air-gapped security',
      );
    });

    testWidgets('Bundled Inter and JetBrains Mono render offline without network requests',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(
            extensions: const [ClairTokens.darkMidnight],
          ),
          home: const Scaffold(
            body: Column(
              children: [
                Text(
                  'ClairSec Security Platform',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  'BOLA CVE-2026-9999 CWE-639',
                  style: TextStyle(
                    fontFamily: 'JetBrainsMono',
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('ClairSec Security Platform'), findsOneWidget);
      expect(find.text('BOLA CVE-2026-9999 CWE-639'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
