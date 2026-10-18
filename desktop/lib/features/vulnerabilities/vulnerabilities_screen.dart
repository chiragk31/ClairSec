import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/tokens.dart';
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
    final tokens = context.tokens;

    return Scaffold(
      backgroundColor: tokens.bg,
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

  /// Active lane: 0 = Confirmed vulnerabilities (feeds score), 1 = Candidates & suspicions.
  int _selectedLane = 0;

  @override
  Widget build(BuildContext context) {
    final all = ref.watch(findingsProvider);
    final tokens = context.tokens;

    final confirmed = all.where((f) => f.isConfirmed).toList();
    final candidates = all.where((f) => !f.isConfirmed).toList();

    final activePool = _selectedLane == 0 ? confirmed : candidates;

    final visible = activePool.where((f) {
      if (_severityFilter != null && f.severity != _severityFilter) return false;
      return true;
    }).toList();

    return Padding(
      padding: const EdgeInsets.all(ClairSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Severity legend row — paired icon + label per DESIGN.md rule
          const _SeverityLegend(),
          const SizedBox(height: ClairSpacing.lg),
          // Two-lane selector (FEATURES.md F7: Confirmed vs Candidates & suspicions)
          Wrap(
            spacing: ClairSpacing.md,
            runSpacing: ClairSpacing.sm,
            children: [
              _LaneButton(
                label: 'Confirmed vulnerabilities (${confirmed.length})',
                icon: Icons.gpp_bad_outlined,
                active: _selectedLane == 0,
                color: tokens.critical,
                onTap: () => setState(() {
                  _selectedLane = 0;
                  _severityFilter = null;
                }),
              ),
              _LaneButton(
                label: 'Candidates & suspicions (${candidates.length})',
                icon: Icons.hourglass_empty,
                active: _selectedLane == 1,
                color: tokens.accent,
                onTap: () => setState(() {
                  _selectedLane = 1;
                  _severityFilter = null;
                }),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.sm),
          Text(
            _selectedLane == 0
                ? 'Demonstrated exploit proofs verified by deterministic oracles. These feed your posture score.'
                : 'Reconnaissance candidates and unconfirmed suspicions. These do not impact your posture score.',
            style: TextStyle(
              fontSize: ClairTypography.caption,
              color: tokens.textMuted,
            ),
          ),
          const SizedBox(height: ClairSpacing.md),
          _FilterBar(
            pool: activePool,
            selected: _severityFilter,
            onSeverityChanged: (s) => setState(() => _severityFilter = s),
          ),
          const SizedBox(height: ClairSpacing.lg),
          Expanded(
            child: visible.isEmpty
                ? EmptyState(
                    icon: _selectedLane == 0
                        ? Icons.bug_report_outlined
                        : Icons.check_circle_outline,
                    title: all.isEmpty
                        ? 'No vulnerabilities found yet'
                        : (_selectedLane == 0 && confirmed.isEmpty
                            ? 'No confirmed vulnerabilities'
                            : 'Nothing matches this filter'),
                    description: all.isEmpty
                        ? 'Confirmed findings from completed scans will appear here. '
                            'Each entry shows severity, confidence, endpoint, '
                            'evidence, and fix status.'
                        : (_selectedLane == 0 && confirmed.isEmpty
                            ? 'No exploits were runtime-confirmed by oracles. Switch to Candidates & suspicions to see unconfirmed findings.'
                            : 'No findings match the current filter. Clear it to see '
                                'all ${activePool.length} recorded findings in this lane.'),
                  )
                : ListView.separated(
                    itemCount: visible.length,
                    separatorBuilder: (context, i) => const SizedBox(height: ClairSpacing.md),
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

class _LaneButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  const _LaneButton({
    required this.label,
    required this.icon,
    required this.active,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(ClairRadius.sm),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.md,
          vertical: ClairSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.15) : tokens.surface,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(
            color: active ? color.withValues(alpha: 0.6) : tokens.border,
            width: active ? 1.5 : 1.0,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 15, color: active ? color : tokens.textSecondary),
            const SizedBox(width: ClairSpacing.sm),
            Text(
              label,
              style: TextStyle(
                fontSize: ClairTypography.body,
                fontWeight: active ? FontWeight.w600 : FontWeight.w500,
                color: active ? tokens.textPrimary : tokens.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Severity filter chips. Each chip shows the count for that band.
class _FilterBar extends StatelessWidget {
  final List<Finding> pool;
  final FindingSeverity? selected;
  final ValueChanged<FindingSeverity?> onSeverityChanged;

  const _FilterBar({
    required this.pool,
    required this.selected,
    required this.onSeverityChanged,
  });

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    int countFor(FindingSeverity s) =>
        pool.where((f) => f.severity == s).length;

    return Wrap(
      spacing: ClairSpacing.sm,
      runSpacing: ClairSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        _FilterChip(
          label: 'All (${pool.length})',
          active: selected == null,
          color: tokens.accent,
          onTap: () => onSeverityChanged(null),
        ),
        for (final s in FindingSeverity.values)
          if (countFor(s) > 0)
            _FilterChip(
              label: '${s.label} (${countFor(s)})',
              active: selected == s,
              color: s.color(tokens),
              icon: s.icon,
              onTap: () => onSeverityChanged(selected == s ? null : s),
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
    final tokens = context.tokens;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(ClairRadius.sm),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.md - 2,
          vertical: ClairSpacing.xs + 2,
        ),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.16) : tokens.surface,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(
            color: active ? color.withValues(alpha: 0.55) : tokens.border,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 12, color: active ? color : tokens.textSecondary),
              const SizedBox(width: 5),
            ],
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: active ? color : tokens.textSecondary,
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
  const _SeverityLegend();

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final items = [
      _SeverityItem(label: 'Critical', color: tokens.critical, icon: Icons.cancel_outlined),
      _SeverityItem(label: 'High', color: tokens.high, icon: Icons.error_outline),
      _SeverityItem(label: 'Medium', color: tokens.medium, icon: Icons.warning_amber_outlined),
      _SeverityItem(label: 'Low', color: tokens.low, icon: Icons.info_outline),
      _SeverityItem(label: 'Informational', color: tokens.info, icon: Icons.circle_outlined),
    ];

    return Wrap(
      spacing: ClairSpacing.md,
      runSpacing: ClairSpacing.sm,
      children: [
        Text(
          'Severity:',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: tokens.textMuted,
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
        const SizedBox(width: ClairSpacing.xs),
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color),
        ),
      ],
    );
  }
}
