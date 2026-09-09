import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/scan_detail.dart';
import '../../providers/scan_detail_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/agent_card.dart';
import 'widgets/event_stream_panel.dart';
import 'widgets/scan_summary_strip.dart';

/// Live scan view — DESIGN.md §6, "the centerpiece". Built ahead of the
/// Phase 9 WebSocket wiring as a presentational shell: it renders whatever
/// [scanDetailProvider] returns and nothing else. Until that provider is
/// backed by a real event stream it returns null, and this screen shows an
/// honest "not connected" state rather than synthetic progress
/// (RULES.md §6 — never fake progress bars).
class ScanDetailScreen extends ConsumerWidget {
  final String scanId;

  const ScanDetailScreen({super.key, required this.scanId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(scanDetailProvider(scanId));

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Scan',
            subtitle: scanId,
          ),
          Expanded(
            child: state == null
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.wifi_off_outlined,
                      title: 'No live connection to this scan',
                      description:
                          'This scan is not currently streaming events, has '
                          'ended, or the live view has not been wired up yet.',
                    ),
                  )
                : _ScanDetailContent(state: state),
          ),
        ],
      ),
    );
  }
}

class _ScanDetailContent extends StatelessWidget {
  final ScanDetailState state;
  const _ScanDetailContent({required this.state});

  @override
  Widget build(BuildContext context) {
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
          EventStreamPanel(events: state.events),
          const SizedBox(height: 24),
          Text(
            'Scan summary',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: AppColors.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: 12),
          ScanSummaryStrip(summary: state.summary),
        ],
      ),
    );
  }
}
