import 'dart:math' as math;
import 'package:flutter/material.dart';

/// The 5 supported theme presets (UI_SYSTEM.md §2.4).
enum ThemePreset {
  midnightDaylight,
  ocean,
  forest,
  violet,
  highContrast;

  String get label => switch (this) {
        ThemePreset.midnightDaylight => 'Midnight / Daylight',
        ThemePreset.ocean => 'Ocean',
        ThemePreset.forest => 'Forest',
        ThemePreset.violet => 'Violet',
        ThemePreset.highContrast => 'High Contrast',
      };
}

/// Spacing scale (4-pt grid per UI_SYSTEM.md §4).
class ClairSpacing {
  const ClairSpacing._();

  static const double xxs = 2.0;
  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 12.0;
  static const double lg = 16.0;
  static const double xl = 24.0;
  static const double xxl = 32.0;
  static const double xxxl = 48.0;
}

/// Predefined EdgeInsets tokens conforming to the 4-pt grid (UI_SYSTEM.md §4).
class ClairInsets {
  const ClairInsets._();

  static const EdgeInsets zero = EdgeInsets.zero;
  static const EdgeInsets allXxs = EdgeInsets.all(ClairSpacing.xxs);
  static const EdgeInsets allXs = EdgeInsets.all(ClairSpacing.xs);
  static const EdgeInsets allSm = EdgeInsets.all(ClairSpacing.sm);
  static const EdgeInsets allMd = EdgeInsets.all(ClairSpacing.md);
  static const EdgeInsets allLg = EdgeInsets.all(ClairSpacing.lg);
  static const EdgeInsets allXl = EdgeInsets.all(ClairSpacing.xl);
  static const EdgeInsets allXxl = EdgeInsets.all(ClairSpacing.xxl);

  // Symmetric
  static const EdgeInsets xSmYXs = EdgeInsets.symmetric(horizontal: ClairSpacing.sm, vertical: ClairSpacing.xs);
  static const EdgeInsets xSmY2 = EdgeInsets.symmetric(horizontal: ClairSpacing.sm, vertical: ClairSpacing.xxs);
  static const EdgeInsets xSmY3 = EdgeInsets.symmetric(horizontal: ClairSpacing.sm, vertical: 3.0);
  static const EdgeInsets xMdYXs = EdgeInsets.symmetric(horizontal: ClairSpacing.md, vertical: ClairSpacing.xs);
  static const EdgeInsets xMdYSm = EdgeInsets.symmetric(horizontal: ClairSpacing.md, vertical: ClairSpacing.sm);
  static const EdgeInsets xLgYXs = EdgeInsets.symmetric(horizontal: ClairSpacing.lg, vertical: ClairSpacing.xs);
  static const EdgeInsets xLgYSm = EdgeInsets.symmetric(horizontal: ClairSpacing.lg, vertical: ClairSpacing.sm);
  static const EdgeInsets xLgYMd = EdgeInsets.symmetric(horizontal: ClairSpacing.lg, vertical: ClairSpacing.md);
  static const EdgeInsets xLgY3 = EdgeInsets.symmetric(horizontal: ClairSpacing.lg, vertical: 3.0);
  static const EdgeInsets xXlYXxl = EdgeInsets.symmetric(horizontal: ClairSpacing.xl, vertical: ClairSpacing.xxl);

  static const EdgeInsets y1 = EdgeInsets.symmetric(vertical: 1.0);
  static const EdgeInsets yXxs = EdgeInsets.symmetric(vertical: ClairSpacing.xxs);
  static const EdgeInsets yXs = EdgeInsets.symmetric(vertical: ClairSpacing.xs);
  static const EdgeInsets y6 = EdgeInsets.symmetric(vertical: 6.0);
  static const EdgeInsets ySm = EdgeInsets.symmetric(vertical: ClairSpacing.sm);
  static const EdgeInsets yMd = EdgeInsets.symmetric(vertical: ClairSpacing.md);
  static const EdgeInsets yLg = EdgeInsets.symmetric(vertical: ClairSpacing.lg);

