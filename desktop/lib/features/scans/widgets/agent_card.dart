import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';
import '../../../models/scan_detail.dart';

/// One of the four pipeline cards on the live scan screen (DESIGN.md §6).
/// Status, task, progress, event count, and elapsed time are all sourced
/// from real backend events — never inferred or animated client-side.
class AgentCard extends StatelessWidget {
  final AgentCardState state;

  const AgentCard({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final status = state.status;
    final statusColor = status.color(tokens);

    return Container(
      width: 220,
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(
          color: status == AgentStatus.running ? statusColor : tokens.border,
          width: status == AgentStatus.running ? 1.5 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(state.role.icon, size: 16, color: tokens.textSecondary),
              const SizedBox(width: ClairSpacing.sm),
              Expanded(
                child: Text(
                  state.role.label,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ),
              _StatusPill(status: status),
            ],
          ),
          const SizedBox(height: ClairSpacing.md),
          Text(
            state.currentTask ?? 'Waiting for scan to reach this stage',
            style: Theme.of(context).textTheme.bodySmall,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: ClairSpacing.md),
          if (state.progress != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(ClairRadius.sm / 2),
              child: LinearProgressIndicator(
                value: state.progress!.clamp(0.0, 1.0),
                minHeight: 4,
                backgroundColor: tokens.surfaceRaised,
                valueColor: AlwaysStoppedAnimation(statusColor),
              ),
            ),
            const SizedBox(height: ClairSpacing.md - 2),
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
    final tokens = context.tokens;
    final color = status.color(tokens);

    return Tooltip(
      message: status.label,
      child: Container(
        padding: ClairInsets.xSmY3,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(status.icon, size: 11, color: color),
            const SizedBox(width: ClairSpacing.xs),
            Text(
              status.label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: color,
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
    final tokens = context.tokens;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: tokens.textMuted),
        const SizedBox(width: ClairSpacing.xs),
        Text(text, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }
}
