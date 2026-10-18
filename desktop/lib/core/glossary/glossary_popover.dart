import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';
import 'glossary.dart';

/// ⓘ popover on technical terms showing plain-language definitions (UI_SYSTEM.md §9).
class GlossaryIcon extends StatelessWidget {
  const GlossaryIcon({
    super.key,
    required this.termKey,
    this.size = 14,
  });

  final String termKey;
  final double size;

  @override
  Widget build(BuildContext context) {
    final entry = kGlossaryEntries[termKey];
    if (entry == null) return const SizedBox.shrink();

    final tokens = context.tokens;

    return Tooltip(
      message: '${entry.term}:\n${entry.plain}',
      padding: const EdgeInsets.all(ClairSpacing.md),
      margin: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
      decoration: BoxDecoration(
        color: tokens.surfaceRaised,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 8,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      textStyle: TextStyle(
        color: tokens.textPrimary,
        fontSize: ClairTypography.small,
        height: 1.4,
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(ClairRadius.pill),
        onTap: () {
          showDialog<void>(
            context: context,
            builder: (ctx) => AlertDialog(
              backgroundColor: tokens.surfaceRaised,
              title: Text(entry.term, style: TextStyle(color: tokens.textPrimary)),
              content: Text(entry.plain, style: TextStyle(color: tokens.textSecondary, fontSize: ClairTypography.body)),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Close'),
                ),
              ],
            ),
          );
        },
        child: Padding(
          padding: ClairInsets.allXxs,
          child: Icon(
            Icons.info_outline,
            size: size,
            color: tokens.textMuted,
          ),
        ),
      ),
    );
  }
}
