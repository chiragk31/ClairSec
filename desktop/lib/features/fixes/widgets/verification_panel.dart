import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/patch.dart';

/// Displays the dual-criterion proof that a fix actually works.
///
/// This is the platform's central claim (METHODOLOGY.md §5): a patch counts
/// only if the original exploit is blocked AND the application's legitimate
/// behaviour is unchanged. Showing a single "fixed" badge would hide the half
/// that makes the claim meaningful — the simplest way to defeat an exploit is
/// to delete the endpoint it targets, and that must read as a regression, not
/// a success.
class VerificationPanel extends StatelessWidget {
  final VerificationProof proof;

  const VerificationPanel({super.key, required this.proof});

  @override
  Widget build(BuildContext context) {
    final verified = proof.fullyVerified;
    final accent = verified
        ? SeverityColors.success
        : (proof.outcome == 'regressed'
            ? SeverityColors.error
            : SeverityColors.warning);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: accent.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                verified ? Icons.verified_outlined : Icons.gpp_maybe_outlined,
                size: 18,
                color: accent,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  verified
                      ? 'Fix verified against the running application'
                      : 'Verification outcome: ${proof.outcome}',
                  style: Theme.of(context)
                      .textTheme
                      .headlineMedium
                      ?.copyWith(color: accent),
                ),
              ),
              if (proof.durationSeconds > 0)
                Text(
                  '${proof.durationSeconds.toStringAsFixed(1)}s',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
            ],
          ),
          const SizedBox(height: 14),

          // Criterion 1 — the exploit no longer works.
          _Criterion(
            passed: proof.exploitBlocked,
            ran: proof.exploitRan,
            title: 'Original exploit blocked',
            detail: proof.exploitRan
                ? (proof.stillExploitable
                    ? 'The exploit still succeeds against the patched build.'
                    : 'The same attack was re-run against the rebuilt target and no '
                        'longer succeeds.')
                : 'The exploit could not be re-run.',
          ),

          // Criterion 2 — nothing legitimate broke. This is the half that is
          // usually omitted, and the half that makes the first half meaningful.
          _Criterion(
            passed: proof.functionalityIntact,
            ran: proof.suiteRan,
            title: 'Functionality preserved',
            detail: proof.suiteRan
                ? (proof.failed == 0
                    ? "All ${proof.passed} of the application's own functional "
                        'tests still pass — the fix did not break legitimate behaviour.'
                    : '${proof.failed} previously passing test(s) now fail: '
                        '${proof.newlyFailing.join(", ")}')
                : 'The functional test suite could not be run.',
          ),

          // Robustness — did it fix the class, or just this one path?
          _Criterion(
            passed: proof.variantRan && !proof.variantExploited,
            ran: proof.variantRan,
            title: 'Withstands an adapted attack',
            detail: proof.variantRan
                ? (proof.variantExploited
                    ? 'A variant of the same attack still succeeds — the specific '
                        'exploit was closed but the underlying weakness may remain.'
                    : 'A mutated variant of the same attack was attempted and also '
                        'failed, indicating the underlying weakness was addressed.')
                : 'No variant attack was attempted.',
            optional: true,
          ),

          if (proof.outcomeReason.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              proof.outcomeReason,
              style: AppTheme.monoStyle(
                fontSize: 11,
                color: AppColors.textDisabled,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Criterion extends StatelessWidget {
  final bool passed;
  final bool ran;
  final String title;
  final String detail;

  /// Optional criteria render neutrally when not satisfied, rather than as a
  /// failure — a missing variant attack is not the same as a broken fix.
  final bool optional;

  const _Criterion({
    required this.passed,
    required this.ran,
    required this.title,
    required this.detail,
    this.optional = false,
  });

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch ((ran, passed)) {
      (false, _) => (Icons.remove_circle_outline, AppColors.textDisabled),
      (true, true) => (Icons.check_circle_outline, SeverityColors.success),
      (true, false) => optional
          ? (Icons.info_outline, SeverityColors.warning)
          : (Icons.cancel_outlined, SeverityColors.error),
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: color,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(height: 2),
                Text(detail, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
