import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../providers/findings_provider.dart';
import '../../providers/scans_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/finding_list_tile.dart';

class VulnerabilitiesScreen extends ConsumerWidget {
  const VulnerabilitiesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Vulnerabilities',
            subtitle: 'Confirmed findings across all scans',
            actions: [
              IconButton(
                onPressed: () {
                  ref.invalidate(scansProvider);
                  ref.invalidate(allFindingsProvider);
                },
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          const Expanded(child: _VulnerabilitiesContent()),
        ],
      ),
    );
  }
}

class _VulnerabilitiesContent extends ConsumerStatefulWidget {
  const _VulnerabilitiesContent();

  @override
  ConsumerState<_VulnerabilitiesContent> createState() =>
      _VulnerabilitiesContentState();
}

class _VulnerabilitiesContentState
    extends ConsumerState<_VulnerabilitiesContent> {
  /// null = show everything. Otherwise restrict to a single severity band.
  FindingSeverity? _severityFilter;

  /// Hide findings the Evaluator did not confirm. On by default: a rejected
  /// candidate is not a vulnerability, and showing it alongside confirmed ones
  /// would misrepresent the result.
  bool _confirmedOnly = true;

  @override
  Widget build(BuildContext context) {
    final all = ref.watch(findingsProvider);

    final visible = all.where((f) {
      if (_confirmedOnly && f.status != FindingStatus.confirmed) return false;
      if (_severityFilter != null && f.severity != _severityFilter) return false;
      return true;
    }).toList();

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Severity legend row — paired icon + label per DESIGN.md rule
          _SeverityLegend(),
          const SizedBox(height: 16),
          _FilterBar(
            all: all,
            selected: _severityFilter,
            confirmedOnly: _confirmedOnly,
            onSeverityChanged: (s) => setState(() => _severityFilter = s),
            onConfirmedOnlyChanged: (v) => setState(() => _confirmedOnly = v),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: visible.isEmpty
                ? EmptyState(
                    icon: Icons.bug_report_outlined,
                    title: all.isEmpty
                        ? 'No vulnerabilities found yet'
                        : 'Nothing matches this filter',
                    description: all.isEmpty
                        ? 'Confirmed findings from completed scans will appear here. '
                            'Each entry shows severity, confidence, endpoint, '
                            'evidence, and fix status.'
                        : 'No findings match the current filter. Clear it to see '
                            'all ${all.length} recorded findings.',
                  )
                : ListView.separated(
                    itemCount: visible.length,
                    separatorBuilder: (context, i) => const SizedBox(height: 12),
                    itemBuilder: (context, i) {
                      final f = visible[i];
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

/// Severity filter chips plus a confirmed-only toggle. Each chip shows the
/// count for that band so an empty band is visible rather than silently absent.
class _FilterBar extends StatelessWidget {
  final List<Finding> all;
  final FindingSeverity? selected;
  final bool confirmedOnly;
  final ValueChanged<FindingSeverity?> onSeverityChanged;
  final ValueChanged<bool> onConfirmedOnlyChanged;

  const _FilterBar({
    required this.all,
    required this.selected,
    required this.confirmedOnly,
    required this.onSeverityChanged,
    required this.onConfirmedOnlyChanged,
  });

  @override
  Widget build(BuildContext context) {
    final pool = confirmedOnly
        ? all.where((f) => f.status == FindingStatus.confirmed).toList()
        : all;

    int countFor(FindingSeverity s) =>
        pool.where((f) => f.severity == s).length;

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        _FilterChip(
          label: 'All (${pool.length})',
          active: selected == null,
          color: AppColors.accent,
          onTap: () => onSeverityChanged(null),
        ),
        for (final s in FindingSeverity.values)
          if (countFor(s) > 0)
            _FilterChip(
              label: '${s.label} (${countFor(s)})',
              active: selected == s,
              color: s.color,
              icon: s.icon,
              onTap: () => onSeverityChanged(selected == s ? null : s),
            ),
        const SizedBox(width: 8),
        _FilterChip(
          label: 'Confirmed only',
          active: confirmedOnly,
          color: SeverityColors.success,
          icon: confirmedOnly ? Icons.check_box_outlined : Icons.check_box_outline_blank,
          onTap: () => onConfirmedOnlyChanged(!confirmedOnly),
        ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool active;
  final Color color;
  final IconData? icon;
  final VoidCallback onTap;

  const _FilterChip({
    required this.label,
    required this.active,
    required this.color,
    required this.onTap,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.16) : AppColors.surface,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: active ? color.withValues(alpha: 0.55) : AppColors.border,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 12, color: active ? color : AppColors.textSecondary),
              const SizedBox(width: 5),
            ],
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: active ? color : AppColors.textSecondary,
                    fontWeight: active ? FontWeight.w600 : FontWeight.w500,
                  ),
            ),
          ],
        ),
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
