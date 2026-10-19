import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/tokens.dart';
import '../../models/finding.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/empty_state.dart';
import '../shared/page_header.dart';
import '../vulnerabilities/widgets/finding_list_tile.dart';

/// Fix Review list: every finding the Fixer worked on, grouped by project, with
/// its honest verification outcome. Opening one shows the diff and the proofs.
class FixesScreen extends ConsumerWidget {
  const FixesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final scans = ref.watch(scansProvider).asData?.value ?? const [];
    final projectByScan = {for (final s in scans) s.id: s.projectName};
    final fixes = ref
        .watch(findingsProvider)
        .where((f) => f.remediationStatus != RemediationStatus.notStarted)
        .toList();

    int count(RemediationStatus s) => fixes.where((f) => f.remediationStatus == s).length;

    final groups = <String, List<Finding>>{};
    for (final f in fixes) {
      groups.putIfAbsent(projectByScan[f.scanId] ?? 'Unknown project', () => []).add(f);
    }

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Fix Review',
            subtitle: 'Patches the Fixer proposed and what the Verifier proved',
            actions: [
              IconButton(
                onPressed: () {
                  ref.invalidate(scansProvider);
                  ref.invalidate(allFindingsProvider);
                },
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(ClairSpacing.xl),
              child: fixes.isEmpty
                  ? const EmptyState(
                      icon: Icons.build_circle_outlined,
                      title: 'No fixes yet',
                      description: 'When a scan confirms a vulnerability, the Fixer writes a '
                          'patch in an isolated copy of the project and the Verifier '
                          're-runs the exploit. Those patches appear here.',
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: ClairSpacing.md,
                          runSpacing: ClairSpacing.sm,
                          children: [
                            for (final s in const [
                              RemediationStatus.fixVerified,
                              RemediationStatus.fixApplied,
                              RemediationStatus.verificationUnavailable,
                              RemediationStatus.regressed,
                              RemediationStatus.fixFailed,
                            ])
                              if (count(s) > 0)
                                Chip(
                                  avatar: Icon(s.icon, size: 15, color: s.color(tokens)),
                                  label: Text('${s.label}: ${count(s)}'),
                                ),
                          ],
                        ),
                        const SizedBox(height: ClairSpacing.lg),
                        Expanded(
                          child: ListView(
                            children: [
                              for (final e in groups.entries) ...[
                                _ProjectHeader(name: e.key, count: e.value.length),
                                for (final f in e.value) ...[
                                  FindingListTile(
                                    finding: f,
                                    onTap: () => context.go('/fixes/${f.id}'),
                                  ),
                                  const SizedBox(height: ClairSpacing.md),
                                ],
                                const SizedBox(height: ClairSpacing.md),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProjectHeader extends StatelessWidget {
  const _ProjectHeader({required this.name, required this.count});

  final String name;
  final int count;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return Padding(
      padding: const EdgeInsets.only(bottom: ClairSpacing.sm),
      child: Row(
        children: [
          Icon(Icons.folder_outlined, size: 18, color: tokens.accent),
          const SizedBox(width: ClairSpacing.sm),
          Flexible(
            child: Text(
              name,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const SizedBox(width: ClairSpacing.sm),
          Text('($count)', style: TextStyle(color: tokens.textMuted)),
        ],
      ),
    );
  }
}
