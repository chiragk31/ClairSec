import 'package:flutter/material.dart';
import 'tokens.dart';

/// AppTheme generator for ClairSec v2 (UI_SYSTEM.md §2–§4).
class AppTheme {
  const AppTheme._();

  static ThemeData get dark => buildTheme(ClairTokens.darkMidnight);
  static ThemeData get light => buildTheme(ClairTokens.lightDaylight);

  /// Builds a complete Material 3 ThemeData from ClairTokens.
  static ThemeData buildTheme(ClairTokens tokens, {double textScale = 1.0}) {
    final colorScheme = ColorScheme(
      brightness: tokens.isDark ? Brightness.dark : Brightness.light,
      primary: tokens.accent,
      onPrimary: tokens.isDark ? tokens.bg : Colors.white,
      secondary: tokens.accentMuted,
      onSecondary: tokens.textPrimary,
      error: tokens.critical,
      onError: Colors.white,
      surface: tokens.surface,
      onSurface: tokens.textPrimary,
      outline: tokens.border,
      surfaceContainerHighest: tokens.surfaceRaised,
    );

    const fontFamily = 'Inter';

    TextStyle s(double size, FontWeight weight, double height, Color color, [double? spacing]) {
      return TextStyle(
        fontFamily: fontFamily,
        fontSize: size * textScale,
        fontWeight: weight,
        height: height,
        color: color,
        letterSpacing: spacing,
      );
    }

    final textTheme = TextTheme(
      // display (score, hero numbers: 40 / 700 / 1.1)
      displayLarge: s(40, FontWeight.w700, 1.1, tokens.textPrimary, -0.5),
      displayMedium: s(32, FontWeight.w700, 1.15, tokens.textPrimary, -0.4),
      displaySmall: s(28, FontWeight.w700, 1.2, tokens.textPrimary, -0.3),

      // h1 page title (24 / 650 / 1.25)
      headlineLarge: s(24, FontWeight.w600, 1.25, tokens.textPrimary, -0.2),
      // h2 section (18 / 600 / 1.3)
      headlineMedium: s(18, FontWeight.w600, 1.3, tokens.textPrimary),
      // h3 card title (15 / 600 / 1.35)
      headlineSmall: s(15, FontWeight.w600, 1.35, tokens.textPrimary),

      titleLarge: s(16, FontWeight.w600, 1.3, tokens.textPrimary),
      titleMedium: s(14, FontWeight.w600, 1.35, tokens.textPrimary),
      titleSmall: s(13, FontWeight.w500, 1.4, tokens.textSecondary),

      // body (14 / 400 / 1.5)
      bodyLarge: s(14, FontWeight.w400, 1.5, tokens.textPrimary),
      // bodySmall (13 / 400 / 1.45)
      bodyMedium: s(13, FontWeight.w400, 1.45, tokens.textSecondary),
      bodySmall: s(12, FontWeight.w400, 1.4, tokens.textMuted),

      // label (chips, badges: 12 / 600 / 1.2, +0.2 letter spacing)
      labelLarge: s(13, FontWeight.w600, 1.2, tokens.textPrimary, 0.1),
      labelMedium: s(12, FontWeight.w600, 1.2, tokens.textSecondary, 0.2),
      labelSmall: s(11, FontWeight.w500, 1.2, tokens.textMuted, 0.2),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: tokens.isDark ? Brightness.dark : Brightness.light,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: tokens.bg,
      textTheme: textTheme,
      dividerColor: tokens.border,
      cardColor: tokens.surface,
      extensions: [tokens],
      cardTheme: CardThemeData(
        color: tokens.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ClairRadius.md),
          side: BorderSide(color: tokens.border, width: 1),
        ),
        margin: EdgeInsets.zero,
      ),
      dividerTheme: DividerThemeData(
        color: tokens.border,
        thickness: 1,
        space: 1,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: tokens.surface,
        foregroundColor: tokens.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: s(15, FontWeight.w600, 1.3, tokens.textPrimary),
        iconTheme: IconThemeData(color: tokens.textSecondary),
        shape: Border(
          bottom: BorderSide(color: tokens.border, width: 1),
        ),
      ),
      listTileTheme: ListTileThemeData(
        textColor: tokens.textSecondary,
        iconColor: tokens.textSecondary,
        selectedColor: tokens.accent,
        selectedTileColor: tokens.accentMuted,
        dense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.lg,
          vertical: ClairSpacing.xs,
        ),
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: tokens.surfaceRaised,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(color: tokens.border),
        ),
        textStyle: s(12, FontWeight.w400, 1.2, tokens.textPrimary),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: tokens.accent,
          foregroundColor: tokens.isDark ? tokens.bg : Colors.white,
          textStyle: s(13, FontWeight.w600, 1.2, tokens.isDark ? tokens.bg : Colors.white),
          padding: const EdgeInsets.symmetric(
            horizontal: ClairSpacing.lg,
            vertical: ClairSpacing.md,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(ClairRadius.sm),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: tokens.textPrimary,
          side: BorderSide(color: tokens.border),
          textStyle: s(13, FontWeight.w500, 1.2, tokens.textPrimary),
          padding: const EdgeInsets.symmetric(
            horizontal: ClairSpacing.lg,
            vertical: ClairSpacing.md,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(ClairRadius.sm),
          ),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: tokens.textSecondary,
          hoverColor: tokens.accentMuted,
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: tokens.surfaceRaised,
        labelStyle: s(12, FontWeight.w600, 1.2, tokens.textSecondary, 0.2),
        side: BorderSide(color: tokens.border),
        padding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.sm,
          vertical: ClairSpacing.xs,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ClairRadius.sm),
        ),
      ),
    );
  }

  /// Monospace font getter for code/log/request display (UI_SYSTEM.md §3).
  static TextStyle monoStyle({
    double fontSize = 13,
    Color? color,
    FontWeight fontWeight = FontWeight.w400,
    double height = 1.5,
  }) {
    return TextStyle(
      fontFamily: 'JetBrainsMono',
      fontSize: fontSize,
      color: color,
      fontWeight: fontWeight,
      height: height,
    );
  }
}
