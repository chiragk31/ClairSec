import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:desktop/core/routing/app_router.dart';
import 'package:desktop/ui/components/command_palette.dart';

void main() {
  group('Gallery Debug Guard (Audit Defect B2)', () {
    test('Router omits /_gallery route when isDebug is false', () {
      final router = createRouter(isDebug: false);
      final shellRoute = router.configuration.routes.first as ShellRoute;
      final paths = shellRoute.routes
          .whereType<GoRoute>()
          .map((r) => r.path)
          .toList();

      expect(
        paths.contains(AppRoutes.gallery),
        isFalse,
        reason: '/_gallery must not be registered when not in debug mode',
      );
    });

    test('Router includes /_gallery route when isDebug is true', () {
      final router = createRouter(isDebug: true);
      final shellRoute = router.configuration.routes.first as ShellRoute;
      final paths = shellRoute.routes
          .whereType<GoRoute>()
          .map((r) => r.path)
          .toList();

      expect(
        paths.contains(AppRoutes.gallery),
        isTrue,
        reason: '/_gallery must be registered in debug mode',
      );
    });

    test('CommandPalette omits Component Gallery action when isDebug is false', () {
      final actions = CommandPalette.getDefaultActions(isDebug: false);
      final titles = actions.map((a) => a.title).toList();

      expect(
        titles.contains('Component Gallery'),
        isFalse,
        reason: 'Command palette must not show Component Gallery when isDebug is false',
      );
    });

    test('CommandPalette includes Component Gallery action when isDebug is true', () {
      final actions = CommandPalette.getDefaultActions(isDebug: true);
      final titles = actions.map((a) => a.title).toList();

      expect(
        titles.contains('Component Gallery'),
        isTrue,
        reason: 'Command palette must include Component Gallery in debug mode',
      );
    });
  });
}