  static const EdgeInsets xXs = EdgeInsets.symmetric(horizontal: ClairSpacing.xs);
  static const EdgeInsets xSm = EdgeInsets.symmetric(horizontal: ClairSpacing.sm);
  static const EdgeInsets xMd = EdgeInsets.symmetric(horizontal: ClairSpacing.md);
  static const EdgeInsets xLg = EdgeInsets.symmetric(horizontal: ClairSpacing.lg);
  static const EdgeInsets xXl = EdgeInsets.symmetric(horizontal: ClairSpacing.xl);

  // Micro & specific widgets
  static const EdgeInsets badge = EdgeInsets.symmetric(horizontal: 5.0, vertical: 1.0);
  static const EdgeInsets x6Y3 = EdgeInsets.symmetric(horizontal: 6.0, vertical: 3.0);
  static const EdgeInsets x6Y2 = EdgeInsets.symmetric(horizontal: 6.0, vertical: 2.0);
  static const EdgeInsets diffLine = EdgeInsets.symmetric(horizontal: ClairSpacing.md, vertical: 1.5);
  static const EdgeInsets compactCard = EdgeInsets.all(ClairSpacing.md - 2);
  static const EdgeInsets relaxedCard = EdgeInsets.all(ClairSpacing.md + 2);

  // Split layouts
  static const EdgeInsets leftSplit = EdgeInsets.fromLTRB(ClairSpacing.xl, ClairSpacing.xl, ClairSpacing.md, ClairSpacing.xl);
  static const EdgeInsets rightSplit = EdgeInsets.fromLTRB(ClairSpacing.md, ClairSpacing.xl, ClairSpacing.xl, ClairSpacing.xl);
}

/// Named font sizes and text scale tokens (UI_SYSTEM.md §3).
class ClairTypography {
  const ClairTypography._();

  static const double hero = 40.0;
  static const double display = 32.0;
  static const double stat = 28.0;
  static const double h1 = 24.0;
  static const double h2 = 18.0;
  static const double title = 16.0;
  static const double h3 = 15.0;
  static const double bodyLarge = 14.0;
  static const double body = 13.0;
  static const double code = 12.5;
  static const double small = 12.0;
  static const double monoSmall = 11.5;
  static const double caption = 11.0;
  static const double badge = 10.0;
  static const double micro = 0.01;
}

/// Corner radius scale (UI_SYSTEM.md §4).
class ClairRadius {
  const ClairRadius._();

  static const double sm = 6.0;
  static const double md = 10.0;
  static const double lg = 14.0;
  static const double pill = 999.0;
}

/// ClairSec theme tokens ThemeExtension (UI_SYSTEM.md §2).
/// One single source of truth for all styling.
class ClairTokens extends ThemeExtension<ClairTokens> {
  const ClairTokens({
    required this.isDark,
    required this.preset,
    required this.bg,
    required this.surface,
    required this.surfaceRaised,
    required this.border,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.accent,
    required this.accentMuted,
    required this.focusRing,
    required this.critical,
    required this.high,
    required this.medium,
    required this.low,
    required this.info,
    required this.success,
    required this.warning,
    required this.danger,
    required this.running,
    required this.neutral,
    required this.agentBuilder,
    required this.agentAttacker,
    required this.agentEvaluator,
    required this.agentFixer,
    required this.agentVerifier,
    required this.agentAssistant,
    required this.diffAddBg,
    required this.diffRemoveBg,
    required this.diffHunkBg,
  });

  final bool isDark;
  final ThemePreset preset;

  // Neutral & brand
  final Color bg;
  final Color surface;
  final Color surfaceRaised;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;
  final Color accent;
  final Color accentMuted;
  final Color focusRing;

  // Severity (always paired with icon + label)
  final Color critical;
  final Color high;
  final Color medium;
  final Color low;
  final Color info;

  // Status
  final Color success;
  final Color warning;
  final Color danger;
  final Color running;
  final Color neutral;

  // Agents
  final Color agentBuilder;
  final Color agentAttacker;
  final Color agentEvaluator;
  final Color agentFixer;
  final Color agentVerifier;
  final Color agentAssistant;

  // Diff
  final Color diffAddBg;
  final Color diffRemoveBg;
  final Color diffHunkBg;

