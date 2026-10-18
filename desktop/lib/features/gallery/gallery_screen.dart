import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/tokens.dart';
import '../../core/theme/theme_provider.dart';
import '../../ui/ui.dart';

/// Component Gallery screen for testing tokens and components (UI_SYSTEM.md §7).
/// Route: `/_gallery`
class GalleryScreen extends ConsumerWidget {
  const GalleryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final themeSettings = ref.watch(themeSettingsProvider);
    final themeNotifier = ref.read(themeSettingsProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('UI Component Gallery'),
        actions: [
          // Preset selector
          DropdownButton<ThemePreset>(
            value: themeSettings.preset,
            dropdownColor: tokens.surfaceRaised,
            underline: const SizedBox.shrink(),
            items: ThemePreset.values.map((p) {
              return DropdownMenuItem(
                value: p,
                child: Text(p.label, style: TextStyle(color: tokens.textPrimary, fontSize: ClairTypography.body)),
              );
            }).toList(),
            onChanged: (p) {
              if (p != null) themeNotifier.setPreset(p);
            },
          ),
          const SizedBox(width: ClairSpacing.md),
          // Dark/Light toggle
          IconButton(
            icon: Icon(tokens.isDark ? Icons.light_mode : Icons.dark_mode),
            tooltip: 'Toggle Theme Mode',
            onPressed: () {
              themeNotifier.setMode(tokens.isDark ? ThemeMode.light : ThemeMode.dark);
            },
          ),
          const SizedBox(width: ClairSpacing.md),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(ClairSpacing.xl),
        children: [
          _sectionHeader(context, '1. Badges (Icons + Labels Always)'),
          Wrap(
            spacing: ClairSpacing.sm,
            runSpacing: ClairSpacing.sm,
            children: const [
              SeverityBadge(severity: 'critical'),
              SeverityBadge(severity: 'high'),
              SeverityBadge(severity: 'medium'),
              SeverityBadge(severity: 'low'),
              SeverityBadge(severity: 'info'),
              StatusBadge(status: 'success'),
              StatusBadge(status: 'warning'),
              StatusBadge(status: 'danger'),
              StatusBadge(status: 'running'),
              ModeBadge(modeId: 'live'),
              ModeBadge(modeId: 'live_local_ai'),
              ModeBadge(modeId: 'live_offline_ai'),
              ModeBadge(modeId: 'demo'),
            ],
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '2. Buttons'),
          Wrap(
            spacing: ClairSpacing.md,
            runSpacing: ClairSpacing.md,
            children: [
              CsButton(
                label: 'Primary Button',
                icon: const Icon(Icons.bolt, size: 16),
                onPressed: () {},
              ),
              CsButton(
                label: 'Loading Button',
                isLoading: true,
                onPressed: () {},
              ),
              CsButton(
                label: 'Secondary Button',
                variant: CsButtonVariant.secondary,
                onPressed: () {},
              ),
              CsButton(
                label: 'Ghost Button',
                variant: CsButtonVariant.ghost,
                onPressed: () {},
              ),
              CsButton(
                label: 'Danger Button',
                variant: CsButtonVariant.danger,
                icon: const Icon(Icons.delete_outline, size: 16),
                onPressed: () {},
              ),
              CsButton(
                label: 'Show Toast',
                variant: CsButtonVariant.secondary,
                onPressed: () => CsToast.show(
                  context,
                  message: 'This is a live notification from ClairSec!',
                  type: ToastType.success,
                  actionLabel: 'Undo',
                  onAction: () {},
                ),
              ),
              CsButton(
                label: 'Open Command Palette (Ctrl+K)',
                variant: CsButtonVariant.secondary,
                icon: const Icon(Icons.search, size: 16),
                onPressed: () => CommandPalette.show(context),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '3. Cards & Metrics'),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Expanded(
                child: CsStat(
                  label: 'Discovered Endpoints',
                  value: '24',
                  delta: '+4 new',
                  icon: Icons.radar,
                ),
              ),
              const SizedBox(width: ClairSpacing.md),
              const Expanded(
                child: CsStat(
                  label: 'Confirmed Findings',
                  value: '3',
                  delta: '-2 fixed',
                  isPositiveDeltaGood: false,
                  icon: Icons.shield,
                ),
              ),
              const SizedBox(width: ClairSpacing.md),
              Expanded(
                child: CsCard(
                  title: 'Posture Score',
                  subtitle: 'Overall security grade for latest scan',
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: ClairSpacing.sm),
                      child: const ScoreGauge(score: 88, previousScore: 65),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '4. Stepper & Pipeline Progress'),
          CsCard(
            title: 'Autonomous Scan Pipeline',
            subtitle: 'Real-time multi-agent execution pipeline',
            child: const CsStepper(
              steps: [
                StepData(
                  title: 'Builder Agent',
                  plainLanguage: 'Reads your app and maps every door into it.',
                  status: CsStepStatus.completed,
                  elapsed: '1.2s',
                ),
                StepData(
                  title: 'Attacker Agent',
                  plainLanguage: 'Tries those doors safely inside a sealed copy.',
                  status: CsStepStatus.completed,
                  elapsed: '4.8s',
                ),
                StepData(
                  title: 'Evaluator Agent',
                  plainLanguage: 'Double-checks every attack with hard deterministic rules.',
                  status: CsStepStatus.running,
                  elapsed: '0.9s',
                ),
                StepData(
                  title: 'Fixer Agent',
                  plainLanguage: 'Writes an AST code change that closes the door.',
                  status: CsStepStatus.pending,
                ),
                StepData(
                  title: 'Verifier Agent',
                  plainLanguage: 'Tries the attack again, asserting exploit blocked & tests passing.',
                  status: CsStepStatus.pending,
                ),
              ],
            ),
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '5. Timeline & Audit Provenance'),
          CsCard(
            title: 'Audit Provenance Lineage',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const ProvenanceStrip(
                  steps: [
                    ProvenanceStep(
                      agentName: 'Builder',
                      action: 'Discovered endpoint',
                      detail: '/documents/{doc_id}',
                    ),
                    ProvenanceStep(
                      agentName: 'Attacker',
                      action: 'Executed test case',
                      detail: 'BOLA parameter switch',
                    ),
                    ProvenanceStep(
                      agentName: 'Evaluator',
                      action: 'Oracle fired (BOLA-01)',
                      detail: 'Confirmed status 200',
                    ),
                    ProvenanceStep(
                      agentName: 'Fixer',
                      action: 'AST patch created',
                      detail: '3 files modified',
                    ),
                    ProvenanceStep(
                      agentName: 'Verifier',
                      action: 'Verified fixed',
                      detail: '5/5 tests passing',
                    ),
                  ],
                ),
                const SizedBox(height: ClairSpacing.lg),
                const TimelineItem(
                  agentName: 'Attacker',
                  title: 'BOLA candidate test case fired against /documents/doc_bob_02',
                  plainLanguage: 'Bob requested Alice\'s document and received HTTP 200.',
                  timestamp: '14:22:05',
                ),
                const TimelineItem(
                  agentName: 'Evaluator',
                  title: 'Deterministic oracle confirmed vulnerability #BOLA-639',
                  plainLanguage: 'Cross-tenant data leakage confirmed by rule ORACLE-BOLA-01.',
                  timestamp: '14:22:06',
                ),
              ],
            ),
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '6. Code, Diffs & HTTP Exchanges'),
          const DiffView(
            filePath: 'app/routers/documents.py',
            diffText: '''@@ -14,6 +14,8 @@
 def get_document(doc_id: str, user: User = Depends(get_current_user)):
-    return db.get(doc_id)
+    doc = db.get(doc_id)
+    if doc.owner_id != user.id: raise HTTPException(403)
+    return doc''',
          ),
          const SizedBox(height: ClairSpacing.md),
          const HttpExchangeView(
            method: 'GET',
            url: 'http://127.0.0.1:49152/documents/doc_bob_02',
            responseStatus: 200,
            responseBody: '{"id": "doc_bob_02", "owner": "bob", "content": "confidential_financials"}',
          ),
          const SizedBox(height: ClairSpacing.xxl),

          _sectionHeader(context, '7. File Tree & Skeleton Loaders'),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: CsCard(
                  title: 'Workspace File Tree',
                  child: FileTree(
                    nodes: const [
                      FileNode(
                        name: 'app',
                        isDirectory: true,
                        children: [
                          FileNode(name: 'main.py', sizeBytes: 2450),
                          FileNode(name: 'routers', isDirectory: true, children: [
                            FileNode(name: 'users.py', sizeBytes: 1820),
                            FileNode(name: 'auth.py', sizeBytes: 3100),
                          ]),
                        ],
                      ),
                      FileNode(name: 'requirements.txt', sizeBytes: 420),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: ClairSpacing.md),
              Expanded(
                child: CsCard(
                  title: 'Skeleton Placeholder',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: const [
                      Skeleton(width: 140, height: 20),
                      SizedBox(height: ClairSpacing.sm),
                      Skeleton(width: double.infinity, height: 14),
                      SizedBox(height: ClairSpacing.xs),
                      Skeleton(width: double.infinity, height: 14),
                      SizedBox(height: ClairSpacing.xs),
                      Skeleton(width: 220, height: 14),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sectionHeader(BuildContext context, String title) {
    final tokens = context.tokens;
    return Padding(
      padding: const EdgeInsets.only(bottom: ClairSpacing.md),
      child: Text(
        title,
        style: TextStyle(
          fontSize: ClairTypography.title,
          fontWeight: FontWeight.w600,
          color: tokens.textPrimary,
        ),
      ),
    );
  }
}
