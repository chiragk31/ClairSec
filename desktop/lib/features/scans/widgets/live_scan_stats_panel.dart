import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';
import '../../../providers/event_stream_provider.dart';

/// Live counters and budget meter panel (FEATURES.md F5, UI_SYSTEM.md §10).
class LiveScanStatsPanel extends StatelessWidget {
  const LiveScanStatsPanel({
    super.key,
    required this.counters,
    this.budget,
  });

  final LiveCounters counters;
  final Map<String, dynamic>? budget;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      padding: const EdgeInsets.all(ClairSpacing.md),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.analytics_outlined, size: 16, color: tokens.accent),
              const SizedBox(width: ClairSpacing.xs),
              Text(
                'Live Scan Telemetry',
                style: TextStyle(
                  fontSize: ClairTypography.h3,
                  fontWeight: FontWeight.w600,
                  color: tokens.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.md),
          Wrap(
            spacing: ClairSpacing.md,
            runSpacing: ClairSpacing.sm,
            children: [
              _StatItem(label: 'Endpoints', value: '${counters.endpoints}', color: tokens.accent),
              _StatItem(label: 'Tests Run', value: '${counters.testsExecuted}', color: tokens.info),
              _StatItem(label: 'Oracle Hits', value: '${counters.oracleHits}', color: tokens.warning),
              _StatItem(label: 'Confirmed', value: '${counters.confirmed}', color: tokens.critical),
              _StatItem(label: 'Patches', value: '${counters.patches}', color: tokens.accentMuted),
              _StatItem(label: 'Verified Fixed', value: '${counters.fixesVerified}', color: tokens.success),
            ],
          ),
          if (budget != null) ...[
            const SizedBox(height: ClairSpacing.md),
            Divider(height: 1, color: tokens.border),
            const SizedBox(height: ClairSpacing.sm),
            Row(
              children: [
                Icon(Icons.account_balance_wallet_outlined, size: 14, color: tokens.textSecondary),
                const SizedBox(width: ClairSpacing.xxs),
                Text(
                  'Resource Budget & Cost',
                  style: TextStyle(
                    fontSize: ClairTypography.caption,
                    fontWeight: FontWeight.w600,
                    color: tokens.textSecondary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: ClairSpacing.xs),
            Row(
              children: [
                if (budget!['elapsed_s'] != null)
                  Padding(
                    padding: const EdgeInsets.only(right: ClairSpacing.md),
                    child: Text(
                      'Elapsed: ${budget!['elapsed_s']}s',
                      style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textMuted),
                    ),
                  ),
                if (budget!['tokens_in'] != null)
                  Padding(
                    padding: const EdgeInsets.only(right: ClairSpacing.md),
                    child: Text(
                      'Tokens In: ${budget!['tokens_in']}',
                      style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textMuted),
                    ),
                  ),
                if (budget!['tokens_out'] != null)
                  Padding(
                    padding: const EdgeInsets.only(right: ClairSpacing.md),
                    child: Text(
                      'Tokens Out: ${budget!['tokens_out']}',
                      style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textMuted),
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  const _StatItem({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return Container(
      padding: ClairInsets.xSmY3,
      decoration: BoxDecoration(
        color: tokens.surfaceRaised,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: ClairSpacing.xs),
          Text(
            '$label: ',
            style: TextStyle(
              fontSize: ClairTypography.caption,
              color: tokens.textSecondary,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: ClairTypography.caption,
              fontWeight: FontWeight.w700,
              color: tokens.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}