  // ---------------------------------------------------------------------------
  // Factory constructors for presets
  // ---------------------------------------------------------------------------

  static ClairTokens of(BuildContext context) {
    return Theme.of(context).extension<ClairTokens>() ?? darkMidnight;
  }

  static const ClairTokens darkMidnight = ClairTokens(
    isDark: true,
    preset: ThemePreset.midnightDaylight,
    bg: Color(0xFF0D1117),
    surface: Color(0xFF161B22),
    surfaceRaised: Color(0xFF21262D),
    border: Color(0xFF30363D),
    textPrimary: Color(0xFFE6EDF3),
    textSecondary: Color(0xFFA0AAB6),
    textMuted: Color(0xFF6E7681),
    accent: Color(0xFF58A6FF),
    accentMuted: Color(0x331F6FEB),
    focusRing: Color(0xFF58A6FF),
    critical: Color(0xFFFF7B7B),
    high: Color(0xFFFFAB56),
    medium: Color(0xFFF8D268),
    low: Color(0xFF5CE0EA),
    info: Color(0xFFA0AAB6),
    success: Color(0xFF4FD664),
    warning: Color(0xFFF8D268),
    danger: Color(0xFFFF7B7B),
    running: Color(0xFF58A6FF),
    neutral: Color(0xFFA0AAB6),
    agentBuilder: Color(0xFFA371F7),
    agentAttacker: Color(0xFFFF7B72),
    agentEvaluator: Color(0xFFF2CC60),
    agentFixer: Color(0xFF3FB950),
    agentVerifier: Color(0xFF56D4DD),
    agentAssistant: Color(0xFF58A6FF),
    diffAddBg: Color(0x263FB950),
    diffRemoveBg: Color(0x26FF7B72),
    diffHunkBg: Color(0x1A58A6FF),
  );

