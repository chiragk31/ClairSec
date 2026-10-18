import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';

/// Severity level enum used to colour StatCard accent.
enum SeverityLevel { none, critical, high, medium, low, informational }

/// A compact summary card showing a labelled metric value.
/// Pairs icon + label with the value to avoid colour-only communication.
class StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final String? tooltip;
  final SeverityLevel severity;

  const StatCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.tooltip,
    this.severity = SeverityLevel.none,
  });

  Color _severityColor(ClairTokens tokens) => switch (severity) {
        SeverityLevel.critical => tokens.critical,
        SeverityLevel.high => tokens.high,
        SeverityLevel.medium => tokens.medium,
        SeverityLevel.low => tokens.low,
        SeverityLevel.informational => tokens.info,
        SeverityLevel.none => tokens.accent,
      };

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final accentColor = _severityColor(tokens);

    final card = Container(
      width: 180,
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 15, color: accentColor),
              const SizedBox(width: ClairSpacing.xs + 2),
              Expanded(
                child: Text(
                  label,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: tokens.textSecondary,
                      ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.md),
          Text(
            value,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: accentColor,
                  fontSize: ClairTypography.stat,
                ),
          ),
        ],
      ),
    );

    if (tooltip != null) {
      return Tooltip(message: tooltip!, child: card);
    }
    return card;
  }
}
