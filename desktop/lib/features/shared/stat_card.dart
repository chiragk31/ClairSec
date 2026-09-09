import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

/// Severity level enum used to colour StatCard accent.
enum SeverityLevel { none, critical, high, medium, low, informational }

Color _severityColor(SeverityLevel level) {
  switch (level) {
    case SeverityLevel.critical:
      return SeverityColors.critical;
    case SeverityLevel.high:
      return SeverityColors.high;
    case SeverityLevel.medium:
      return SeverityColors.medium;
    case SeverityLevel.low:
      return SeverityColors.low;
    case SeverityLevel.informational:
      return SeverityColors.informational;
    case SeverityLevel.none:
      return AppColors.accent;
  }
}

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

  @override
  Widget build(BuildContext context) {
    final accentColor = _severityColor(severity);
    final card = Container(
      width: 180,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 15, color: accentColor),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  label,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: accentColor,
                  fontSize: 28,
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
