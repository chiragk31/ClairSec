import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../core/theme/tokens.dart';
import '../../models/finding.dart';
import '../../providers/findings_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/status_badges.dart';
import 'widgets/replay_panel.dart';
import '../../core/glossary/glossary.dart';
import '../../ui/components/provenance_strip.dart';

/// Full finding detail (DESIGN.md §7): explanation, impact, evidence,
/// source location, reproduction summary, fix status, verification status.
class FindingDetailScreen extends ConsumerWidget {
  final String findingId;

  const FindingDetailScreen({super.key, required this.findingId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final finding = ref.watch(findingByIdProvider(findingId));

    return Scaffold(
      backgroundColor: tokens.bg,
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
                    padding: EdgeInsets.all(ClairSpacing.xl),
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
    final tokens = context.tokens;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(ClairSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: ClairSpacing.sm,
            runSpacing: ClairSpacing.sm,
            children: [
              SeverityPill(severity: finding.severity),
              FindingStatusBadge(status: finding.status),
              RuntimeConfirmationBadge.forFinding(finding),
              RemediationStatusBadge(status: finding.remediationStatus),
            ],
          ),
          const SizedBox(height: ClairSpacing.sm),
          Text(
            '${finding.category} · ${finding.cwe} · ${finding.confidence.label}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (kGlossaryEntries[finding.category] != null) ...[
            const SizedBox(height: ClairSpacing.md),
            Container(
              width: double.infinity,
              padding: ClairInsets.allMd,
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                borderRadius: BorderRadius.circular(ClairRadius.sm),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.lightbulb_outline, size: 18, color: tokens.accent),
                  const SizedBox(width: ClairSpacing.sm),
                  Expanded(
                    child: Text(
                      'In plain words: ${kGlossaryEntries[finding.category]!.plain}',
                      style: TextStyle(color: tokens.textPrimary),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: ClairSpacing.xl),
          _Section(
            title: 'Why you can trust this finding',
            child: _ProvenanceView(findingId: finding.id),
          ),
          if (finding.status == FindingStatus.confirmed)
            _Section(
              title: 'Replay the attack: live proof',
              child: ReplayPanel(findingId: finding.id, category: finding.category),
            ),
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
                style: AppTheme.monoStyle(fontSize: ClairTypography.code),
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
                      padding: const EdgeInsets.only(bottom: ClairSpacing.xs),
                      child: Text(
                        loc.display,
                        style: AppTheme.monoStyle(fontSize: ClairTypography.code, color: tokens.accent),
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
    final tokens = context.tokens;

    return Padding(
      padding: const EdgeInsets.only(bottom: ClairSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: tokens.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: ClairSpacing.sm),
          Container(
            width: double.infinity,
            padding: ClairInsets.relaxedCard,
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: BorderRadius.circular(ClairRadius.md),
              border: Border.all(color: tokens.border),
            ),
            child: child,
          ),
        ],
      ),
    );
  }
}


/// Evidence chain of custody (FEATURES.md F7) — who did what, from stored records.
class _ProvenanceView extends ConsumerWidget {
  const _ProvenanceView({required this.findingId});

  final String findingId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final prov = ref.watch(findingProvenanceProvider(findingId));
    return prov.when(
      loading: () => const LinearProgressIndicator(minHeight: 2),
      error: (e, _) => Text(
        'Evidence chain unavailable: $e',
        style: TextStyle(color: tokens.textSecondary),
      ),
      data: (p) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            p.badge,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: p.lane == 'confirmed' ? tokens.success : tokens.warning,
            ),
          ),
          const SizedBox(height: ClairSpacing.xs),
          Text(
            'Steps marked AI proposal were suggested by the model; every verdict '
            'after that was decided by platform code, never by the AI.',
            style: TextStyle(color: tokens.textSecondary),
          ),
          const SizedBox(height: ClairSpacing.sm),
          ProvenanceStrip(steps: p.steps),
        ],
      ),
    );
  }
}
