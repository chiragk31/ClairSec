import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../providers/isolation_provider.dart';
import 'run_scan_button.dart';

/// Isolation lifecycle controls for a project card (Phase 3 / 3.5).
///
/// Starting isolation returns a background job id (202) — this widget polls
/// `GET /api/jobs/{id}` until the job reaches a terminal state, showing the
/// real reported stage rather than a fake progress bar (RULES.md §6).
class IsolationControls extends ConsumerStatefulWidget {
  final String projectId;
  final bool isolationReady;

  const IsolationControls({
    super.key,
    required this.projectId,
    required this.isolationReady,
  });

  @override
  ConsumerState<IsolationControls> createState() => _IsolationControlsState();
}

class _IsolationControlsState extends ConsumerState<IsolationControls> {
  bool _busy = false;
  String? _stage;
  String? _error;
  Timer? _pollTimer;

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _startIsolation() async {
    setState(() {
      _busy = true;
      _error = null;
      _stage = 'queued';
    });

    final service = ref.read(isolationServiceProvider);
    try {
      final jobId = await service.startIsolation(widget.projectId);
      await _pollJob(jobId);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _stage = null;
        });
        ref.invalidate(isolationStatusProvider(widget.projectId));
      }
    }
  }

  /// Poll the background job until terminal. Building an image can take up to
  /// the configured build timeout, so this polls patiently rather than
  /// assuming a duration.
  Future<void> _pollJob(String jobId) async {
    final service = ref.read(isolationServiceProvider);
    const interval = Duration(seconds: 2);
    const maxAttempts = 120; // ~4 minutes ceiling

    for (var i = 0; i < maxAttempts; i++) {
      await Future<void>.delayed(interval);
      if (!mounted) return;

      final job = await service.getJob(jobId);
      if (mounted) setState(() => _stage = job.stage);

      if (job.isTerminal) {
        if (!job.succeeded && mounted) {
          setState(() => _error = job.error ?? 'Isolation ${job.status}.');
        }
        return;
      }
    }
    if (mounted) setState(() => _error = 'Timed out waiting for isolation job.');
  }

  Future<void> _runAction(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        ref.invalidate(isolationStatusProvider(widget.projectId));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(isolationStatusProvider(widget.projectId));
    final service = ref.read(isolationServiceProvider);

    return statusAsync.when(
      loading: () => const _StatusLine(text: 'Checking isolation status…'),
      error: (err, _) => _StatusLine(text: 'Status unavailable', color: SeverityColors.warning),
      data: (status) {
        final state = status.state;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(state.icon, size: 14, color: state.color),
                const SizedBox(width: 6),
                Text(
                  state.label,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(color: state.color),
                ),
                if (_busy) ...[
                  const SizedBox(width: 12),
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    _stage ?? 'working…',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
                const Spacer(),
                if (!_busy && state.canIsolate && widget.isolationReady)
                  FilledButton.icon(
                    onPressed: _startIsolation,
                    icon: const Icon(Icons.play_arrow, size: 15),
                    label: const Text('Isolate'),
                  ),
                if (!_busy && state.canStop) ...[
                  OutlinedButton.icon(
                    onPressed: () => _runAction(() => service.stop(widget.projectId)),
                    icon: const Icon(Icons.stop, size: 15),
                    label: const Text('Stop'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () => _runAction(() => service.cleanup(widget.projectId)),
                    icon: const Icon(Icons.delete_outline, size: 15),
                    label: const Text('Clean up'),
                  ),
                ],
              ],
            ),
            if (status.containerName != null && state.canStop) ...[
              const SizedBox(height: 6),
              Text(
                'Container: ${status.containerName}',
                style: AppTheme.monoStyle(fontSize: 11, color: AppColors.textDisabled),
              ),
            ],
            const SizedBox(height: 12),
            RunScanButton(
              projectId: widget.projectId,
              enabled: !_busy && state.canStop,
            ),
            if (status.isolationError != null && _error == null) ...[
              const SizedBox(height: 6),
              _ErrorBox(message: status.isolationError!),
            ],
            if (_error != null) ...[
              const SizedBox(height: 6),
              _ErrorBox(message: _error!),
            ],
          ],
        );
      },
    );
  }
}

