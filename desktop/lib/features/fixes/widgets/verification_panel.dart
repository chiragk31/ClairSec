import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/theme/tokens.dart';
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
    final tokens = context.tokens;
    final verified = proof.fullyVerified;
    final accent = verified
        ? tokens.success
        : (proof.outcome == 'regressed'
            ? tokens.critical
            : tokens.warning);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(ClairRadius.md),
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
              const SizedBox(width: ClairSpacing.sm),
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
          const SizedBox(height: ClairSpacing.md + 2),

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
                : 'Exploit was not re-executed.',
          ),

          // Criterion 2 — the app still works (functional behaviour preserved).
          _Criterion(
            passed: proof.suitePassed,
            ran: proof.suiteRan,
            title: proof.suiteSource == 'auto_smoke'
                ? 'App still works (auto-generated tests)'
                : 'App still works (test suite)',
            detail: proof.suiteRan
                ? (proof.brokenTests.isEmpty
                    ? (proof.suiteSource == 'auto_smoke'
                        ? "All ${proof.total} read-only checks generated from the app's own API "
                            'description behave as they did before the fix.'
                        : 'All ${proof.total} project tests passed — no existing behaviour broken.')
                    : '${proof.brokenTests.length} check(s) broke: ${proof.brokenTests.join(", ")}')
                : (proof.suiteDetail.isNotEmpty
                    ? proof.suiteDetail
                    : 'No functional checks ran, so this fix cannot be marked verified.'),
          ),

          // Criterion 3 — the endpoint was not simply deleted.
          _Criterion(
            passed: proof.endpointPreserved,
            ran: proof.endpointCheckRan,
            title: 'Endpoint preserved',
            detail: proof.endpointDetail.isNotEmpty
                ? proof.endpointDetail
                : 'The route table of the patched code could not be read statically.',
          ),

          // Extra depth — variant attack blocked (optional).
          _Criterion(
            passed: proof.variantBlocked,
            ran: proof.variantRan,
            title: 'Variant attack blocked',
            detail: proof.variantRan
                ? (proof.variantExploited
                    ? 'A variant of the same attack still succeeds — the specific '
                        'exploit was closed but the underlying weakness may remain.'
                    : 'A mutated variant of the same attack was attempted and also '
                        'failed, indicating the underlying weakness was addressed.')
                : 'No variant attack was attempted.',
            optional: true,
          ),

          Text(
            'Every check above is platform code re-running real requests. '
            'No AI model voted on whether this fix works.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: tokens.textSecondary),
          ),
          if (proof.outcomeReason.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.sm + 2),
            Text(
              proof.outcomeReason,
              style: AppTheme.monoStyle(
                fontSize: ClairTypography.caption,
                color: tokens.textMuted,
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
    final tokens = context.tokens;
    final (icon, color) = switch ((ran, passed)) {
      (false, _) => (Icons.remove_circle_outline, tokens.textMuted),
      (true, true) => (Icons.check_circle_outline, tokens.success),
      (true, false) => optional
          ? (Icons.info_outline, tokens.warning)
          : (Icons.cancel_outlined, tokens.critical),
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: ClairSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: ClairSpacing.md - 2),
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
