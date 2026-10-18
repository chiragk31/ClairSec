import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

/// Stat metric card (UI_SYSTEM.md §7).
/// Number + label + delta + optional trend indicator.
class CsStat extends StatelessWidget {
  const CsStat({
    super.key,
    required this.label,
    required this.value,
    this.delta,
    this.isPositiveDeltaGood = true,
    this.unit,
    this.icon,
  });

  final String label;
  final String value;
  final String? delta;
  final bool isPositiveDeltaGood;
  final String? unit;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label.toUpperCase(),
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                    color: tokens.textSecondary,
                  ),
                ),
              ),
              if (icon != null) Icon(icon, size: 16, color: tokens.textMuted),
            ],
          ),
          const SizedBox(height: ClairSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                value,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.5,
                  color: tokens.textPrimary,
                ),
              ),
              if (unit != null) ...[
                const SizedBox(width: ClairSpacing.xs),
                Text(
                  unit!,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: tokens.textSecondary,
                  ),
                ),
              ],
            ],
          ),
          if (delta != null) ...[
            const SizedBox(height: ClairSpacing.xs),
            Row(
              children: [
                Icon(
                  delta!.startsWith('+') ? Icons.trending_up : Icons.trending_down,
                  size: 14,
                  color: (delta!.startsWith('+') == isPositiveDeltaGood) ? tokens.success : tokens.critical,
                ),
                const SizedBox(width: ClairSpacing.xs),
                Text(
                  delta!,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: (delta!.startsWith('+') == isPositiveDeltaGood) ? tokens.success : tokens.critical,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
