import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../providers/findings_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/status_badges.dart';

/// Full finding detail (DESIGN.md §7): explanation, impact, evidence,
/// source location, reproduction summary, fix status, verification status.
class FindingDetailScreen extends ConsumerWidget {
  final String findingId;

  const FindingDetailScreen({super.key, required this.findingId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final finding = ref.watch(findingByIdProvider(findingId));

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: finding?.title ?? 'Finding',
            subtitle: findingId,
            actions: [
              if (finding != null &&
                  finding.remediationStatus != RemediationStatus.notStarted)
                FilledButton.icon(
                  onPressed: () => context.go('/fixes/$findingId'),
                  icon: const Icon(Icons.build_outlined, size: 15),
                  label: const Text('View Fix'),
                ),
            ],
          ),
          Expanded(
            child: finding == null
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.search_off_outlined,
                      title: 'Finding not found',
                      description:
                          'This finding does not exist, or its scan has not '
                          'been loaded.',
                    ),
                  )
                : _FindingDetailContent(finding: finding),
          ),
        ],
      ),
    );
  }
}

class _FindingDetailContent extends StatelessWidget {
  final Finding finding;
  const _FindingDetailContent({required this.finding});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              SeverityPill(severity: finding.severity),
              FindingStatusBadge(status: finding.status),
              RuntimeConfirmationBadge(runtimeConfirmed: finding.runtimeConfirmed),
              RemediationStatusBadge(status: finding.remediationStatus),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${finding.category} · ${finding.cwe} · ${finding.confidence.label}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 24),
          _Section(
            title: 'Description',
            child: Text(finding.description, style: Theme.of(context).textTheme.bodyLarge),
          ),
          _Section(
            title: 'Impact',
            child: Text(finding.impact, style: Theme.of(context).textTheme.bodyLarge),
          ),
          if (finding.statusReason != null)
            _Section(
              title: 'Evaluator reasoning',
              child: Text(finding.statusReason!, style: Theme.of(context).textTheme.bodyLarge),
            ),
          if (finding.evidenceSummary != null)
            _Section(
              title: 'Evidence',
              mono: true,
              child: Text(
                finding.evidenceSummary!,
                style: AppTheme.monoStyle(fontSize: 12.5),
              ),
            ),
          if (finding.reproductionSummary != null)
            _Section(
              title: 'Reproduction',
              child: Text(finding.reproductionSummary!, style: Theme.of(context).textTheme.bodyLarge),
            ),
          if (finding.sourceLocations.isNotEmpty)
            _Section(
              title: 'Source location',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final loc in finding.sourceLocations)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(
                        loc.display,
                        style: AppTheme.monoStyle(fontSize: 12.5, color: AppColors.accent),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  final bool mono;

  const _Section({required this.title, required this.child, this.mono = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: AppColors.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: child,
          ),
        ],
      ),
    );
  }
}
