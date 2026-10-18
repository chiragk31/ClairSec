import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/theme_provider.dart';
import '../../core/theme/tokens.dart';
import '../../models/finding.dart';
import '../../models/scan_detail.dart';
import '../../providers/event_stream_provider.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scan_detail_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import '../vulnerabilities/widgets/finding_list_tile.dart';
import 'widgets/agent_card.dart';
import 'widgets/attack_surface_map.dart';
import 'widgets/attack_timeline.dart';
import 'widgets/posture_card.dart';
import '../../ui/components/cs_badge.dart';
import 'widgets/live_scan_stats_panel.dart';
import 'widgets/scan_summary_strip.dart';

/// Live scan view — DESIGN.md §6, "the centerpiece".
///
/// Renders whatever the backend reports and nothing else. Refresh is manual
/// rather than on a timer: the scan is normally already complete by the time
/// this screen opens, because Run Security Scan waits for a terminal state
/// before navigating here.
const _modeLabels = {
  'live': 'LIVE',
  'live_local_ai': 'LIVE · LOCAL AI',
  'live_offline_ai': 'LIVE · OFFLINE AI',
  'demo': 'DEMO APP',
  'recorded': 'RECORDED RUN',
};

class ScanDetailScreen extends ConsumerWidget {
  final String scanId;

  const ScanDetailScreen({super.key, required this.scanId});

  void _refresh(WidgetRef ref) {
    ref.invalidate(scanProvider(scanId));
    ref.invalidate(scanFindingsProvider(scanId));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final state = ref.watch(scanDetailProvider(scanId));
    final findingsAsync = ref.watch(scanFindingsProvider(scanId));

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Scan',
            subtitle: scanId,
            actions: [
              if (ref.watch(scanProvider(scanId)).asData?.value case final summary?)
                Padding(
                  padding: const EdgeInsets.only(right: ClairSpacing.sm),
                  child: ModeBadge(
                    modeId: summary.mode,
                    label: _modeLabels[summary.mode] ?? summary.mode.toUpperCase(),
                  ),
                ),
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
                    padding: ClairInsets.allXl,
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

class _ScanDetailContent extends ConsumerWidget {
  final ScanDetailState state;
  final List<Finding> findings;

  const _ScanDetailContent({required this.state, required this.findings});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final confirmed =
        findings.where((f) => f.status == FindingStatus.confirmed).toList();
    final events = ref.watch(scanEventsProvider(state.scanId));
    final liveCounters = ref.watch(scanLiveCountersProvider(state.scanId));
    final budget = ref.watch(scanBudgetProvider(state.scanId));

    return SingleChildScrollView(
      padding: ClairInsets.allXl,
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
          PostureCard(
            posture: ref.watch(scanProvider(state.scanId)).asData?.value.posture,
          ),
          const SizedBox(height: 24),
          LiveScanStatsPanel(
            counters: liveCounters,
            // Presenter mode hides developer details such as token cost (F14).
            budget: ref.watch(themeSettingsProvider).presenterMode ? null : budget,
          ),
          const SizedBox(height: 24),
          AttackTimeline(
            events: events,
            onSelectFinding: (fid) => context.go('/vulnerabilities/$fid'),
          ),
          const SizedBox(height: 24),
          _SectionTitle(text: 'Attack surface'),
          const SizedBox(height: 4),
          Text(
            'Every door into the app. Coloured doors had a confirmed problem.',
            style: TextStyle(color: context.tokens.textSecondary),
          ),
          const SizedBox(height: 12),
          _SurfaceSection(scanId: state.scanId),
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
    final tokens = context.tokens;
    return Text(
      text,
      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            color: tokens.textSecondary,
            letterSpacing: 0.5,
          ),
    );
  }
}


class _SurfaceSection extends ConsumerWidget {
  const _SurfaceSection({required this.scanId});

  final String scanId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final surface = ref.watch(scanSurfaceProvider(scanId));
    return surface.when(
      loading: () => const SizedBox(
        height: 80,
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      ),
      error: (e, _) => EmptyState(
        icon: Icons.account_tree_outlined,
        title: 'Attack surface unavailable',
        description: 'Could not load the endpoint map for this scan: $e',
      ),
      data: (s) => s.nodes.isEmpty
          ? const EmptyState(
              icon: Icons.account_tree_outlined,
              title: 'No endpoints mapped yet',
              description: 'The map fills in once the Builder has read the app.',
            )
          : SizedBox(
              height: 420,
              child: AttackSurfaceMap(
                nodes: s.nodes,
                edges: s.edges,
                onNodeSelected: (node) {
                  if (node.findingIds.isNotEmpty) {
                    context.go('/vulnerabilities/${node.findingIds.first}');
                  }
                },
              ),
            ),
    );
  }
}
