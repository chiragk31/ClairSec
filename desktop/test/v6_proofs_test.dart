import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/core/theme/tokens.dart';
import 'package:desktop/features/fixes/widgets/verification_panel.dart';
import 'package:desktop/features/vulnerabilities/widgets/replay_panel.dart';
import 'package:desktop/models/patch.dart';

Widget _host(Widget child) => ProviderScope(
      child: MaterialApp(
        theme: ThemeData(extensions: const [ClairTokens.darkMidnight]),
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );

VerificationProof _proof(Map<String, dynamic> overrides) => VerificationProof.fromJson({
      'outcome': 'fixed',
      'outcomeReason': 'dual_criterion_satisfied',
      'rebuildOk': true,
      'originalExploit': {'ran': true, 'exploited': false},
      'functionalSuite': {'ran': true, 'passed': 5, 'failed': 0, 'total': 5, 'source': 'auto_smoke'},
      'variantAttack': {'ran': true, 'exploited': false, 'variantKind': 'header'},
      'endpointPreserved': {'ran': true, 'preserved': true, 'detail': 'GET /documents/{doc_id} is still defined.'},
      ...overrides,
    })!;

void main() {
  testWidgets('F9: three proof cards with honest auto-generated label', (tester) async {
    await tester.pumpWidget(_host(VerificationPanel(proof: _proof({}))));
    expect(find.text('Original exploit blocked'), findsOneWidget);
    expect(find.text('App still works (auto-generated tests)'), findsOneWidget);
    expect(find.text('Endpoint preserved'), findsOneWidget);
    expect(find.textContaining('No AI model voted'), findsOneWidget);
    expect(find.text('Fix verified against the running application'), findsOneWidget);
  });

  testWidgets('F9: a fix that deleted the endpoint is never shown as verified', (tester) async {
    final proof = _proof({
      'outcome': 'regressed',
      'endpointPreserved': {'ran': true, 'preserved': false, 'detail': 'GET /documents/{doc_id} no longer exists.'},
    });
    expect(proof.fullyVerified, isFalse);
    await tester.pumpWidget(_host(VerificationPanel(proof: proof)));
    expect(find.text('Fix verified against the running application'), findsNothing);
    expect(find.textContaining('no longer exists'), findsOneWidget);
  });

  testWidgets('F8: replay panel offers original and patched replays', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_host(const ReplayPanel(findingId: 'f1', category: 'BOLA')));
    expect(find.text('Original app'), findsOneWidget);
    expect(find.text('Patched app'), findsOneWidget);
    expect(find.text('Replay attack'), findsNWidgets(2));
    expect(find.textContaining('What we replay'), findsOneWidget);
  });
}
