import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../models/scan_detail.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scan_detail_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import '../vulnerabilities/widgets/finding_list_tile.dart';
import 'widgets/agent_card.dart';
import 'widgets/scan_summary_strip.dart';

/// Live scan view — DESIGN.md §6, "the centerpiece".
///
/// Renders whatever the backend reports and nothing else. Refresh is manual
/// rather than on a timer: the scan is normally already complete by the time
/// this screen opens, because Run Security Scan waits for a terminal state
/// before navigating here.
class ScanDetailScreen extends ConsumerWidget {
  final String scanId;

  const ScanDetailScreen({super.key, required this.scanId});

  void _refresh(WidgetRef ref) {
    ref.invalidate(scanProvider(scanId));
    ref.invalidate(scanFindingsProvider(scanId));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(scanDetailProvider(scanId));
    final findingsAsync = ref.watch(scanFindingsProvider(scanId));

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Scan',
            subtitle: scanId,
            actions: [
              IconButton(
                onPressed: () => _refresh(ref),
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          Expanded(
            child: state == null
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.hourglass_empty,
                      title: 'Loading scan…',
                      description:
                          'Reading this scan from the backend. If this persists, the '
                          'scan may not exist or the backend may be unreachable.',
                    ),
                  )
                : _ScanDetailContent(
                    state: state,
                    findings: findingsAsync.asData?.value ?? const <Finding>[],
                  ),
          ),
        ],
      ),
    );
  }
}

class _ScanDetailContent extends StatelessWidget {
  final ScanDetailState state;
  final List<Finding> findings;

  const _ScanDetailContent({required this.state, required this.findings});

  @override
  Widget build(BuildContext context) {
    final confirmed =
        findings.where((f) => f.status == FindingStatus.confirmed).toList();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final role in AgentRole.values)
                AgentCard(state: state.cardFor(role)),
            ],
          ),
          const SizedBox(height: 24),
          _SectionTitle(text: 'Scan summary'),
          const SizedBox(height: 12),
          ScanSummaryStrip(summary: state.summary),
          const SizedBox(height: 24),
          _SectionTitle(
            text: confirmed.isEmpty
                ? 'Confirmed findings'
                : 'Confirmed findings (${confirmed.length})',
          ),
          const SizedBox(height: 12),
          if (confirmed.isEmpty)
            const EmptyState(
              icon: Icons.shield_outlined,
              title: 'No confirmed findings',
              description:
                  'Findings appear here once the Evaluator has confirmed them '
                  'against captured runtime evidence.',
            )
          else
            for (final finding in confirmed) ...[
              FindingListTile(
                finding: finding,
                onTap: () => context.go('/vulnerabilities/${finding.id}'),
              ),
              const SizedBox(height: 12),
            ],
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            color: AppColors.textSecondary,
            letterSpacing: 0.5,
          ),
    );
  }
}
