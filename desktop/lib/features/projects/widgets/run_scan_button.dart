import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/scan_summary.dart';
import '../../../providers/scans_provider.dart';
import '../../../providers/findings_provider.dart';

/// Triggers a full Builder → Attacker → Evaluator → Fixer → Verifier run and
/// polls the scan until it reaches a terminal state, then navigates to the
/// live scan view.
///
/// Progress text comes from the backend's reported `stage` — never a synthetic
/// timer (RULES.md §6).
class RunScanButton extends ConsumerStatefulWidget {
  final String projectId;
  final bool enabled;

  const RunScanButton({
    super.key,
    required this.projectId,
    required this.enabled,
  });

  @override
  ConsumerState<RunScanButton> createState() => _RunScanButtonState();
}

class _RunScanButtonState extends ConsumerState<RunScanButton> {
  bool _busy = false;
  String? _stage;
  String? _error;

  Future<void> _runScan() async {
    setState(() {
      _busy = true;
      _error = null;
      _stage = 'queued';
    });

    final service = ref.read(scansServiceProvider);
    try {
      final scanId = await service.createScan(widget.projectId);
      await _pollScan(scanId);

      if (!mounted) return;
      // Refresh every downstream view before navigating.
      ref.invalidate(scansProvider);
      ref.invalidate(allFindingsProvider);
      context.go('/scans/$scanId');
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _stage = null;
        });
      }
    }
  }

  /// The full pipeline runs five agents against a live container, so this
  /// polls patiently rather than assuming a duration.
  Future<void> _pollScan(String scanId) async {
    final service = ref.read(scansServiceProvider);
    const interval = Duration(seconds: 2);
    const maxAttempts = 180; // ~6 minutes ceiling

    for (var i = 0; i < maxAttempts; i++) {
      await Future<void>.delayed(interval);
      if (!mounted) return;

      final scan = await service.getScan(scanId);
      if (mounted) setState(() => _stage = scan.stage.isEmpty ? scan.state.label : scan.stage);

      if (scan.isTerminal) return;
    }
    if (mounted) setState(() => _error = 'Timed out waiting for the scan to finish.');
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (_busy) ...[
              const SizedBox(
                width: 13,
                height: 13,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 8),
              Text(
                _stage ?? 'running…',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ] else
              FilledButton.icon(
                onPressed: widget.enabled ? _runScan : null,
                icon: const Icon(Icons.radar, size: 15),
                label: const Text('Run Security Scan'),
              ),
            if (!widget.enabled && !_busy) ...[
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Isolate the project first',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
            ],
          ],
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: SeverityColors.error.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SeverityColors.error.withValues(alpha: 0.3)),
            ),
            child: Text(
              _error!,
              style: AppTheme.monoStyle(fontSize: 11, color: SeverityColors.error),
            ),
          ),
        ],
      ],
    );
  }
}
