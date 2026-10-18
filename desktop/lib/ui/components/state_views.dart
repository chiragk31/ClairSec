import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';
import 'cs_button.dart';

/// Empty state view with illustration icon, explanation, and primary action (UI_SYSTEM.md §7).
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String message;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(ClairSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(ClairSpacing.lg),
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                shape: BoxShape.circle,
                border: Border.all(color: tokens.border),
              ),
              child: Icon(icon, size: 36, color: tokens.textSecondary),
            ),
            const SizedBox(height: ClairSpacing.lg),
            Text(
              title,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: tokens.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: ClairSpacing.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: Text(
                message,
                style: TextStyle(
                  fontSize: 13,
                  color: tokens.textSecondary,
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: ClairSpacing.lg),
              CsButton(
                label: actionLabel!,
                onPressed: onAction,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Error state view with alert icon, explanation, and retry action (UI_SYSTEM.md §7).
class ErrorState extends StatelessWidget {
  const ErrorState({
    super.key,
    this.title = 'Something went wrong',
    required this.message,
    this.onRetry,
    this.retryLabel = 'Retry',
  });

  final String title;
  final String message;
  final VoidCallback? onRetry;
  final String retryLabel;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(ClairSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(ClairSpacing.lg),
              decoration: BoxDecoration(
                color: tokens.critical.withValues(alpha: 0.15),
                shape: BoxShape.circle,
                border: Border.all(color: tokens.critical.withValues(alpha: 0.3)),
              ),
              child: Icon(Icons.error_outline, size: 36, color: tokens.critical),
            ),
            const SizedBox(height: ClairSpacing.lg),
            Text(
              title,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: tokens.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: ClairSpacing.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Text(
                message,
                style: TextStyle(
                  fontSize: 13,
                  color: tokens.textSecondary,
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: ClairSpacing.lg),
              CsButton(
                label: retryLabel,
                icon: const Icon(Icons.refresh, size: 16),
                onPressed: onRetry,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Offline state view when backend / container is unreachable (UI_SYSTEM.md §7).
class OfflineState extends StatelessWidget {
  const OfflineState({
    super.key,
    this.serviceName = 'Backend',
    required this.message,
    this.onReconnect,
  });

  final String serviceName;
  final String message;
  final VoidCallback? onReconnect;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(ClairSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(ClairSpacing.lg),
              decoration: BoxDecoration(
                color: tokens.warning.withValues(alpha: 0.15),
                shape: BoxShape.circle,
                border: Border.all(color: tokens.warning.withValues(alpha: 0.3)),
              ),
              child: Icon(Icons.cloud_off, size: 36, color: tokens.warning),
            ),
            const SizedBox(height: ClairSpacing.lg),
            Text(
              '$serviceName Offline',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: tokens.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: ClairSpacing.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Text(
                message,
                style: TextStyle(
                  fontSize: 13,
                  color: tokens.textSecondary,
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),
            ),
            if (onReconnect != null) ...[
              const SizedBox(height: ClairSpacing.lg),
              CsButton(
                label: 'Re-check Connection',
                icon: const Icon(Icons.refresh, size: 16),
                onPressed: onReconnect,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
