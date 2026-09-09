import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Semantic severity colours used throughout the app.
/// Never convey severity by colour alone — always pair with a label/icon.
class SeverityColors {
  const SeverityColors._();

  static const Color critical = Color(0xFFFF3B3B); // vivid red
  static const Color high = Color(0xFFFF7B2C); // orange
  static const Color medium = Color(0xFFFFBF00); // amber
  static const Color low = Color(0xFF4FC3F7); // light-blue
  static const Color informational = Color(0xFF90A4AE); // blue-grey
  static const Color success = Color(0xFF43D68C); // green
  static const Color warning = Color(0xFFFFBF00); // amber (same as medium)
  static const Color error = Color(0xFFFF3B3B); // red (same as critical)
}

class AppColors {
  const AppColors._();

  // Backgrounds
  static const Color background = Color(0xFF0D1117); // near-black
  static const Color surface = Color(0xFF161B22); // dark card
  static const Color surfaceVariant = Color(0xFF21262D); // raised surface
  static const Color border = Color(0xFF30363D); // subtle border

  // Text
  static const Color textPrimary = Color(0xFFE6EDF3); // near-white
  static const Color textSecondary = Color(0xFF8B949E); // muted
  static const Color textDisabled = Color(0xFF484F58); // very muted

  // Accent (restrained cyan-teal, avoiding neon/cyberpunk)
  static const Color accent = Color(0xFF58A6FF); // muted blue
  static const Color accentDim = Color(0xFF1F6FEB); // darker shade

  // Interactive
  static const Color hoverOverlay = Color(0x14FFFFFF); // 8% white
  static const Color selectedOverlay = Color(0x1A58A6FF); // 10% accent
}

class AppTheme {
  const AppTheme._();

  static ThemeData get dark {
    // UI font: Inter — clean, professional, highly readable
    final textTheme = GoogleFonts.interTextTheme(
      const TextTheme(
        displayLarge: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w700,
          color: AppColors.textPrimary,
          letterSpacing: -0.5,
        ),
        displayMedium: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          letterSpacing: -0.25,
        ),
        headlineLarge: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
        ),
        headlineMedium: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
        ),
        headlineSmall: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          letterSpacing: 0.5,
        ),
        titleLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w500,
          color: AppColors.textPrimary,
        ),
        titleMedium: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w500,
          color: AppColors.textPrimary,
        ),
        titleSmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: AppColors.textSecondary,
          letterSpacing: 0.4,
        ),
        bodyLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w400,
          color: AppColors.textPrimary,
        ),
        bodyMedium: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w400,
          color: AppColors.textSecondary,
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w400,
          color: AppColors.textSecondary,
        ),
        labelLarge: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w500,
          color: AppColors.textPrimary,
          letterSpacing: 0.1,
        ),
        labelMedium: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: AppColors.textSecondary,
          letterSpacing: 0.5,
        ),
        labelSmall: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: AppColors.textDisabled,
          letterSpacing: 0.5,
        ),
      ),
    );

    const colorScheme = ColorScheme.dark(
      surface: AppColors.background,
      onSurface: AppColors.textPrimary,
      primary: AppColors.accent,
      onPrimary: AppColors.background,
      secondary: AppColors.accentDim,
      onSecondary: AppColors.textPrimary,
      error: SeverityColors.error,
      onError: AppColors.textPrimary,
      outline: AppColors.border,
      surfaceContainerHighest: AppColors.surfaceVariant,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.background,
      textTheme: textTheme,
      dividerColor: AppColors.border,
      cardColor: AppColors.surface,
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: AppColors.border, width: 1),
        ),
        margin: EdgeInsets.zero,
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: 1,
        space: 1,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: GoogleFonts.inter(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
        ),
        iconTheme: const IconThemeData(color: AppColors.textSecondary),
        shape: const Border(
          bottom: BorderSide(color: AppColors.border, width: 1),
        ),
      ),
      listTileTheme: const ListTileThemeData(
        textColor: AppColors.textSecondary,
        iconColor: AppColors.textSecondary,
        selectedColor: AppColors.accent,
        selectedTileColor: AppColors.selectedOverlay,
        dense: true,
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppColors.border),
        ),
        textStyle: GoogleFonts.inter(
          fontSize: 12,
          color: AppColors.textPrimary,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.accent,
          foregroundColor: AppColors.background,
          textStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textPrimary,
          side: const BorderSide(color: AppColors.border),
          textStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w500),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: AppColors.textSecondary,
          hoverColor: AppColors.hoverOverlay,
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.surfaceVariant,
        labelStyle: GoogleFonts.inter(fontSize: 12, color: AppColors.textSecondary),
        side: const BorderSide(color: AppColors.border),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      ),
    );
  }

  /// Monospace font getter for code/log display.
  /// Use this wherever raw code, diffs, or log output appears.
  static TextStyle monoStyle({
    double fontSize = 13,
    Color color = AppColors.textPrimary,
    FontWeight fontWeight = FontWeight.w400,
  }) {
    return GoogleFonts.jetBrainsMono(
      fontSize: fontSize,
      color: color,
      fontWeight: fontWeight,
    );
  }
}
