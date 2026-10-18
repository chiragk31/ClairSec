import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

/// Standard card component (UI_SYSTEM.md §7).
/// Flat card with 1px border, title, optional plain-language subtitle, trailing actions.
class CsCard extends StatefulWidget {
  const CsCard({
    super.key,
    this.title,
    this.subtitle,
    this.trailing,
    required this.child,
    this.padding = const EdgeInsets.all(ClairSpacing.lg),
    this.onTap,
    this.borderColor,
    this.backgroundColor,
  });

  final String? title;
  final String? subtitle;
  final Widget? trailing;
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? borderColor;
  final Color? backgroundColor;

  @override
  State<CsCard> createState() => _CsCardState();
}

class _CsCardState extends State<CsCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final bg = widget.backgroundColor ?? (_hovered && widget.onTap != null ? tokens.surfaceRaised : tokens.surface);
    final borderCol = widget.borderColor ?? (_hovered && widget.onTap != null ? tokens.accent : tokens.border);

    Widget content = Container(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: borderCol, width: 1),
      ),
      padding: widget.padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.title != null || widget.trailing != null) ...[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (widget.title != null)
                        Text(
                          widget.title!,
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                color: tokens.textPrimary,
                              ),
                        ),
                      if (widget.subtitle != null) ...[
                        const SizedBox(height: ClairSpacing.xs),
                        Text(
                          widget.subtitle!,
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: tokens.textSecondary,
                              ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (widget.trailing != null) widget.trailing!,
              ],
            ),
            const SizedBox(height: ClairSpacing.md),
          ],
          widget.child,
        ],
      ),
    );

    if (widget.onTap != null) {
      content = MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: GestureDetector(
          onTap: widget.onTap,
          child: content,
        ),
      );
    }

    return content;
  }
}
