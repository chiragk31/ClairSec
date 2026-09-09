import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/scan_detail.dart';

/// Live, ordered event log (DESIGN.md §6 "live event stream").
/// Renders in monospace per DESIGN.md §11 typography rules, and shows
/// concise operational text only — never raw chain-of-thought (DESIGN.md §9).
class EventStreamPanel extends StatelessWidget {
  final List<ScanEventEntry> events;

  const EventStreamPanel({super.key, required this.events});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Text(
              'Live event stream',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: AppColors.textSecondary,
                    letterSpacing: 0.5,
                  ),
            ),
          ),
          const Divider(height: 1),
          SizedBox(
            height: 280,
            child: events.isEmpty
                ? Center(
                    child: Text(
                      'No events yet',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(vertical: 4),
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

  Color get _levelColor => switch (entry.level) {
        ScanEventLevel.error => SeverityColors.error,
        ScanEventLevel.warning => SeverityColors.warning,
        ScanEventLevel.info => AppColors.textSecondary,
      };

  @override
  Widget build(BuildContext context) {
    final ts = entry.timestamp;
    final time =
        '${ts.hour.toString().padLeft(2, '0')}:${ts.minute.toString().padLeft(2, '0')}:${ts.second.toString().padLeft(2, '0')}';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(time, style: AppTheme.monoStyle(fontSize: 11, color: AppColors.textDisabled)),
          const SizedBox(width: 10),
          SizedBox(
            width: 64,
            child: Text(
              entry.agent.label,
              style: AppTheme.monoStyle(fontSize: 11, color: AppColors.accent),
            ),
          ),
          Expanded(
            child: Text(
              entry.message,
              style: AppTheme.monoStyle(fontSize: 12, color: _levelColor),
            ),
          ),
        ],
      ),
    );
  }
}
