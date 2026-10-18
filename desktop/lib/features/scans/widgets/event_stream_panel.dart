import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../models/scan_detail.dart';

/// Live, ordered event log (DESIGN.md §6 "live event stream").
/// Renders in monospace per DESIGN.md §11 typography rules, and shows
/// concise operational text only — never raw chain-of-thought (DESIGN.md §9).
class EventStreamPanel extends StatelessWidget {
  final List<ScanEventEntry> events;

  const EventStreamPanel({super.key, required this.events});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              ClairSpacing.lg,
              ClairSpacing.md,
              ClairSpacing.lg,
              ClairSpacing.sm,
            ),
            child: Text(
              'Live event stream',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: tokens.textSecondary,
                    letterSpacing: 0.5,
                  ),
            ),
          ),
          Divider(height: 1, color: tokens.border),
          SizedBox(
            height: 280,
            child: events.isEmpty
                ? Center(
                    child: Text(
                      'No events yet',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: tokens.textMuted,
                          ),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xs),
                    itemCount: events.length,
                    itemBuilder: (context, i) => _EventRow(entry: events[i]),
                  ),
          ),
        ],
      ),
    );
  }
}

class _EventRow extends StatelessWidget {
  final ScanEventEntry entry;
  const _EventRow({required this.entry});

  Color _levelColor(ClairTokens tokens) => switch (entry.level) {
        ScanEventLevel.error => tokens.critical,
        ScanEventLevel.warning => tokens.warning,
        ScanEventLevel.info => tokens.textSecondary,
      };

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final ts = entry.timestamp;
    final time =
        '${ts.hour.toString().padLeft(2, '0')}:${ts.minute.toString().padLeft(2, '0')}:${ts.second.toString().padLeft(2, '0')}';

    return Padding(
      padding: ClairInsets.xLgY3,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(time, style: AppTheme.monoStyle(fontSize: ClairTypography.caption, color: tokens.textMuted)),
          const SizedBox(width: ClairSpacing.md - 2),
          SizedBox(
            width: 64,
            child: Text(
              entry.agent.label,
              style: AppTheme.monoStyle(fontSize: ClairTypography.caption, color: tokens.accent),
            ),
          ),
          Expanded(
            child: Text(
              entry.message,
              style: AppTheme.monoStyle(fontSize: ClairTypography.small, color: _levelColor(tokens)),
            ),
          ),
        ],
      ),
    );
  }
}
