import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/finding.dart';
import '../../models/patch.dart';
import '../../providers/findings_provider.dart';
import '../../providers/patches_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import '../vulnerabilities/widgets/status_badges.dart';
import 'widgets/diff_viewer.dart';
import 'widgets/verification_panel.dart';

/// Fix Review — DESIGN.md §8 split layout:
///
///   ┌───────────────────┬──────────────────────┐
///   │ Vulnerability     │ Proposed Fix         │
///   │ Explanation       │ Source diff          │
///   │ Evidence          │                      │
///   └───────────────────┴──────────────────────┘
///
/// The diff is shown verbatim so the user can see exactly what changed before
/// trusting the fix.
class FixReviewScreen extends ConsumerWidget {
  final String findingId;

  const FixReviewScreen({super.key, required this.findingId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final finding = ref.watch(findingByIdProvider(findingId));
    final patch = ref.watch(patchForFindingProvider(findingId));

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Fix Review',
            subtitle: finding?.title ?? findingId,
          ),
          Expanded(
            child: finding == null
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.search_off_outlined,
                      title: 'Finding not found',
                      description: 'This finding could not be loaded.',
                    ),
                  )
                : _SplitLayout(finding: finding, patch: patch),
          ),
        ],
      ),
    );
  }
}

class _SplitLayout extends StatelessWidget {
  final Finding finding;
  final Patch? patch;

  const _SplitLayout({required this.finding, this.patch});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Stack vertically on narrow windows so neither pane gets crushed.
        final isWide = constraints.maxWidth >= 900;
        final left = _VulnerabilityPane(finding: finding);
        final right = _FixPane(patch: patch, finding: finding);

        if (!isWide) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [left, const SizedBox(height: 24), right],
            ),
          );
        }

        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 4,
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 24, 12, 24),
                child: left,
              ),
            ),
            const VerticalDivider(width: 1),
            Expanded(
              flex: 6,
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(12, 24, 24, 24),
                child: right,
              ),
            ),
          ],
        );
      },
    );
  }
}

class _VulnerabilityPane extends StatelessWidget {
  final Finding finding;
  const _VulnerabilityPane({required this.finding});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _PaneTitle(icon: Icons.gpp_bad_outlined, text: 'Vulnerability'),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            SeverityPill(severity: finding.severity),
            FindingStatusBadge(status: finding.status),
            RuntimeConfirmationBadge(runtimeConfirmed: finding.runtimeConfirmed),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          '${finding.method}  ${finding.routeTemplate}',
          style: AppTheme.monoStyle(fontSize: 12, color: AppColors.accent),
        ),
        const SizedBox(height: 4),
        Text(
          '${finding.category} · ${finding.cwe}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 20),
        _Block(title: 'What it is', body: finding.description),
        _Block(title: 'Impact', body: finding.impact),
        if (finding.statusReason != null)
          _Block(title: 'Why it was confirmed', body: finding.statusReason!),
        if (finding.reproductionSummary != null)
          _Block(title: 'Reproduction', body: finding.reproductionSummary!, mono: true),
      ],
    );
  }
}

class _FixPane extends StatelessWidget {
  final Patch? patch;
  final Finding finding;

  const _FixPane({required this.patch, required this.finding});

  @override
  Widget build(BuildContext context) {
    final p = patch;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            _PaneTitle(icon: Icons.build_outlined, text: 'Proposed Fix'),
            const Spacer(),
            RemediationStatusBadge(status: finding.remediationStatus),
          ],
        ),
        const SizedBox(height: 12),
        if (p == null)
          const EmptyState(
            icon: Icons.hourglass_empty,
            title: 'No patch generated',
            description:
                'The Fixer did not produce a patch for this finding, or the '
                'scan has not reached the fix stage yet.',
          )
        else ...[
          Row(
            children: [
              DiffStatsChip(stats: p.diffStats),
              const Spacer(),
              _ValidationBadges(validation: p.validation),
            ],
          ),
          const SizedBox(height: 16),
          if (p.verification != null) ...[
            VerificationPanel(proof: p.verification!),
            const SizedBox(height: 20),
          ],
          if (p.rootCause.isNotEmpty) _Block(title: 'Root cause', body: p.rootCause),
          if (p.rationale.isNotEmpty) _Block(title: 'Rationale', body: p.rationale),
          Text(
            'Source diff',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: AppColors.textSecondary,
                  letterSpacing: 0.5,
                ),
          ),
          const SizedBox(height: 8),
          for (final f in p.files) ...[
            DiffViewer(fileDiff: f),
            const SizedBox(height: 12),
          ],
          if (p.applyError != null)
            _Block(title: 'Apply error', body: p.applyError!, mono: true),
          const SizedBox(height: 8),
          Text(
            p.applied
                ? 'Applied to the isolated workspace only — your original project is untouched.'
                : 'Not applied.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }
}

class _ValidationBadges extends StatelessWidget {
  final PatchValidation validation;
  const _ValidationBadges({required this.validation});

  @override
  Widget build(BuildContext context) {
    Widget chip(String label, bool ok) => Padding(
          padding: const EdgeInsets.only(left: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                ok ? Icons.check_circle_outline : Icons.cancel_outlined,
                size: 12,
                color: ok ? SeverityColors.success : SeverityColors.error,
              ),
              const SizedBox(width: 4),
              Text(
                label,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: ok ? SeverityColors.success : SeverityColors.error,
                    ),
              ),
            ],
          ),
        );

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        chip('Syntax', validation.astParsed),
        chip('Path safe', validation.pathCheckPassed),
        chip('Size', validation.sizeOk),
      ],
    );
  }
}

class _PaneTitle extends StatelessWidget {
  final IconData icon;
  final String text;
  const _PaneTitle({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 17, color: AppColors.textSecondary),
        const SizedBox(width: 8),
        Text(text, style: Theme.of(context).textTheme.headlineLarge),
      ],
    );
  }
}

class _Block extends StatelessWidget {
  final String title;
  final String body;
  final bool mono;

  const _Block({required this.title, required this.body, this.mono = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
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
          const SizedBox(height: 6),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Text(
              body,
              style: mono
                  ? AppTheme.monoStyle(fontSize: 12)
                  : Theme.of(context).textTheme.bodyLarge,
            ),
          ),
        ],
      ),
    );
  }
}
