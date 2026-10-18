import 'package:flutter/material.dart';
import '../../../core/glossary/glossary_popover.dart';
import '../../../core/theme/tokens.dart';
import '../../../models/posture.dart';
import '../../../ui/components/score_gauge.dart';

/// Posture score before → after verification (FEATURES.md F6).
///
/// Every number comes from the backend's `posture` record; this widget never
/// computes a score. Never says "Secure" — a high score only means we did not
/// find these problems.
class PostureCard extends StatelessWidget {
  const PostureCard({super.key, required this.posture});

  final Posture? posture;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final p = posture;
    return Container(
      padding: ClairInsets.allLg,
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: p == null
          ? Row(
              children: [
                Icon(Icons.speed, color: tokens.textMuted),
                const SizedBox(width: ClairSpacing.md),
                Expanded(
                  child: Text(
                    'The security score appears once the Evaluator has finished '
                    'checking every finding.',
                    style: TextStyle(color: tokens.textSecondary),
                  ),
                ),
              ],
            )
          : Wrap(
              spacing: ClairSpacing.xl,
              runSpacing: ClairSpacing.lg,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                ScoreGauge(
                  score: p.after.toDouble(),
                  previousScore: p.before.toDouble(),
                  coverage: p.coverage,
                  basis: p.basis,
                ),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 460),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text('Security score',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(width: ClairSpacing.xs),
                          const GlossaryIcon(termKey: 'posture_score'),
                        ],
                      ),
                      const SizedBox(height: ClairSpacing.sm),
                      Text(
                        'Before fixes: ${p.before} (${p.gradeBefore})   →   '
                        'After verified fixes: ${p.after} (${p.gradeAfter})',
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          color: p.improved ? tokens.success : tokens.textPrimary,
                        ),
                      ),
                      const SizedBox(height: ClairSpacing.sm),
                      if (p.limitedCoverage)
                        Padding(
                          padding: const EdgeInsets.only(bottom: ClairSpacing.sm),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.warning_amber, size: 16, color: tokens.warning),
                              const SizedBox(width: ClairSpacing.xs),
                              Text('Limited coverage — fewer than half the categories were tested',
                                  style: TextStyle(color: tokens.warning)),
                            ],
                          ),
                        ),
                      Text(p.basis, style: TextStyle(color: tokens.textSecondary)),
                      if (p.moves.isNotEmpty) ...[
                        const SizedBox(height: ClairSpacing.md),
                        Text('What moved the score',
                            style: TextStyle(
                                fontWeight: FontWeight.w600, color: tokens.textSecondary)),
                        const SizedBox(height: ClairSpacing.xs),
                        for (final m in p.moves)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xxs),
                            child: Row(
                              children: [
                                Icon(
                                  m.isFixed ? Icons.check_circle : Icons.remove_circle_outline,
                                  size: 14,
                                  color: m.isFixed ? tokens.success : tokens.danger,
                                ),
                                const SizedBox(width: ClairSpacing.xs),
                                Expanded(
                                  child: Text(
                                    '${m.title} · ${m.severity} · −${m.penalty}'
                                    '${m.isFixed ? ' (fix verified, removed from "after")' : ''}',
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(color: tokens.textPrimary),
                                  ),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}
