import 'dart:async';
import 'package:flutter/material.dart';
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

class _ErrorBox extends StatelessWidget {
  final String message;
  const _ErrorBox({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: SeverityColors.error.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SeverityColors.error.withValues(alpha: 0.3)),
      ),
      child: Text(
        message,
        style: AppTheme.monoStyle(fontSize: 11, color: SeverityColors.error),
      ),
    );
  }
}
