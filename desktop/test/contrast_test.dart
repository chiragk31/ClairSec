import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/core/theme/tokens.dart';

void main() {
  group('WCAG 2.1 Contrast Ratio Verification (UI_SYSTEM.md §2.3)', () {
    final presets = ThemePreset.values;
    final modes = [true, false]; // dark, light

    for (final preset in presets) {
      for (final isDark in modes) {
        final modeName = isDark ? 'Dark' : 'Light';
        final testName = '${preset.label} ($modeName)';

        test(testName, () {
          final tokens = ClairTokens.select(preset, isDark);
          final surfaces = <String, Color>{
            'bg': tokens.bg,
            'surface': tokens.surface,
            'surfaceRaised': tokens.surfaceRaised,
          };

          final textTokens = <String, Color>{
            'textPrimary': tokens.textPrimary,
            'textSecondary': tokens.textSecondary,
            'accent': tokens.accent,
            'critical': tokens.critical,
            'high': tokens.high,
            'medium': tokens.medium,
            'low': tokens.low,
            'info': tokens.info,
            'success': tokens.success,
            'warning': tokens.warning,
            'danger': tokens.danger,
          };

          for (final surfEntry in surfaces.entries) {
            for (final textEntry in textTokens.entries) {
              final ratio = ClairTokens.contrastRatio(textEntry.value, surfEntry.value);
              expect(
                ratio,
                greaterThanOrEqualTo(4.5),
                reason:
                    'Contrast failure in $testName: ${textEntry.key} on ${surfEntry.key} '
                    'has ratio ${ratio.toStringAsFixed(2)}:1 (minimum 4.5:1 required)',
              );
            }
          }
        });
      }
    }
  });
}
