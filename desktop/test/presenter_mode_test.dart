import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:desktop/core/theme/theme_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('F14: presenter mode raises text scale to at least 1.25 and persists', () async {
    SharedPreferences.setMockInitialValues({});
    final c = ProviderContainer();
    addTearDown(c.dispose);
    c.read(themeSettingsProvider);
    await Future<void>.delayed(Duration.zero);
    expect(c.read(themeSettingsProvider).effectiveTextScale, 1.0);
    await c.read(themeSettingsProvider.notifier).setPresenterMode(true);
    expect(c.read(themeSettingsProvider).effectiveTextScale, 1.25);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool('clairsec_presenter_mode'), isTrue);
  });
}
