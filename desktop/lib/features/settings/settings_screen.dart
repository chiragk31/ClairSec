import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../shared/page_header.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const PageHeader(
            title: 'Settings',
            subtitle: 'Application configuration',
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SettingsSection(
                    title: 'Backend',
                    children: [
                      _SettingTile(
                        label: 'API Base URL',
                        description:
                            'Address of the local Python backend process.',
                        trailing: _SettingValue(value: 'http://localhost:8000'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'LLM Provider',
                    children: [
                      _SettingTile(
                        label: 'Provider',
                        description:
                            'LLM provider used by the agent pipeline. '
                            'Configuration available in Phase 4.',
                        trailing: const _SettingValue(value: 'Not configured'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'Isolation',
                    children: [
                      _SettingTile(
                        label: 'Docker socket',
                        description:
                            'Docker is required to run imported FastAPI projects '
                            'in isolation. Configuration available in Phase 3.',
                        trailing: const _SettingValue(value: 'Not configured'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'About',
                    children: [
                      _SettingTile(
                        label: 'Version',
                        description: 'Application version.',
                        trailing: const _SettingValue(value: '0.1.0 (Phase 1)'),
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

class _SettingsSection extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _SettingsSection({required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title.toUpperCase(),
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: AppColors.textDisabled,
                letterSpacing: 1.0,
              ),
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            children: children
                .expand((child) => [child, const Divider(height: 1)])
                .toList()
              ..removeLast(), // remove trailing divider
          ),
        ),
      ],
    );
  }
}

class _SettingTile extends StatelessWidget {
  final String label;
  final String description;
  final Widget? trailing;

  const _SettingTile({
    required this.label,
    required this.description,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(description, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

class _SettingValue extends StatelessWidget {
  final String value;

  const _SettingValue({required this.value});

  @override
  Widget build(BuildContext context) {
    return Text(
      value,
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: AppColors.textDisabled,
          ),
    );
  }
}