  static const ClairTokens lightDaylight = ClairTokens(
    isDark: false,
    preset: ThemePreset.midnightDaylight,
    bg: Color(0xFFF6F8FA),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFEEF1F4),
    border: Color(0xFFD0D7DE),
    textPrimary: Color(0xFF1F2328),
    textSecondary: Color(0xFF4A5562),
    textMuted: Color(0xFF6E7781),
    accent: Color(0xFF0969DA),
    accentMuted: Color(0x1A0969DA),
    focusRing: Color(0xFF0969DA),
    critical: Color(0xFFB31424),
    high: Color(0xFFA63E00),
    medium: Color(0xFF8A5800),
    low: Color(0xFF0E6970),
    info: Color(0xFF4A5562),
    success: Color(0xFF146C2E),
    warning: Color(0xFF8A5800),
    danger: Color(0xFFB31424),
    running: Color(0xFF0969DA),
    neutral: Color(0xFF4A5562),
    agentBuilder: Color(0xFF8250DF),
    agentAttacker: Color(0xFFCF222E),
    agentEvaluator: Color(0xFF9A6700),
    agentFixer: Color(0xFF1A7F37),
    agentVerifier: Color(0xFF1B7C83),
    agentAssistant: Color(0xFF0969DA),
    diffAddBg: Color(0x261A7F37),
    diffRemoveBg: Color(0x26CF222E),
    diffHunkBg: Color(0x1A0969DA),
  );

  static const ClairTokens darkOcean = ClairTokens(
    isDark: true,
    preset: ThemePreset.ocean,
    bg: Color(0xFF0A131A),
    surface: Color(0xFF101C26),
    surfaceRaised: Color(0xFF172633),
    border: Color(0xFF243B4E),
    textPrimary: Color(0xFFE2F0F7),
    textSecondary: Color(0xFF9FB9CA),
    textMuted: Color(0xFF637C8E),
    accent: Color(0xFF39C5CF),
    accentMuted: Color(0x3339C5CF),
    focusRing: Color(0xFF39C5CF),
    critical: Color(0xFFFF7B7B),
    high: Color(0xFFFFAB56),
    medium: Color(0xFFF8D268),
    low: Color(0xFF5CE0EA),
    info: Color(0xFF9FB9CA),
    success: Color(0xFF4FD664),
    warning: Color(0xFFF8D268),
    danger: Color(0xFFFF7B7B),
    running: Color(0xFF39C5CF),
    neutral: Color(0xFF9FB9CA),
    agentBuilder: Color(0xFFA371F7),
    agentAttacker: Color(0xFFFF7B72),
    agentEvaluator: Color(0xFFF2CC60),
    agentFixer: Color(0xFF3FB950),
    agentVerifier: Color(0xFF56D4DD),
    agentAssistant: Color(0xFF39C5CF),
    diffAddBg: Color(0x263FB950),
    diffRemoveBg: Color(0x26FF7B72),
    diffHunkBg: Color(0x1A39C5CF),
  );

  static const ClairTokens lightOcean = ClairTokens(
    isDark: false,
    preset: ThemePreset.ocean,
    bg: Color(0xFFF2F7F9),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFE5EFF3),
    border: Color(0xFFCADBE3),
    textPrimary: Color(0xFF10232B),
    textSecondary: Color(0xFF3D5866),
    textMuted: Color(0xFF6A8493),
    accent: Color(0xFF0A6870),
    accentMuted: Color(0x1A0A6870),
    focusRing: Color(0xFF0A6870),
    critical: Color(0xFFB31424),
    high: Color(0xFFA63E00),
    medium: Color(0xFF8A5800),
    low: Color(0xFF0E6970),
    info: Color(0xFF3D5866),
    success: Color(0xFF146C2E),
    warning: Color(0xFF8A5800),
    danger: Color(0xFFB31424),
    running: Color(0xFF0A6870),
    neutral: Color(0xFF3D5866),
    agentBuilder: Color(0xFF8250DF),
    agentAttacker: Color(0xFFCF222E),
    agentEvaluator: Color(0xFF9A6700),
    agentFixer: Color(0xFF1A7F37),
    agentVerifier: Color(0xFF1B7C83),
    agentAssistant: Color(0xFF0A6870),
    diffAddBg: Color(0x261A7F37),
    diffRemoveBg: Color(0x26CF222E),
    diffHunkBg: Color(0x1A0A6870),
  );

  static const ClairTokens darkForest = ClairTokens(
    isDark: true,
    preset: ThemePreset.forest,
    bg: Color(0xFF0D140F),
    surface: Color(0xFF141F17),
    surfaceRaised: Color(0xFF1C2B20),
    border: Color(0xFF2A3D30),
    textPrimary: Color(0xFFE5F2E8),
    textSecondary: Color(0xFFA0B9A6),
    textMuted: Color(0xFF677E6D),
    accent: Color(0xFF56D364),
    accentMuted: Color(0x3356D364),
    focusRing: Color(0xFF56D364),
    critical: Color(0xFFFF7B7B),
    high: Color(0xFFFFAB56),
    medium: Color(0xFFF8D268),
    low: Color(0xFF5CE0EA),
    info: Color(0xFFA0B9A6),
    success: Color(0xFF4FD664),
    warning: Color(0xFFF8D268),
    danger: Color(0xFFFF7B7B),
    running: Color(0xFF56D364),
    neutral: Color(0xFFA0B9A6),
    agentBuilder: Color(0xFFA371F7),
    agentAttacker: Color(0xFFFF7B72),
    agentEvaluator: Color(0xFFF2CC60),
    agentFixer: Color(0xFF3FB950),
    agentVerifier: Color(0xFF56D4DD),
    agentAssistant: Color(0xFF56D364),
    diffAddBg: Color(0x263FB950),
    diffRemoveBg: Color(0x26FF7B72),
    diffHunkBg: Color(0x1A56D364),
  );

  static const ClairTokens lightForest = ClairTokens(
    isDark: false,
    preset: ThemePreset.forest,
    bg: Color(0xFFF3F8F4),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFE6F0E8),
    border: Color(0xFFCBDCCF),
    textPrimary: Color(0xFF122216),
    textSecondary: Color(0xFF3D5443),
    textMuted: Color(0xFF6B8271),
    accent: Color(0xFF146C2E),
    accentMuted: Color(0x1A146C2E),
    focusRing: Color(0xFF146C2E),
    critical: Color(0xFFB31424),
    high: Color(0xFFA63E00),
    medium: Color(0xFF8A5800),
    low: Color(0xFF0E6970),
    info: Color(0xFF3D5443),
    success: Color(0xFF146C2E),
    warning: Color(0xFF8A5800),
    danger: Color(0xFFB31424),
    running: Color(0xFF146C2E),
    neutral: Color(0xFF3D5443),
    agentBuilder: Color(0xFF8250DF),
    agentAttacker: Color(0xFFCF222E),
    agentEvaluator: Color(0xFF9A6700),
    agentFixer: Color(0xFF1A7F37),
    agentVerifier: Color(0xFF1B7C83),
    agentAssistant: Color(0xFF146C2E),
    diffAddBg: Color(0x261A7F37),
    diffRemoveBg: Color(0x26CF222E),
    diffHunkBg: Color(0x1A146C2E),
  );

  static const ClairTokens darkViolet = ClairTokens(
    isDark: true,
    preset: ThemePreset.violet,
    bg: Color(0xFF110E18),
    surface: Color(0xFF1A1624),
    surfaceRaised: Color(0xFF252033),
    border: Color(0xFF39324C),
    textPrimary: Color(0xFFF0EBF9),
    textSecondary: Color(0xFFB4A8D1),
    textMuted: Color(0xFF7A7091),
    accent: Color(0xFFBC8CFF),
    accentMuted: Color(0x33BC8CFF),
    focusRing: Color(0xFFBC8CFF),
    critical: Color(0xFFFF7B7B),
    high: Color(0xFFFFAB56),
    medium: Color(0xFFF8D268),
    low: Color(0xFF5CE0EA),
    info: Color(0xFFB4A8D1),
    success: Color(0xFF4FD664),
    warning: Color(0xFFF8D268),
    danger: Color(0xFFFF7B7B),
    running: Color(0xFFBC8CFF),
    neutral: Color(0xFFB4A8D1),
    agentBuilder: Color(0xFFA371F7),
    agentAttacker: Color(0xFFFF7B72),
    agentEvaluator: Color(0xFFF2CC60),
    agentFixer: Color(0xFF3FB950),
    agentVerifier: Color(0xFF56D4DD),
    agentAssistant: Color(0xFFBC8CFF),
    diffAddBg: Color(0x263FB950),
    diffRemoveBg: Color(0x26FF7B72),
    diffHunkBg: Color(0x1ABC8CFF),
  );

  static const ClairTokens lightViolet = ClairTokens(
    isDark: false,
    preset: ThemePreset.violet,
    bg: Color(0xFFF7F5FA),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFEEE9F5),
    border: Color(0xFFD8D0E5),
    textPrimary: Color(0xFF211A2E),
    textSecondary: Color(0xFF4E4364),
    textMuted: Color(0xFF786D90),
    accent: Color(0xFF6E39CC),
    accentMuted: Color(0x1A6E39CC),
    focusRing: Color(0xFF6E39CC),
    critical: Color(0xFFB31424),
    high: Color(0xFFA63E00),
    medium: Color(0xFF8A5800),
    low: Color(0xFF0E6970),
    info: Color(0xFF4E4364),
    success: Color(0xFF146C2E),
    warning: Color(0xFF8A5800),
    danger: Color(0xFFB31424),
    running: Color(0xFF6E39CC),
    neutral: Color(0xFF4E4364),
    agentBuilder: Color(0xFF8250DF),
    agentAttacker: Color(0xFFCF222E),
    agentEvaluator: Color(0xFF9A6700),
    agentFixer: Color(0xFF1A7F37),
    agentVerifier: Color(0xFF1B7C83),
    agentAssistant: Color(0xFF6E39CC),
    diffAddBg: Color(0x261A7F37),
    diffRemoveBg: Color(0x26CF222E),
    diffHunkBg: Color(0x1A6E39CC),
  );

  static const ClairTokens darkHighContrast = ClairTokens(
    isDark: true,
    preset: ThemePreset.highContrast,
    bg: Color(0xFF000000),
    surface: Color(0xFF0A0A0A),
    surfaceRaised: Color(0xFF171717),
    border: Color(0xFFFFFFFF),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFE5E5E5),
    textMuted: Color(0xFFCCCCCC),
    accent: Color(0xFF79B8FF),
    accentMuted: Color(0x3379B8FF),
    focusRing: Color(0xFFFFFFFF),
    critical: Color(0xFFFF9999),
    high: Color(0xFFFFC085),
    medium: Color(0xFFFFE082),
    low: Color(0xFF80E5FF),
    info: Color(0xFFE5E5E5),
    success: Color(0xFF7EE787),
    warning: Color(0xFFFFE082),
    danger: Color(0xFFFF9999),
    running: Color(0xFF79B8FF),
    neutral: Color(0xFFE5E5E5),
    agentBuilder: Color(0xFFD2A8FF),
    agentAttacker: Color(0xFFFF9999),
    agentEvaluator: Color(0xFFFFE082),
    agentFixer: Color(0xFF7EE787),
    agentVerifier: Color(0xFF80E5FF),
    agentAssistant: Color(0xFF79B8FF),
    diffAddBg: Color(0x337EE787),
    diffRemoveBg: Color(0x33FF9999),
    diffHunkBg: Color(0x3379B8FF),
  );

  static const ClairTokens lightHighContrast = ClairTokens(
    isDark: false,
    preset: ThemePreset.highContrast,
    bg: Color(0xFFFFFFFF),
    surface: Color(0xFFF5F5F5),
    surfaceRaised: Color(0xFFE5E5E5),
    border: Color(0xFF000000),
    textPrimary: Color(0xFF000000),
    textSecondary: Color(0xFF222222),
    textMuted: Color(0xFF444444),
    accent: Color(0xFF054CA3),
    accentMuted: Color(0x22054CA3),
    focusRing: Color(0xFF000000),
    critical: Color(0xFF8A000E),
    high: Color(0xFF7A2E00),
    medium: Color(0xFF6B4300),
    low: Color(0xFF085157),
    info: Color(0xFF222222),
    success: Color(0xFF0E5220),
    warning: Color(0xFF6B4300),
    danger: Color(0xFF8A000E),
    running: Color(0xFF054CA3),
    neutral: Color(0xFF222222),
    agentBuilder: Color(0xFF5823B0),
    agentAttacker: Color(0xFF8A000E),
    agentEvaluator: Color(0xFF6B4300),
    agentFixer: Color(0xFF0E5220),
    agentVerifier: Color(0xFF085157),
    agentAssistant: Color(0xFF054CA3),
    diffAddBg: Color(0x260E5220),
    diffRemoveBg: Color(0x268A000E),
    diffHunkBg: Color(0x22054CA3),
  );

  static ClairTokens select(ThemePreset preset, bool isDark) {
    return switch (preset) {
      ThemePreset.midnightDaylight => isDark ? darkMidnight : lightDaylight,
      ThemePreset.ocean => isDark ? darkOcean : lightOcean,
      ThemePreset.forest => isDark ? darkForest : lightForest,
      ThemePreset.violet => isDark ? darkViolet : lightViolet,
      ThemePreset.highContrast => isDark ? darkHighContrast : lightHighContrast,
    };
  }

  // ---------------------------------------------------------------------------
  // WCAG contrast helper (UI_SYSTEM.md §2.3)
  // ---------------------------------------------------------------------------

  static double relativeLuminance(Color c) {
    double transform(int val) {
      final s = val / 255.0;
      return s <= 0.04045 ? s / 12.92 : math.pow((s + 0.055) / 1.055, 2.4).toDouble();
    }

    final r = transform((c.r * 255).round());
    final g = transform((c.g * 255).round());
    final b = transform((c.b * 255).round());
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  static double contrastRatio(Color foreground, Color background) {
    final l1 = relativeLuminance(foreground);
    final l2 = relativeLuminance(background);
    final brighter = math.max(l1, l2);
    final darker = math.min(l1, l2);
    return (brighter + 0.05) / (darker + 0.05);
  }

  @override
  ClairTokens copyWith({
    bool? isDark,
    ThemePreset? preset,
    Color? bg,
    Color? surface,
    Color? surfaceRaised,
    Color? border,
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? accent,
    Color? accentMuted,
    Color? focusRing,
    Color? critical,
    Color? high,
    Color? medium,
    Color? low,
    Color? info,
    Color? success,
    Color? warning,
    Color? danger,
    Color? running,
    Color? neutral,
    Color? agentBuilder,
    Color? agentAttacker,
    Color? agentEvaluator,
    Color? agentFixer,
    Color? agentVerifier,
    Color? agentAssistant,
    Color? diffAddBg,
    Color? diffRemoveBg,
    Color? diffHunkBg,
  }) {
    return ClairTokens(
      isDark: isDark ?? this.isDark,
      preset: preset ?? this.preset,
      bg: bg ?? this.bg,
      surface: surface ?? this.surface,
      surfaceRaised: surfaceRaised ?? this.surfaceRaised,
      border: border ?? this.border,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textMuted: textMuted ?? this.textMuted,
      accent: accent ?? this.accent,
      accentMuted: accentMuted ?? this.accentMuted,
      focusRing: focusRing ?? this.focusRing,
      critical: critical ?? this.critical,
      high: high ?? this.high,
      medium: medium ?? this.medium,
      low: low ?? this.low,
      info: info ?? this.info,
      success: success ?? this.success,
      warning: warning ?? this.warning,
      danger: danger ?? this.danger,
      running: running ?? this.running,
      neutral: neutral ?? this.neutral,
      agentBuilder: agentBuilder ?? this.agentBuilder,
      agentAttacker: agentAttacker ?? this.agentAttacker,
      agentEvaluator: agentEvaluator ?? this.agentEvaluator,
      agentFixer: agentFixer ?? this.agentFixer,
      agentVerifier: agentVerifier ?? this.agentVerifier,
      agentAssistant: agentAssistant ?? this.agentAssistant,
      diffAddBg: diffAddBg ?? this.diffAddBg,
      diffRemoveBg: diffRemoveBg ?? this.diffRemoveBg,
      diffHunkBg: diffHunkBg ?? this.diffHunkBg,
    );
  }

  @override
  ClairTokens lerp(ThemeExtension<ClairTokens>? other, double t) {
    if (other is! ClairTokens) return this;
    return ClairTokens(
      isDark: t < 0.5 ? isDark : other.isDark,
      preset: t < 0.5 ? preset : other.preset,
      bg: Color.lerp(bg, other.bg, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceRaised: Color.lerp(surfaceRaised, other.surfaceRaised, t)!,
      border: Color.lerp(border, other.border, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      accentMuted: Color.lerp(accentMuted, other.accentMuted, t)!,
      focusRing: Color.lerp(focusRing, other.focusRing, t)!,
      critical: Color.lerp(critical, other.critical, t)!,
      high: Color.lerp(high, other.high, t)!,
      medium: Color.lerp(medium, other.medium, t)!,
      low: Color.lerp(low, other.low, t)!,
      info: Color.lerp(info, other.info, t)!,
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      danger: Color.lerp(danger, other.danger, t)!,
      running: Color.lerp(running, other.running, t)!,
      neutral: Color.lerp(neutral, other.neutral, t)!,
      agentBuilder: Color.lerp(agentBuilder, other.agentBuilder, t)!,
      agentAttacker: Color.lerp(agentAttacker, other.agentAttacker, t)!,
      agentEvaluator: Color.lerp(agentEvaluator, other.agentEvaluator, t)!,
      agentFixer: Color.lerp(agentFixer, other.agentFixer, t)!,
      agentVerifier: Color.lerp(agentVerifier, other.agentVerifier, t)!,
      agentAssistant: Color.lerp(agentAssistant, other.agentAssistant, t)!,
      diffAddBg: Color.lerp(diffAddBg, other.diffAddBg, t)!,
      diffRemoveBg: Color.lerp(diffRemoveBg, other.diffRemoveBg, t)!,
      diffHunkBg: Color.lerp(diffHunkBg, other.diffHunkBg, t)!,
    );
  }
}

/// Convenience context extension for clean token access: `context.tokens.accent`
extension ClairTokensContext on BuildContext {
  ClairTokens get tokens => ClairTokens.of(this);
}
