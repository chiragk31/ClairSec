import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../models/finding.dart';
import 'status_badges.dart';

/// One row in the findings list (DESIGN.md §7). Tapping opens the full
/// detail screen with evidence, source location, and reproduction summary.
class FindingListTile extends StatelessWidget {
  final Finding finding;
  final VoidCallback? onTap;

  const FindingListTile({super.key, required this.finding, this.onTap});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(ClairRadius.md),
      child: Container(
        padding: const EdgeInsets.all(ClairSpacing.lg),
        decoration: BoxDecoration(
          color: tokens.surface,
          borderRadius: BorderRadius.circular(ClairRadius.md),
          border: Border.all(color: tokens.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    finding.title,
                    style: Theme.of(context).textTheme.headlineMedium,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                SeverityPill(severity: finding.severity),
              ],
            ),
            const SizedBox(height: ClairSpacing.sm),
            Row(
              children: [
                Icon(Icons.route_outlined, size: 13, color: tokens.textMuted),
                const SizedBox(width: ClairSpacing.xs),
                Text(
                  '${finding.method}  ${finding.routeTemplate}',
                  style: AppTheme.monoStyle(fontSize: ClairTypography.small, color: tokens.textSecondary),
                ),
              ],
            ),
            const SizedBox(height: ClairSpacing.md),
            Wrap(
              spacing: ClairSpacing.sm,
              runSpacing: ClairSpacing.sm,
              children: [
                FindingStatusBadge(status: finding.status),
                RuntimeConfirmationBadge.forFinding(finding),
                RemediationStatusBadge(status: finding.remediationStatus),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
