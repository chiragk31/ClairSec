import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

/// Single item in the attack/scan execution timeline (UI_SYSTEM.md §7).
class TimelineItem extends StatelessWidget {
  const TimelineItem({
    super.key,
    required this.agentName,
    required this.title,
    this.plainLanguage,
    required this.timestamp,
    this.icon = Icons.bolt,
    this.onTap,
  });

  final String agentName; // builder, attacker, evaluator, fixer, verifier, assistant
  final String title;
  final String? plainLanguage;
  final String timestamp;
  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final agentColor = switch (agentName.toLowerCase()) {
      'builder' => tokens.agentBuilder,
      'attacker' => tokens.agentAttacker,
      'evaluator' => tokens.agentEvaluator,
      'fixer' => tokens.agentFixer,
      'verifier' => tokens.agentVerifier,
      'assistant' => tokens.agentAssistant,
      _ => tokens.accent,
    };

    Widget content = Container(
      margin: const EdgeInsets.only(bottom: ClairSpacing.sm),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Colored agent left rail
            Container(
              width: 4,
              decoration: BoxDecoration(
                color: agentColor,
                borderRadius: const BorderRadius.horizontal(
                  left: Radius.circular(ClairRadius.sm),
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(ClairSpacing.md),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(ClairSpacing.xs),
                      decoration: BoxDecoration(
                        color: agentColor.withValues(alpha: tokens.isDark ? 0.2 : 0.15),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(icon, size: 14, color: agentColor),
                    ),
                    const SizedBox(width: ClairSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(
                                agentName.toUpperCase(),
                                style: TextStyle(
                                  fontSize: 10.5,
                                  fontWeight: FontWeight.w700,
                                  color: agentColor,
                                  letterSpacing: 0.5,
                                ),
                              ),
                              const Spacer(),
                              Text(
                                timestamp,
                                style: TextStyle(
                                  fontSize: 11.5,
                                  color: tokens.textMuted,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Text(
                            title,
                            style: TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w600,
                              color: tokens.textPrimary,
                            ),
                          ),
                          if (plainLanguage != null) ...[
                            const SizedBox(height: 2),
                            Text(
                              plainLanguage!,
                              style: TextStyle(
                                fontSize: 12.5,
                                color: tokens.textSecondary,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );

    if (onTap != null) {
      content = InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        child: content,
      );
    }

    return content;
  }
}
