import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

/// Base badge component (UI_SYSTEM.md §7).
/// Always pairs an icon with a text label. Never colour alone.
class CsBadge extends StatelessWidget {
  const CsBadge({
    super.key,
    required this.label,
    required this.icon,
    required this.color,
    this.backgroundColor,
    this.borderColor,
    this.isSmall = false,
  });

  final String label;
  final IconData icon;
  final Color color;
  final Color? backgroundColor;
  final Color? borderColor;
  final bool isSmall;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final bg = backgroundColor ?? color.withValues(alpha: tokens.isDark ? 0.15 : 0.12);
    final border = borderColor ?? color.withValues(alpha: tokens.isDark ? 0.35 : 0.25);

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: isSmall ? ClairSpacing.sm : ClairSpacing.md,
        vertical: isSmall ? 2.0 : ClairSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(ClairRadius.pill),
        border: Border.all(color: border, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: isSmall ? 12 : 14, color: color),
          const SizedBox(width: ClairSpacing.xs),
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontSize: isSmall ? 10.5 : 11.5,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.4,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

/// Severity badge with semantic icon & color (UI_SYSTEM.md §2.2).
class SeverityBadge extends StatelessWidget {
  const SeverityBadge({
    super.key,
    required this.severity,
    this.isSmall = false,
  });

  final String severity; // critical, high, medium, low, info
  final bool isSmall;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final s = severity.toLowerCase();

    final (color, icon, label) = switch (s) {
      'critical' => (tokens.critical, Icons.dangerous_outlined, 'Critical'),
      'high' => (tokens.high, Icons.error_outline, 'High'),
      'medium' => (tokens.medium, Icons.warning_amber_outlined, 'Medium'),
      'low' => (tokens.low, Icons.info_outline, 'Low'),
      _ => (tokens.info, Icons.help_outline, s.isNotEmpty ? s : 'Info'),
    };

    return CsBadge(
      label: label,
      icon: icon,
      color: color,
      isSmall: isSmall,
    );
  }
}

/// Status badge with semantic icon & color (UI_SYSTEM.md §2.3).
class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.status,
    this.labelOverride,
    this.isSmall = false,
  });

  final String status; // success, warning, danger, running, neutral
  final String? labelOverride;
  final bool isSmall;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final s = status.toLowerCase();

    final (color, icon, defaultLabel) = switch (s) {
      'success' || 'confirmed' || 'verified' || 'fixed' || 'ready' => (
        tokens.success,
        Icons.check_circle_outline,
        'Success'
      ),
      'warning' || 'inconclusive' || 'degraded' => (
        tokens.warning,
        Icons.warning_amber_outlined,
        'Warning'
      ),
      'danger' || 'failed' || 'regressed' || 'error' => (
        tokens.danger,
        Icons.cancel_outlined,
        'Failed'
      ),
      'running' || 'building' || 'starting' => (
        tokens.running,
        Icons.sync,
        'Running'
      ),
      _ => (tokens.neutral, Icons.radio_button_unchecked, 'Neutral'),
    };

    return CsBadge(
      label: labelOverride ?? defaultLabel,
      icon: icon,
      color: color,
      isSmall: isSmall,
    );
  }
}

/// Experience Mode badge for top bar & banners (UI_SYSTEM.md §6, FEATURES.md F4).
class ModeBadge extends StatelessWidget {
  const ModeBadge({
    super.key,
    required this.modeId,
    this.label,
    this.reason,
    this.isSmall = false,
  });

  final String modeId; // live, live_local_ai, live_offline_ai, demo, recorded
  final String? label;
  final String? reason;
  final bool isSmall;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    final (color, icon, defaultLabel, defaultReason) = switch (modeId) {
      'live' => (
          tokens.success,
          Icons.bolt,
          'LIVE',
          'Docker isolation is ready and cloud LLM provider is configured.',
        ),
      'live_local_ai' => (
          tokens.accent,
          Icons.memory,
          'LIVE · LOCAL AI',
          'Docker isolation is ready and local Ollama model is available.',
        ),
      'live_offline_ai' => (
          tokens.warning,
          Icons.cloud_off,
          'LIVE · OFFLINE AI',
          'Docker isolation is ready with local offline mock/replay intelligence.',
        ),
      'demo' => (
          tokens.info,
          Icons.science_outlined,
          'DEMO APP',
          'Docker is unavailable. Scans run against bundled demo apps via trusted fixture isolation.',
        ),
      'recorded' => (
          tokens.neutral,
          Icons.play_circle_outline,
          'RECORDED RUN',
          'Playing back a recorded scan bundle captured from a previous dynamic run.',
        ),
      _ => (
          tokens.neutral,
          Icons.circle,
          modeId.toUpperCase(),
          'Active experience mode: ${modeId.toUpperCase()}',
        ),
    };

    return Tooltip(
      message: reason ?? defaultReason,
      child: CsBadge(
        label: label ?? defaultLabel,
        icon: icon,
        color: color,
        isSmall: isSmall,
      ),
    );
  }
}

/// Shown while the backend runs on its in-memory database fallback.
class TemporaryStorageBadge extends StatelessWidget {
  const TemporaryStorageBadge({super.key});

  static const label = 'TEMPORARY STORAGE';

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'MongoDB is not running, so results are kept in memory only and '
          'disappear when the app closes. Start the MongoDB service and restart '
          'the backend to keep them.',
      child: CsBadge(
        label: label,
        icon: Icons.memory,
        color: context.tokens.warning,
        isSmall: true,
      ),
    );
  }
}
