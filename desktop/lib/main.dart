import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';

void main() {
  runApp(
    // ProviderScope is the root of Riverpod's dependency injection tree.
    // All providers are accessible from within this scope.
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

    return MaterialApp.router(
      title: 'ClairSec — Adversarial Security Platform',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      routerConfig: router,
    );
  }
}
