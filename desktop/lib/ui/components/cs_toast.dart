import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

enum ToastType { success, info, warning, danger }

/// Toast notification component (UI_SYSTEM.md §7).
class CsToast extends StatelessWidget {
  const CsToast({
    super.key,
    required this.message,
    this.type = ToastType.info,
    this.actionLabel,
    this.onAction,
  });

  final String message;
  final ToastType type;
  final String? actionLabel;
  final VoidCallback? onAction;

  static void show(
    BuildContext context, {
    required String message,
    ToastType type = ToastType.info,
    String? actionLabel,
    VoidCallback? onAction,
    Duration duration = const Duration(seconds: 4),
  }) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        behavior: SnackBarBehavior.floating,
        backgroundColor: Colors.transparent,
        elevation: 0,
        margin: const EdgeInsets.all(ClairSpacing.lg),
        duration: duration,
        content: CsToast(
          message: message,
          type: type,
          actionLabel: actionLabel,
          onAction: onAction,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    final (color, icon) = switch (type) {
      ToastType.success => (tokens.success, Icons.check_circle_outline),
      ToastType.warning => (tokens.warning, Icons.warning_amber_outlined),
      ToastType.danger => (tokens.danger, Icons.error_outline),
      ToastType.info => (tokens.accent, Icons.info_outline),
    };

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: ClairSpacing.lg,
        vertical: ClairSpacing.md,
      ),
      decoration: BoxDecoration(
        color: tokens.surfaceRaised,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: ClairSpacing.md),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: tokens.textPrimary,
              ),
            ),
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(width: ClairSpacing.md),
            TextButton(
              onPressed: onAction,
              style: TextButton.styleFrom(
                foregroundColor: color,
                padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.sm),
              ),
              child: Text(
                actionLabel!,
                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
