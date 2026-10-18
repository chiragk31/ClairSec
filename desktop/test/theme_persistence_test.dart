import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:desktop/core/theme/theme_provider.dart';
import 'package:desktop/core/theme/tokens.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Theme Settings Persistence (V1 exit gate)', () {
    test('Persists mode, preset, density, and text scale to SharedPreferences and reloads', () async {
      SharedPreferences.setMockInitialValues({});

      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(themeSettingsProvider.notifier);
      await notifier.setMode(ThemeMode.dark);
      await notifier.setPreset(ThemePreset.forest);
      await notifier.setDensity(DensitySetting.compact);
      await notifier.setTextScale(1.15);
      await notifier.setReduceMotion(ReduceMotionSetting.on);

      // Verify current in-memory state
      final current = container.read(themeSettingsProvider);
      expect(current.mode, ThemeMode.dark);
      expect(current.preset, ThemePreset.forest);
      expect(current.density, DensitySetting.compact);
      expect(current.textScale, 1.15);
      expect(current.reduceMotion, ReduceMotionSetting.on);

      // Verify underlying SharedPreferences storage
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getInt('clairsec_theme_mode'), ThemeMode.dark.index);
      expect(prefs.getInt('clairsec_theme_preset'), ThemePreset.forest.index);
      expect(prefs.getInt('clairsec_theme_density'), DensitySetting.compact.index);
      expect(prefs.getDouble('clairsec_text_scale'), 1.15);
      expect(prefs.getInt('clairsec_reduce_motion'), ReduceMotionSetting.on.index);

      // Simulate app restart by creating a new ProviderContainer reading from the same SharedPreferences
      final restartedContainer = ProviderContainer();
      addTearDown(restartedContainer.dispose);

      // Trigger read & wait for async init
      restartedContainer.read(themeSettingsProvider);
      await Future<void>.delayed(const Duration(milliseconds: 50));

      final restored = restartedContainer.read(themeSettingsProvider);
      expect(restored.mode, ThemeMode.dark);
      expect(restored.preset, ThemePreset.forest);
      expect(restored.density, DensitySetting.compact);
      expect(restored.textScale, 1.15);
      expect(restored.reduceMotion, ReduceMotionSetting.on);
    });
  });
}
