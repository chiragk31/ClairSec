import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

enum CsStepStatus { pending, running, completed, failed }

class StepData {
  const StepData({
    required this.title,
    this.plainLanguage,
    this.status = CsStepStatus.pending,
    this.elapsed,
    this.error,
  });

  final String title;
  final String? plainLanguage;
  final CsStepStatus status;
  final String? elapsed;
  final String? error;
}

/// Vertical stepper for scan/isolation progress (UI_SYSTEM.md §7).
class CsStepper extends StatelessWidget {
  const CsStepper({
    super.key,
    required this.steps,
  });

  final List<StepData> steps;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (int i = 0; i < steps.length; i++) ...[
          _StepRow(
            step: steps[i],
            isLast: i == steps.length - 1,
            tokens: tokens,
          ),
        ],
      ],
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({
    required this.step,
    required this.isLast,
    required this.tokens,
  });

  final StepData step;
  final bool isLast;
  final ClairTokens tokens;

  @override
  Widget build(BuildContext context) {
    final (indicatorColor, indicatorIcon) = switch (step.status) {
      CsStepStatus.completed => (tokens.success, Icons.check),
      CsStepStatus.running => (tokens.running, Icons.sync),
      CsStepStatus.failed => (tokens.danger, Icons.close),
      CsStepStatus.pending => (tokens.textMuted, Icons.circle),
    };

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Indicator column with connector line
          Column(
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: indicatorColor.withValues(alpha: tokens.isDark ? 0.2 : 0.15),
                  border: Border.all(color: indicatorColor, width: 2),
                ),
                alignment: Alignment.center,
                child: step.status == CsStepStatus.running
                    ? SizedBox(
                        width: 12,
                        height: 12,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(indicatorColor),
                        ),
                      )
                    : Icon(indicatorIcon, size: 12, color: indicatorColor),
              ),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    color: step.status == CsStepStatus.completed ? tokens.success : tokens.border,
                  ),
                ),
            ],
          ),
          const SizedBox(width: ClairSpacing.md),
          // Content column
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : ClairSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        step.title,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: tokens.textPrimary,
                        ),
                      ),
                      if (step.elapsed != null) ...[
                        const SizedBox(width: ClairSpacing.sm),
                        Text(
                          '(${step.elapsed})',
                          style: TextStyle(
                            fontSize: 12,
                            color: tokens.textSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (step.plainLanguage != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      step.plainLanguage!,
                      style: TextStyle(
                        fontSize: 13,
                        color: tokens.textSecondary,
                      ),
                    ),
                  ],
                  if (step.error != null) ...[
                    const SizedBox(height: ClairSpacing.xs),
                    Container(
                      padding: const EdgeInsets.all(ClairSpacing.sm),
                      decoration: BoxDecoration(
                        color: tokens.critical.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(ClairRadius.sm),
                        border: Border.all(color: tokens.critical.withValues(alpha: 0.3)),
                      ),
                      child: Text(
                        step.error!,
                        style: TextStyle(
                          fontSize: 12,
                          color: tokens.critical,
                          fontFamily: 'JetBrainsMono',
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
