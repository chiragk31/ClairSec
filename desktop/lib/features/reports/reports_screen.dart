import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../models/scan_summary.dart';
import '../../providers/scans_provider.dart';
import '../../services/reports_service.dart';
import '../shared/empty_state.dart';
import '../shared/page_header.dart';

final reportsServiceProvider = Provider((ref) => ReportsService());

/// Every report generated so far, newest first (`GET /api/reports`).
final reportsProvider = FutureProvider<List<ReportRecord>>((ref) async {
  return ref.read(reportsServiceProvider).listAll();
});

/// Reports (FEATURES.md F12, F13): generate an executive + technical report for a
/// completed scan, preview it, open it in any format, and compare scans.
class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final scans = ref.watch(scanListProvider).where((s) => s.state == ScanState.completed).toList();
    final reports = ref.watch(reportsProvider).maybeWhen(
          data: (r) => r,
          orElse: () => const <ReportRecord>[],
        );

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Reports',
            subtitle: 'Turn a finished scan into a report a manager and a developer can both act on',
            actions: [
              IconButton(
                onPressed: () {
                  ref.invalidate(scansProvider);
                  ref.invalidate(reportsProvider);
                },
                icon: const Icon(Icons.refresh, size: 19),
                tooltip: 'Refresh',
              ),
            ],
          ),
          Expanded(
            child: scans.isEmpty
                ? const Padding(
                    padding: ClairInsets.allXl,
                    child: EmptyState(
                      icon: Icons.assignment_outlined,
                      title: 'No completed scans yet',
                      description: 'Run a scan (or the Demo app) first. Every completed scan can be '
                          'turned into an HTML, Markdown, JSON or SARIF report.',
                    ),
                  )
                : ListView.separated(
                    padding: ClairInsets.allXl,
                    itemCount: scans.length,
                    separatorBuilder: (_, _) => const SizedBox(height: ClairSpacing.lg),
                    itemBuilder: (context, i) => _ScanReportCard(
                      scan: scans[i],
                      reports: reports.where((r) => r.scanId == scans[i].id).toList(),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ScanReportCard extends ConsumerStatefulWidget {
  const _ScanReportCard({required this.scan, required this.reports});

  final ScanSummary scan;
  final List<ReportRecord> reports;

  @override
  ConsumerState<_ScanReportCard> createState() => _ScanReportCardState();
}

class _ScanReportCardState extends ConsumerState<_ScanReportCard> {
  bool _busy = false;
  String? _error;

  Future<void> _generate() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(reportsServiceProvider).generate(widget.scan.id);
      ref.invalidate(reportsProvider);
    } catch (e) {
      _error = 'Could not generate the report: $e';
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _compare() async {
    final service = ref.read(reportsServiceProvider);
    try {
      final diff = await service.diff(widget.scan.projectId);
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (_) => _DiffDialog(diff: diff));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Comparison unavailable: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final latest = widget.reports.isEmpty ? null : widget.reports.first;
    final p = widget.scan.posture;
    return Container(
      padding: ClairInsets.allLg,
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: ClairSpacing.md,
            runSpacing: ClairSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(widget.scan.projectName, style: Theme.of(context).textTheme.titleMedium),
              Text(
                '${widget.scan.findingsConfirmed} confirmed · ${widget.scan.fixesVerified} fixes verified'
                '${p != null ? ' · score ${p.before} → ${p.after}' : ''}',
                style: TextStyle(color: tokens.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.md),
          Wrap(
            spacing: ClairSpacing.sm,
            runSpacing: ClairSpacing.sm,
            children: [
              FilledButton.icon(
                onPressed: _busy ? null : _generate,
                icon: _busy
                    ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.description_outlined, size: 16),
                label: Text(latest == null ? 'Generate report' : 'Generate again'),
              ),
              OutlinedButton.icon(
                onPressed: _compare,
                icon: const Icon(Icons.compare_arrows, size: 16),
                label: const Text('Compare with previous scan'),
              ),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: ClairSpacing.sm),
            Text(_error!, style: TextStyle(color: tokens.danger)),
          ],
          if (latest != null) ...[
            const SizedBox(height: ClairSpacing.lg),
            Text('Executive preview', style: TextStyle(fontWeight: FontWeight.w600, color: tokens.textSecondary)),
            const SizedBox(height: ClairSpacing.xs),
            for (final line in latest.summary)
              Padding(
                padding: const EdgeInsets.only(bottom: ClairSpacing.xs),
                child: Text(line, style: TextStyle(color: tokens.textPrimary)),
              ),
            const SizedBox(height: ClairSpacing.sm),
            Wrap(
              spacing: ClairSpacing.sm,
              runSpacing: ClairSpacing.sm,
              children: [
                for (final entry in const {
                  'pdf': 'Open PDF',
                  'html': 'Open HTML',
                  'md': 'Markdown',
                  'json': 'JSON',
                  'sarif': 'SARIF',
                }.entries)
                  if (latest.files[entry.key] != null)
                    OutlinedButton(
                      onPressed: () => ref.read(reportsServiceProvider).openFile(latest.files[entry.key]!),
                      child: Text(entry.value),
                    ),
                if (latest.files['html'] != null)
                  TextButton.icon(
                    onPressed: () => ref.read(reportsServiceProvider).openFolder(latest.files['html']!),
                    icon: const Icon(Icons.folder_open, size: 16),
                    label: const Text('Open folder'),
                  ),
              ],
            ),
            const SizedBox(height: ClairSpacing.xs),
            Text(
              'Tip: open the HTML report and use your browser\'s Print → Save as PDF for a PDF copy.',
              style: TextStyle(color: tokens.textMuted),
            ),
          ],
        ],
      ),
    );
  }
}

class _DiffDialog extends StatelessWidget {
  const _DiffDialog({required this.diff});

  final ScanDiff diff;

  static const _labels = {
    'new': ('New since last scan', Icons.fiber_new),
    'came_back': ('Came back after a fix', Icons.restart_alt),
    'still_open': ('Still open', Icons.pending_outlined),
    'fixed_since_last_scan': ('Fixed since last scan', Icons.check_circle_outline),
  };

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return AlertDialog(
      title: const Text('What changed between the last two scans'),
      content: SizedBox(
        width: 520,
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final e in _labels.entries) ...[
              Row(
                children: [
                  Icon(e.value.$2, size: 18, color: tokens.accent),
                  const SizedBox(width: ClairSpacing.sm),
                  Text('${e.value.$1} (${diff.buckets[e.key]?.length ?? 0})',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ],
              ),
              for (final f in diff.buckets[e.key] ?? const <Map<String, dynamic>>[])
                Padding(
                  padding: const EdgeInsets.only(left: ClairSpacing.xl, top: ClairSpacing.xs),
                  child: Text('${f['title']} · ${f['method']} ${f['route']}',
                      style: TextStyle(color: tokens.textSecondary)),
                ),
              const SizedBox(height: ClairSpacing.md),
            ],
          ],
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    );
  }
}
