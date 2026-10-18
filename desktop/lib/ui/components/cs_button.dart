import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

enum CsButtonVariant { primary, secondary, ghost, danger }

/// Consistent button component (UI_SYSTEM.md §7).
/// Supports primary, secondary, ghost, and danger variants, with loading state and keyboard focus.
class CsButton extends StatefulWidget {
  const CsButton({
    super.key,
    required this.label,
    this.icon,
    required this.onPressed,
    this.variant = CsButtonVariant.primary,
    this.isLoading = false,
    this.isFullWidth = false,
  });

  final String label;
  final Widget? icon;
  final VoidCallback? onPressed;
  final CsButtonVariant variant;
  final bool isLoading;
  final bool isFullWidth;

  @override
  State<CsButton> createState() => _CsButtonState();
}

class _CsButtonState extends State<CsButton> {
  bool _focused = false;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final isEnabled = widget.onPressed != null && !widget.isLoading;

    final (bg, fg, border) = switch (widget.variant) {
      CsButtonVariant.primary => (
        isEnabled ? tokens.accent : tokens.accent.withValues(alpha: 0.5),
        tokens.isDark ? tokens.bg : Colors.white,
        Colors.transparent,
      ),
      CsButtonVariant.secondary => (
        tokens.surfaceRaised,
        tokens.textPrimary,
        tokens.border,
      ),
      CsButtonVariant.ghost => (
        Colors.transparent,
        tokens.textSecondary,
        Colors.transparent,
      ),
      CsButtonVariant.danger => (
        tokens.critical.withValues(alpha: tokens.isDark ? 0.15 : 0.12),
        tokens.critical,
        tokens.critical.withValues(alpha: 0.4),
      ),
    };

    Widget content = Row(
      mainAxisSize: widget.isFullWidth ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (widget.isLoading) ...[
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(fg),
            ),
          ),
          const SizedBox(width: ClairSpacing.sm),
        ] else if (widget.icon != null) ...[
          widget.icon!,
          const SizedBox(width: ClairSpacing.sm),
        ],
        Text(
          widget.label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: fg,
          ),
        ),
      ],
    );

    return FocusableActionDetector(
      onShowFocusHighlight: (v) => setState(() => _focused = v),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(
            color: _focused ? tokens.focusRing : border,
            width: _focused ? 2 : 1,
          ),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(ClairRadius.sm),
            onTap: isEnabled ? widget.onPressed : null,
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: ClairSpacing.lg,
                vertical: ClairSpacing.md,
              ),
              child: content,
            ),
          ),
        ),
      ),
    );
  }
}