class _StatusLine extends StatelessWidget {
  final String text;
  final Color? color;
  const _StatusLine({required this.text, this.color});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context)
          .textTheme
          .labelMedium
          ?.copyWith(color: color ?? AppColors.textDisabled),
    );
  }
}

/// Renders an isolation failure so the cause is readable at a glance.
///
/// The backend returns a headline, an optional "Likely cause:" diagnosis, and
/// the tail of the build log. Showing all three as one undifferentiated block
/// of red monospace buries the only part that matters, so they are split:
/// headline and diagnosis stay visible, the raw log is collapsed behind a
/// toggle and scrolls within a bounded height.
class _ErrorBox extends StatefulWidget {
  final String message;
  const _ErrorBox({required this.message});

  @override
  State<_ErrorBox> createState() => _ErrorBoxState();
}

class _ErrorBoxState extends State<_ErrorBox> {
  bool _expanded = false;
  bool _copied = false;

  /// Split the backend message into headline / diagnosis / raw log.
  (String, String?, String?) _parse() {
    final text = widget.message;

    String? diagnosis;
    final causeIndex = text.indexOf('Likely cause:');
    final outputIndex = text.indexOf('Build output');

    if (causeIndex != -1) {
      final end = outputIndex > causeIndex ? outputIndex : text.length;
      diagnosis = text
          .substring(causeIndex + 'Likely cause:'.length, end)
          .trim();
    }

    String? log;
    if (outputIndex != -1) {
      final newline = text.indexOf('\n', outputIndex);
      if (newline != -1) log = text.substring(newline + 1).trim();
    }

    final headlineEnd = [
      causeIndex,
      outputIndex,
      text.length,
    ].where((i) => i > 0).reduce((a, b) => a < b ? a : b);
    final headline = text.substring(0, headlineEnd).trim();

    return (headline, diagnosis, log);
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.message));
    if (!mounted) return;
    setState(() => _copied = true);
    await Future<void>.delayed(const Duration(seconds: 2));
    if (mounted) setState(() => _copied = false);
  }

  @override
  Widget build(BuildContext context) {
    final (headline, diagnosis, log) = _parse();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SeverityColors.error.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SeverityColors.error.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.error_outline,
                  size: 15, color: SeverityColors.error),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  headline.isEmpty ? 'Isolation failed' : headline,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: SeverityColors.error,
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
              InkWell(
                onTap: _copy,
                borderRadius: BorderRadius.circular(4),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  child: Text(
                    _copied ? 'Copied' : 'Copy',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: _copied
                              ? SeverityColors.success
                              : AppColors.textSecondary,
                        ),
                  ),
                ),
              ),
            ],
          ),

          // The actionable part — what to actually do about it.
          if (diagnosis != null) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: SeverityColors.warning.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(5),
                border: Border.all(
                  color: SeverityColors.warning.withValues(alpha: 0.35),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.lightbulb_outline,
                      size: 14, color: SeverityColors.warning),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Likely cause',
                          style:
                              Theme.of(context).textTheme.labelSmall?.copyWith(
                                    color: SeverityColors.warning,
                                    fontWeight: FontWeight.w700,
                                  ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          diagnosis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],

          if (log != null && log.isNotEmpty) ...[
            const SizedBox(height: 8),
            InkWell(
              onTap: () => setState(() => _expanded = !_expanded),
              borderRadius: BorderRadius.circular(4),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      size: 16,
                      color: AppColors.textSecondary,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _expanded ? 'Hide build log' : 'Show build log',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                ),
              ),
            ),
            if (_expanded)
              Container(
                width: double.infinity,
                constraints: const BoxConstraints(maxHeight: 260),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.background,
                  borderRadius: BorderRadius.circular(5),
                  border: Border.all(color: AppColors.border),
                ),
                child: SingleChildScrollView(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Text(
                      log,
                      style: AppTheme.monoStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                      softWrap: false,
                    ),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}
