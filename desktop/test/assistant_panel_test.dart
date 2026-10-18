import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/core/theme/tokens.dart';
import 'package:desktop/features/assistant/assistant_panel.dart';
import 'package:desktop/services/assistant_service.dart';

class _FakeAssistant extends AssistantService {
  AssistantContext? lastContext;

  @override
  Future<List<String>> suggestions(String screen) async =>
      screen == 'finding' ? ['Is the fix safe?'] : ['What is happening right now?'];

  @override
  Future<AssistantReply> ask(String message, AssistantContext context,
      {bool explainSimply = false, String? conversationId}) async {
    lastContext = context;
    return const AssistantReply(
      answer: 'Verification outcome: fixed.',
      mode: 'offline',
      conversationId: 'c1',
      citations: [AssistantCitation('verification', 'v1', 'Fix verification')],
      actions: [AssistantAction('Open this finding', '/vulnerabilities/f1')],
    );
  }
}

void main() {
  test('F11: context is derived from the current route', () {
    expect(AssistantContext.fromPath('/scans/s1').scanId, 's1');
    expect(AssistantContext.fromPath('/vulnerabilities/f1').screen, 'finding');
    expect(AssistantContext.fromPath('/fixes/f1').findingId, 'f1');
    expect(AssistantContext.fromPath('/').screen, 'dashboard');
  });

  testWidgets('F11: suggestion chip asks with the screen context and shows citations', (tester) async {
    final fake = _FakeAssistant();
    await tester.pumpWidget(ProviderScope(
      overrides: [assistantServiceProvider.overrideWithValue(fake)],
      child: MaterialApp(
        theme: ThemeData(extensions: const [ClairTokens.darkMidnight]),
        home: const Scaffold(body: AssistantPanel(currentPath: '/vulnerabilities/f1')),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Is the fix safe?'), findsOneWidget);
    await tester.tap(find.text('Is the fix safe?'));
    await tester.pumpAndSettle();
    expect(fake.lastContext?.findingId, 'f1');
    expect(find.text('Verification outcome: fixed.'), findsOneWidget);
    expect(find.text('Offline assistant'), findsOneWidget);
    expect(find.textContaining('verification: Fix verification'), findsOneWidget);
    expect(find.text('Open this finding'), findsOneWidget);
  });
}
