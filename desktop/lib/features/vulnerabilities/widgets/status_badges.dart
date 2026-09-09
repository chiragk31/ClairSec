import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/finding.dart';

/// Small icon+label+colour pill. Severity/status must never be conveyed by
/// colour alone (DESIGN.md §2) — every badge in this file pairs colour with
/// an icon and a text label.
class _Pill extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _Pill({required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}

class SeverityPill extends StatelessWidget {
  final FindingSeverity severity;
  const SeverityPill({super.key, required this.severity});

  @override
  Widget build(BuildContext context) =>
      _Pill(icon: severity.icon, label: severity.label, color: severity.color);
}

class FindingStatusBadge extends StatelessWidget {
  final FindingStatus status;
  const FindingStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) =>
      _Pill(icon: status.icon, label: status.label, color: status.color);
}

class RemediationStatusBadge extends StatelessWidget {
  final RemediationStatus status;
  const RemediationStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) =>
      _Pill(icon: status.icon, label: status.label, color: status.color);
}

/// Visually distinguishes a demonstrated finding from a source-suspicion-only
/// one (DESIGN.md §10a) — required whenever `runtimeConfirmed` is false, so a
/// suspicion can never be mistaken for a confirmation.
class RuntimeConfirmationBadge extends StatelessWidget {
  final bool runtimeConfirmed;
  const RuntimeConfirmationBadge({super.key, required this.runtimeConfirmed});

  @override
  Widget build(BuildContext context) {
    if (runtimeConfirmed) {
      return const _Pill(
        icon: Icons.bolt_outlined,
        label: 'Runtime confirmed',
        color: AppColors.accent,
      );
    }
    return const _Pill(
      icon: Icons.description_outlined,
      label: 'Source suspicion only',
      color: AppColors.textSecondary,
    );
  }
}
