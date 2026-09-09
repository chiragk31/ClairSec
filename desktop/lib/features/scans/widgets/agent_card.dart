import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/scan_detail.dart';

/// One of the four pipeline cards on the live scan screen (DESIGN.md §6).
/// Status, task, progress, event count, and elapsed time are all sourced
/// from real backend events — never inferred or animated client-side.
class AgentCard extends StatelessWidget {
  final AgentCardState state;

  const AgentCard({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final status = state.status;
    return Container(
      width: 220,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: status == AgentStatus.running ? status.color : AppColors.border,
          width: status == AgentStatus.running ? 1.5 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(state.role.icon, size: 16, color: AppColors.textSecondary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  state.role.label,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ),
              _StatusPill(status: status),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            state.currentTask ?? 'Waiting for scan to reach this stage',
            style: Theme.of(context).textTheme.bodySmall,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 12),
          if (state.progress != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: state.progress!.clamp(0.0, 1.0),
                minHeight: 4,
                backgroundColor: AppColors.surfaceVariant,
                valueColor: AlwaysStoppedAnimation(status.color),
              ),
            ),
            const SizedBox(height: 10),
          ],
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _InlineStat(
                icon: Icons.list_alt_outlined,
                text: '${state.eventCount} events',
              ),
              _InlineStat(
                icon: Icons.timer_outlined,
                text: _formatElapsed(state.elapsed),
              ),
            ],
          ),
        ],
      ),
    );
  }

  static String _formatElapsed(Duration d) {
    if (d == Duration.zero) return '—';
    final m = d.inMinutes;
    final s = d.inSeconds % 60;
    return m > 0 ? '${m}m ${s}s' : '${s}s';
  }
}

class _StatusPill extends StatelessWidget {
  final AgentStatus status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: status.label,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: status.color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: status.color.withValues(alpha: 0.4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(status.icon, size: 11, color: status.color),
            const SizedBox(width: 4),
            Text(
              status.label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: status.color,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InlineStat extends StatelessWidget {
  final IconData icon;
  final String text;
  const _InlineStat({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: AppColors.textDisabled),
        const SizedBox(width: 4),
        Text(text, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }
}
