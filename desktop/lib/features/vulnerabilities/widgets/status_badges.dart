import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';
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
      padding: const EdgeInsets.symmetric(
        horizontal: ClairSpacing.sm,
        vertical: 3,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: ClairSpacing.xs),
          Flexible(
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
              overflow: TextOverflow.ellipsis,
            ),
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
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return _Pill(icon: severity.icon, label: severity.label, color: severity.color(tokens));
  }
}

class FindingStatusBadge extends StatelessWidget {
  final FindingStatus status;
  const FindingStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return _Pill(icon: status.icon, label: status.label, color: status.color(tokens));
  }
}

class RemediationStatusBadge extends StatelessWidget {
  final RemediationStatus status;
  const RemediationStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return _Pill(icon: status.icon, label: status.label, color: status.color(tokens));
  }
}

/// Visually distinguishes a demonstrated finding from a source-suspicion-only
/// one (DESIGN.md §10a) — required whenever `runtimeConfirmed` is false or oracle evidence
/// is absent, so a suspicion can never be mistaken for a confirmation (FEATURES.md F7).
class RuntimeConfirmationBadge extends StatelessWidget {
  final bool runtimeConfirmed;
  final bool hasOracleEvidence;
  final FindingStatus? status;

  const RuntimeConfirmationBadge({
    super.key,
    required this.runtimeConfirmed,
    this.hasOracleEvidence = true,
    this.status,
  });

  factory RuntimeConfirmationBadge.forFinding(Finding finding) {
    return RuntimeConfirmationBadge(
      runtimeConfirmed: finding.runtimeConfirmed,
      hasOracleEvidence: finding.hasOracleEvidence,
      status: finding.status,
    );
  }

  bool get isConfirmed =>
      runtimeConfirmed &&
      hasOracleEvidence &&
      (status == null || status == FindingStatus.confirmed);

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    if (isConfirmed) {
      return _Pill(
        icon: Icons.bolt_outlined,
        label: 'Runtime-confirmed · oracle-verified',
        color: tokens.accent,
      );
    }
    return _Pill(
      icon: Icons.description_outlined,
      label: 'Source suspicion — not confirmed',
      color: tokens.textSecondary,
    );
  }
}
