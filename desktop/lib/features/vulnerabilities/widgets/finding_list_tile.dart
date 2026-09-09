import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
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
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
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
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(Icons.route_outlined, size: 13, color: AppColors.textDisabled),
                const SizedBox(width: 4),
                Text(
                  '${finding.method}  ${finding.routeTemplate}',
                  style: AppTheme.monoStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FindingStatusBadge(status: finding.status),
                RuntimeConfirmationBadge(runtimeConfirmed: finding.runtimeConfirmed),
                RemediationStatusBadge(status: finding.remediationStatus),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
