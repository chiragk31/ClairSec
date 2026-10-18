import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';
import 'core/theme/theme_provider.dart';
import 'core/theme/tokens.dart';

void registerFontLicenses() {
  LicenseRegistry.addLicense(() async* {
    final oflText = await rootBundle.loadString('assets/fonts/OFL.txt');
    yield LicenseEntryWithLineBreaks(['Inter', 'JetBrains Mono'], oflText);
  });
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Register bundled font licenses (Audit defect B5)
  registerFontLicenses();

  // Offline font rule (UI_SYSTEM.md §3, PLAN.md Round 1):
  // Never fetch fonts over the network at runtime; all fonts bundled as assets.
  GoogleFonts.config.allowRuntimeFetching = false;

  runApp(
    const ProviderScope(
      child: ClairSecApp(),
    ),
  );
}

/// Root application widget.
class ClairSecApp extends ConsumerWidget {
  const ClairSecApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final themeSettings = ref.watch(themeSettingsProvider);

    final lightTokens = ClairTokens.select(themeSettings.preset, false);
    final darkTokens = ClairTokens.select(themeSettings.preset, true);

    return MaterialApp.router(
      title: 'ClairSec — Adversarial Security Platform',
      debugShowCheckedModeBanner: false,
      themeMode: themeSettings.mode,
      theme: AppTheme.buildTheme(lightTokens, textScale: themeSettings.effectiveTextScale),
      darkTheme: AppTheme.buildTheme(darkTokens, textScale: themeSettings.effectiveTextScale),
      routerConfig: router,
    );
  }
}
