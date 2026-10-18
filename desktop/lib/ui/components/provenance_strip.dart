import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

class ProvenanceStep {
  const ProvenanceStep({
    required this.agentName,
    required this.action,
    this.detail,
    this.timestamp,
    this.status = 'completed',
  });

  final String agentName; // builder, attacker, evaluator, fixer, verifier, or "AI proposal"/"Platform code"
  final String action;
  final String? detail;
  final String? timestamp;

  /// completed | failed | unknown | unverified | unconfirmed — from the backend record.
  final String status;

  /// Maps one step of `GET /api/findings/{id}/provenance`.
  factory ProvenanceStep.fromJson(Map<String, dynamic> json) => ProvenanceStep(
        agentName: (json['who'] ?? 'Platform code') as String,
        action: (json['title'] ?? json['action'] ?? '') as String,
        detail: json['detail'] as String?,
        timestamp: json['timestamp']?.toString(),
        status: (json['status'] ?? 'unknown') as String,
      );
}

/// Provenance audit strip (UI_SYSTEM.md §7, FEATURES.md F7).
/// Renders the cryptographic/deterministic lineage of how a finding was discovered, verified, and fixed.
class ProvenanceStrip extends StatelessWidget {
  const ProvenanceStrip({
    super.key,
    required this.steps,
  });

  final List<ProvenanceStep> steps;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    Color agentColor(String name) => switch (name.toLowerCase()) {
          'builder' => tokens.agentBuilder,
          'attacker' => tokens.agentAttacker,
          'evaluator' => tokens.agentEvaluator,
          'fixer' => tokens.agentFixer,
          'verifier' => tokens.agentVerifier,
          'ai proposal' => tokens.agentAttacker,
          'platform code' => tokens.agentVerifier,
          _ => tokens.accent,
        };

    (IconData, Color) statusIcon(String status) => switch (status) {
          'completed' => (Icons.check_circle, tokens.success),
          'failed' => (Icons.cancel, tokens.danger),
          _ => (Icons.help_outline, tokens.textMuted),
        };

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (int i = 0; i < steps.length; i++) ...[
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: ClairSpacing.md,
                vertical: ClairSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: tokens.surface,
                borderRadius: BorderRadius.circular(ClairRadius.sm),
                border: Border.all(
                  color: agentColor(steps[i].agentName).withValues(alpha: 0.35),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Tooltip(
                    message: 'Step ${i + 1}: ${steps[i].status}',
                    child: Icon(
                      statusIcon(steps[i].status).$1,
                      size: 14,
                      color: statusIcon(steps[i].status).$2,
                    ),
                  ),
                  const SizedBox(width: ClairSpacing.sm),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        steps[i].agentName.toUpperCase(),
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: agentColor(steps[i].agentName),
                          letterSpacing: 0.5,
                        ),
                      ),
                      Text(
                        steps[i].action,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: tokens.textPrimary,
                        ),
                      ),
                      if (steps[i].detail != null)
                        Text(
                          steps[i].detail!,
                          style: TextStyle(
                            fontFamily: 'JetBrainsMono',
                            fontSize: 11,
                            color: tokens.textSecondary,
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
            if (i < steps.length - 1) ...[
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.xs),
                child: Icon(Icons.arrow_forward, size: 14, color: tokens.textMuted),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
