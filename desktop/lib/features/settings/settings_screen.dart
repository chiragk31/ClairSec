import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/tokens.dart';
import '../../core/theme/theme_provider.dart';
import '../../providers/projects_provider.dart';
import '../../services/health_service.dart';
import '../shared/page_header.dart';

/// Settings screen with full Appearance section (UI_SYSTEM.md §2.4, PLAN.md Round 1).
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final themeSettings = ref.watch(themeSettingsProvider);
    final themeNotifier = ref.read(themeSettingsProvider.notifier);

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Settings',
            subtitle: 'Application configuration and appearance',
            actions: [
              IconButton(
                onPressed: () => ref.invalidate(backendStatusProvider),
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Re-check connection',
              ),
            ],
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(ClairSpacing.xl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _ConnectionStatusCard(),
                  const SizedBox(height: ClairSpacing.xl),

                  // ── Appearance Section ─────────────────────────────────────
                  _SettingsSection(
                    title: 'Appearance',
                    children: [
                      // Mode: System / Light / Dark
                      _SettingTile(
                        label: 'Theme Mode',
                        description: 'System follows operating system appearance.',
                        trailing: SegmentedButton<ThemeMode>(
                          segments: const [
                            ButtonSegment(value: ThemeMode.system, label: Text('System')),
                            ButtonSegment(value: ThemeMode.light, label: Text('Light')),
                            ButtonSegment(value: ThemeMode.dark, label: Text('Dark')),
                          ],
                          selected: {themeSettings.mode},
                          onSelectionChanged: (s) => themeNotifier.setMode(s.first),
                        ),
                      ),
                      // Preset: 5 preview tiles
                      Padding(
                        padding: const EdgeInsets.all(ClairSpacing.lg),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Color Preset',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                    color: tokens.textPrimary,
                                  ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Presets change neutral tint and accent; severity remains semantic.',
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: tokens.textSecondary,
                                  ),
                            ),
                            const SizedBox(height: ClairSpacing.md),
                            Wrap(
                              spacing: ClairSpacing.md,
                              runSpacing: ClairSpacing.md,
                              children: ThemePreset.values.map((p) {
                                final isSelected = p == themeSettings.preset;
                                final preview = ClairTokens.select(p, tokens.isDark);

                                return InkWell(
                                  onTap: () => themeNotifier.setPreset(p),
                                  borderRadius: BorderRadius.circular(ClairRadius.md),
                                  child: Container(
                                    // Fixed size so every tile lines up; only the selected
                                    // tile gets the accent border (the High Contrast preset's
                                    // own white border used to make it look selected).
                                    width: 150,
                                    height: 78,
                                    padding: const EdgeInsets.all(ClairSpacing.md),
                                    decoration: BoxDecoration(
                                      color: preview.surface,
                                      borderRadius: BorderRadius.circular(ClairRadius.md),
                                      border: Border.all(
                                        color: isSelected ? tokens.accent : tokens.border,
                                        width: isSelected ? 2 : 1,
                                      ),
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          children: [
                                            Container(
                                              width: 14,
                                              height: 14,
                                              decoration: BoxDecoration(
                                                color: preview.accent,
                                                shape: BoxShape.circle,
                                              ),
                                            ),
                                            const SizedBox(width: ClairSpacing.xs),
                                            Container(
                                              width: 14,
                                              height: 14,
                                              decoration: BoxDecoration(
                                                color: preview.surfaceRaised,
                                                shape: BoxShape.circle,
                                                border: Border.all(color: preview.border),
                                              ),
                                            ),
                                            const Spacer(),
                                            if (isSelected)
                                              Icon(Icons.check, size: 14, color: preview.accent),
                                          ],
                                        ),
                                        const SizedBox(height: ClairSpacing.sm),
                                        Text(
                                          p == ThemePreset.values.first
                                              ? (tokens.isDark ? 'Midnight' : 'Daylight')
                                              : p.label,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(
                                            fontSize: ClairTypography.small,
                                            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                                            color: preview.textPrimary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              }).toList(),
                            ),
                          ],
                        ),
                      ),
                      // Density: Comfortable / Compact
                      _SettingTile(
                        label: 'Layout Density',
                        description: 'Compact density reduces list and table row padding.',
                        trailing: SegmentedButton<DensitySetting>(
                          segments: const [
                            ButtonSegment(value: DensitySetting.comfortable, label: Text('Comfortable')),
                            ButtonSegment(value: DensitySetting.compact, label: Text('Compact')),
                          ],
                          selected: {themeSettings.density},
                          onSelectionChanged: (s) => themeNotifier.setDensity(s.first),
                        ),
                      ),
                      // Text size: 90% - 130%
                      Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: ClairSpacing.lg,
                          vertical: ClairSpacing.md,
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'Text Size (${(themeSettings.textScale * 100).round()}%)',
                                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                          color: tokens.textPrimary,
                                        ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    'Scale typography throughout the application.',
                                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                          color: tokens.textSecondary,
                                        ),
                                  ),
                                ],
                              ),
                            ),
                            SizedBox(
                              width: 220,
                              child: Slider(
                                value: themeSettings.textScale,
                                min: 0.9,
                                max: 1.3,
                                divisions: 8,
                                label: '${(themeSettings.textScale * 100).round()}%',
                                onChanged: (v) => themeNotifier.setTextScale(v),
                              ),
                            ),
                          ],
                        ),
                      ),
                      // Reduce motion: System / On / Off
                      _SettingTile(
                        label: 'Reduce Motion',
                        description: 'Disable animations and replace sweeps with static states.',
                        trailing: SegmentedButton<ReduceMotionSetting>(
                          segments: const [
                            ButtonSegment(value: ReduceMotionSetting.system, label: Text('System')),
                            ButtonSegment(value: ReduceMotionSetting.on, label: Text('On')),
                            ButtonSegment(value: ReduceMotionSetting.off, label: Text('Off')),
                          ],
                          selected: {themeSettings.reduceMotion},
                          onSelectionChanged: (s) => themeNotifier.setReduceMotion(s.first),
                        ),
                      ),
                      _SettingTile(
                        label: 'Presenter Mode (F11)',
                        description: 'Bigger text for projectors and hides developer details such as token cost.',
                        trailing: Switch(
                          value: themeSettings.presenterMode,
                          onChanged: (v) => themeNotifier.setPresenterMode(v),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xl),

                  // ── Backend Section ────────────────────────────────────────
                  _SettingsSection(
                    title: 'Backend',
                    children: [
                      _SettingTile(
                        label: 'API Base URL',
                        description: 'Address of the local Python backend process.',
                        trailing: _SettingValue(value: 'http://localhost:8000'),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xl),

                  // ── LLM Provider Section ───────────────────────────────────
                  _SettingsSection(
                    title: 'LLM Provider',
                    children: [
                      _SettingTile(
                        label: 'Provider',
                        description: 'LLM provider used by the autonomous agent pipeline.',
                        trailing: const _SettingValue(value: 'Configured in Environment'),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xl),

                  // ── About Section ──────────────────────────────────────────
                  _SettingsSection(
                    title: 'About',
                    children: [
                      _SettingTile(
                        label: 'Version',
                        description: 'ClairSec Platform version.',
                        trailing: const _SettingValue(value: 'v2.0.0-upgrade'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ConnectionStatusCard extends ConsumerWidget {
  const _ConnectionStatusCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final statusAsync = ref.watch(backendStatusProvider);

    final (icon, color, title, detail) = switch (statusAsync) {
      AsyncData(:final value) => switch (value) {
          BackendStatus.connected => (
              Icons.check_circle_outline,
              tokens.success,
              'Connected',
              'The backend is reachable and this client is authenticated.',
            ),
          BackendStatus.tokenMissing => (
              Icons.key_off_outlined,
              tokens.warning,
              'Auth token missing',
              'The backend is running but no token file was found. Restart backend.',
            ),
          BackendStatus.disconnected => (
              Icons.cloud_off_outlined,
              tokens.danger,
              'Not connected',
              'No response from backend. Start it with: uvicorn app.main:app',
            ),
        },
      AsyncError() => (
          Icons.error_outline,
          tokens.danger,
          'Connection check failed',
          'Could not determine backend status.',
        ),
      _ => (
          Icons.hourglass_empty,
          tokens.textSecondary,
          'Checking…',
          'Probing the backend health endpoint.',
        ),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: color.withValues(alpha: tokens.isDark ? 0.12 : 0.08),
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: color),
          const SizedBox(width: ClairSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: color),
                ),
                const SizedBox(height: 4),
                Text(
                  detail,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(color: tokens.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title.toUpperCase(),
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: tokens.textSecondary,
                letterSpacing: 1.0,
                fontWeight: FontWeight.w600,
              ),
        ),
        const SizedBox(height: ClairSpacing.sm),
        Container(
          decoration: BoxDecoration(
            color: tokens.surface,
            borderRadius: BorderRadius.circular(ClairRadius.md),
            border: Border.all(color: tokens.border),
          ),
          child: Column(
            children: children
                .expand((child) => [child, Divider(height: 1, color: tokens.border)])
                .toList()
              ..removeLast(),
          ),
        ),
      ],
    );
  }
}

class _SettingTile extends StatelessWidget {
  const _SettingTile({
    required this.label,
    required this.description,
    this.trailing,
  });

  final String label;
  final String description;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: ClairSpacing.lg,
        vertical: ClairSpacing.md,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final isNarrow = constraints.maxWidth < 450;
          if (isNarrow) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: tokens.textPrimary,
                      ),
                ),
                const SizedBox(height: 3),
                Text(
                  description,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: tokens.textSecondary,
                      ),
                ),
                if (trailing != null) ...[
                  const SizedBox(height: ClairSpacing.md),
                  trailing!,
                ],
              ],
            );
          }

          return Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: tokens.textPrimary,
                          ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      description,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: tokens.textSecondary,
                          ),
                    ),
                  ],
                ),
              ),
              ?trailing,
            ],
          );
        },
      ),
    );
  }
}

class _SettingValue extends StatelessWidget {
  const _SettingValue({required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return Text(
      value,
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: tokens.textSecondary,
          ),
    );
  }
}
