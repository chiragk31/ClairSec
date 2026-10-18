import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';

/// Consistent empty-state widget shown when a section has no data yet.
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final Widget? action;

  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.description,
    this.action,
  });

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        vertical: ClairSpacing.xxxl,
        horizontal: ClairSpacing.xl,
      ),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: tokens.textMuted),
          const SizedBox(height: ClairSpacing.lg),
          Text(
            title,
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: tokens.textSecondary,
                ),
          ),
          const SizedBox(height: ClairSpacing.sm),
          Text(
            description,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: tokens.textMuted,
                ),
            textAlign: TextAlign.center,
          ),
          if (action != null) ...[
            const SizedBox(height: ClairSpacing.xl),
            action!,
          ],
        ],
      ),
    );
  }
}
