import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../projects/widgets/import_project_dialog.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../providers/readiness_provider.dart';
import '../../../../services/readiness_service.dart';
import '../../../../ui/components/cs_badge.dart';

/// Live Backend / MongoDB / Docker / LLM / Git status banner restyled on ClairTokens (UI_SYSTEM.md §2, FEATURES.md F0, F4).
class ReadinessBanner extends ConsumerWidget {
  const ReadinessBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final report = ref.watch(readinessProvider);

    return report.when(
      loading: () => _Shell(
        color: tokens.textSecondary,
        title: 'Checking system readiness…',
        isReady: false,
        children: const [],
      ),
      error: (_, _) => const SizedBox.shrink(),
      data: (r) => _Shell(
        color: r.ready ? tokens.success : tokens.warning,
        title: r.ready
            ? 'All systems ready — scans can run'
            : 'Not ready — fix the items below before scanning',
        mode: r.mode,
        isReady: r.ready,
        onRecheck: () => ref.invalidate(readinessProvider),
        children: [for (final c in r.checks) _CheckRow(c)],
      ),
    );
  }
}

class _Shell extends StatelessWidget {
  const _Shell({
    required this.color,
    required this.title,
    required this.children,
    required this.isReady,
    this.mode,
    this.onRecheck,
  });

  final Color color;
  final String title;
  final List<Widget> children;
  final bool isReady;
  final ExperienceModeInfo? mode;
  final VoidCallback? onRecheck;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: ClairSpacing.xl),
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: color.withValues(alpha: 0.6), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final isNarrow = constraints.maxWidth < 650;
              if (isNarrow) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.circle, size: 10, color: color),
                        const SizedBox(width: ClairSpacing.md),
                        Expanded(
                          child: Text(
                            title,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  color: tokens.textPrimary,
                                  fontWeight: FontWeight.w600,
                                ),
                          ),
                        ),
                        if (mode != null)
                          ModeBadge(modeId: mode!.id, label: mode!.label, isSmall: true),
                      ],
                    ),
                    if (!isReady || onRecheck != null) ...[
                      const SizedBox(height: ClairSpacing.md),
                      Wrap(
                        spacing: ClairSpacing.md,
                        runSpacing: ClairSpacing.sm,
                        children: [
                          if (!isReady)
                            FilledButton.tonalIcon(
                              onPressed: () {
                                showDialog<bool>(
                                  context: context,
                                  builder: (ctx) => const ImportProjectDialog(initialType: ImportType.demo),
                                );
                              },
                              icon: const Icon(Icons.play_circle_outline, size: 16),
                              label: const Text('Run the demo instead'),
                            ),
                          if (onRecheck != null)
                            TextButton.icon(
                              onPressed: onRecheck,
                              icon: const Icon(Icons.refresh, size: 16),
                              label: const Text('Re-check'),
                            ),
                        ],
                      ),
                    ],
                  ],
                );
              }

              return Row(
                children: [
                  Icon(Icons.circle, size: 10, color: color),
                  const SizedBox(width: ClairSpacing.md),
                  Expanded(
                    child: Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: tokens.textPrimary,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                  ),
                  if (mode != null) ...[
                    ModeBadge(modeId: mode!.id, label: mode!.label, isSmall: true),
                    const SizedBox(width: ClairSpacing.md),
                  ],
                  if (!isReady) ...[
                    FilledButton.tonalIcon(
                      onPressed: () {
                        showDialog<bool>(
                          context: context,
                          builder: (ctx) => const ImportProjectDialog(initialType: ImportType.demo),
                        );
                      },
                      icon: const Icon(Icons.play_circle_outline, size: 16),
                      label: const Text('Run the demo instead'),
                    ),
                    const SizedBox(width: ClairSpacing.md),
                  ],
                  if (onRecheck != null)
                    TextButton.icon(
                      onPressed: onRecheck,
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text('Re-check'),
                    ),
                ],
              );
            },
          ),
          if (children.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.md),
            ...children,
          ],
        ],
      ),
    );
  }
}

class _CheckRow extends StatelessWidget {
  const _CheckRow(this.check);

  final ReadinessCheck check;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final color = check.ok ? tokens.success : tokens.critical;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(check.ok ? Icons.check_circle : Icons.cancel, size: 16, color: color),
          const SizedBox(width: ClairSpacing.md),
          SizedBox(
            width: 100,
            child: Text(
              check.name,
              style: TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: ClairTypography.body,
                color: tokens.textPrimary,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  check.detail,
                  style: TextStyle(color: tokens.textSecondary, fontSize: ClairTypography.body),
                ),
                if (!check.ok && check.fix != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    'Fix: ${check.fix}',
                    style: TextStyle(color: tokens.accent, fontSize: ClairTypography.small, fontWeight: FontWeight.w500),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
