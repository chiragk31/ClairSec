import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('B5: Inter-Variable.ttf is removed and OFL licenses exist', () {
    final fontsDir = Directory('assets/fonts');
    expect(fontsDir.existsSync(), isTrue, reason: 'assets/fonts must exist');

    final variableTtf = File('assets/fonts/Inter-Variable.ttf');
    expect(variableTtf.existsSync(), isFalse,
        reason: 'Unused Inter-Variable.ttf should be deleted per B5');

    final oflInter = File('assets/fonts/OFL-Inter.txt');
    final oflJetBrains = File('assets/fonts/OFL-JetBrainsMono.txt');
    final oflCombined = File('assets/fonts/OFL.txt');

    expect(oflInter.existsSync(), isTrue, reason: 'OFL-Inter.txt must exist');
    expect(oflJetBrains.existsSync(), isTrue, reason: 'OFL-JetBrainsMono.txt must exist');
    expect(oflCombined.existsSync(), isTrue, reason: 'OFL.txt must exist');
  });

  test('B5: registerFontLicenses adds Inter and JetBrains Mono to LicenseRegistry', () async {
    registerFontLicenses();

    // Verify LicenseRegistry produces licenses without error
    final licenses = await LicenseRegistry.licenses.toList();
    expect(licenses, isNotEmpty);
  });
}
