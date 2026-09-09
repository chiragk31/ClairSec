import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../providers/findings_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/finding_list_tile.dart';

class VulnerabilitiesScreen extends StatelessWidget {
  const VulnerabilitiesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PageHeader(
            title: 'Vulnerabilities',
            subtitle: 'Confirmed findings across all scans',
          ),
          Expanded(child: _VulnerabilitiesContent()),
        ],
      ),
    );
  }
}

class _VulnerabilitiesContent extends ConsumerWidget {
  const _VulnerabilitiesContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final findings = ref.watch(findingsProvider);

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Severity legend row — paired icon + label per DESIGN.md rule
          _SeverityLegend(),
          const SizedBox(height: 24),
          Expanded(
            child: findings.isEmpty
                ? const EmptyState(
                    icon: Icons.bug_report_outlined,
                    title: 'No vulnerabilities found yet',
                    description:
                        'Confirmed findings from completed scans will appear here. '
                        'Each entry shows severity, confidence, endpoint, '
                        'evidence, and fix status.',
                  )
                : ListView.separated(
                    itemCount: findings.length,
                    separatorBuilder: (context, i) => const SizedBox(height: 12),
                    itemBuilder: (context, i) {
                      final f = findings[i];
                      return FindingListTile(
                        finding: f,
                        onTap: () => context.go('/vulnerabilities/${f.id}'),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _SeverityLegend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    const items = [
      _SeverityItem(label: 'Critical', color: SeverityColors.critical, icon: Icons.cancel_outlined),
      _SeverityItem(label: 'High', color: SeverityColors.high, icon: Icons.error_outline),
      _SeverityItem(label: 'Medium', color: SeverityColors.medium, icon: Icons.warning_amber_outlined),
      _SeverityItem(label: 'Low', color: SeverityColors.low, icon: Icons.info_outline),
      _SeverityItem(label: 'Informational', color: SeverityColors.informational, icon: Icons.circle_outlined),
    ];

    return Wrap(
      spacing: 12,
      runSpacing: 8,
      children: [
        Text(
          'Severity:',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: AppColors.textDisabled,
              ),
        ),
        ...items,
      ],
    );
  }
}

class _SeverityItem extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;

  const _SeverityItem({
    required this.label,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 4),
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color),
        ),
      ],
    );
  }
}
