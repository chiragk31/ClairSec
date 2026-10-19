import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/tokens.dart';
import '../../../models/project.dart';
import '../../../providers/projects_provider.dart';
import '../../../ui/components/cs_stepper.dart';

class AutopilotDialog extends ConsumerStatefulWidget {
  final ProjectRecord project;

  const AutopilotDialog({super.key, required this.project});

  @override
  ConsumerState<AutopilotDialog> createState() => _AutopilotDialogState();
}

class _AutopilotDialogState extends ConsumerState<AutopilotDialog> {
  String? _pipelineId;
  String _pipelineStatus = 'starting';
  String? _error;
  String? _fixHint;
  String? _scanId;
  Timer? _pollTimer;

  Map<String, dynamic> _stages = {
    'import': {'status': 'completed', 'line': 'Project source verified'},
    'isolate': {'status': 'pending', 'line': 'Building a sealed copy of your app so we can test it safely'},
    'scan': {'status': 'pending', 'line': 'Autonomous security scan: Builder -> Attacker -> Evaluator -> Fixer -> Verifier'},
    'report': {'status': 'pending', 'line': 'Report generation arrives in V7 — scan results preserved'},
  };

  @override
  void initState() {
    super.initState();
    _startAutopilot();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _startAutopilot() async {
    final service = ref.read(projectsServiceProvider);
    try {
      final res = await service.startPipeline(projectId: widget.project.id);
      setState(() {
        _pipelineId = res['pipeline_id'] as String?;
        _pipelineStatus = res['status'] as String? ?? 'running';
      });

      _pollTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
        if (_pipelineId == null) return;
        try {
          final p = await service.getPipeline(_pipelineId!);
          if (!mounted) return;
          setState(() {
            _pipelineStatus = p['status'] as String? ?? 'running';
            _stages = Map<String, dynamic>.from(p['stages'] as Map? ?? _stages);
            _error = p['error'] as String?;
            _fixHint = p['fix_hint'] as String?;
            _scanId = p['scan_id'] as String?;
          });

          if (_pipelineStatus == 'completed' || _pipelineStatus == 'failed' || _pipelineStatus == 'cancelled') {
            timer.cancel();
          }
        } catch (_) {}
      });
    } catch (e) {
      setState(() {
        _pipelineStatus = 'failed';
        _error = e.toString();
      });
    }
  }

  CsStepStatus _mapStatus(String? status) {
    switch (status) {
      case 'completed':
        return CsStepStatus.completed;
      case 'running':
        return CsStepStatus.running;
      case 'failed':
        return CsStepStatus.failed;
      default:
        return CsStepStatus.pending;
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    final steps = [
      StepData(
        title: 'Import',
        plainLanguage: _stages['import']?['line'] as String?,
        status: _mapStatus(_stages['import']?['status'] as String?),
        elapsed: _stages['import']?['elapsed_s'] != null ? '${_stages['import']?['elapsed_s']}s' : null,
      ),
      StepData(
        title: 'Isolate',
        plainLanguage: _stages['isolate']?['line'] as String? ?? 'Building sealed container sandbox',
        status: _mapStatus(_stages['isolate']?['status'] as String?),
        elapsed: _stages['isolate']?['elapsed_s'] != null ? '${_stages['isolate']?['elapsed_s']}s' : null,
        error: _stages['isolate']?['error'] as String?,
      ),
      StepData(
        title: 'Scan',
        plainLanguage: _stages['scan']?['line'] as String? ?? 'Autonomous security testing',
        status: _mapStatus(_stages['scan']?['status'] as String?),
        elapsed: _stages['scan']?['elapsed_s'] != null ? '${_stages['scan']?['elapsed_s']}s' : null,
        error: _stages['scan']?['error'] as String?,
      ),
      StepData(
        title: 'Report',
        plainLanguage: _stages['report']?['line'] as String? ?? 'Report generation arrives in V7',
        status: _mapStatus(_stages['report']?['status'] as String?),
        elapsed: _stages['report']?['elapsed_s'] != null ? '${_stages['report']?['elapsed_s']}s' : null,
      ),
    ];

    return Dialog(
      backgroundColor: tokens.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ClairRadius.lg),
        side: BorderSide(color: tokens.border),
      ),
      child: ConstrainedBox(
        // Never taller than the visible window: the body scrolls instead of
        // overflowing at the bottom (small windows, presenter text, long errors).
        constraints: BoxConstraints(
          maxWidth: 580,
          maxHeight: MediaQuery.sizeOf(context).height * 0.85,
        ),
        child: Padding(
          padding: const EdgeInsets.all(ClairSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Row(
                      children: [
                        Icon(Icons.bolt, color: tokens.accent, size: 22),
                        const SizedBox(width: ClairSpacing.xs),
                        Expanded(
                          child: Text(
                            'Autopilot — Full Security Check',
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: ClairTypography.h2,
                              fontWeight: FontWeight.w700,
                              color: tokens.textPrimary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: Icon(Icons.close, color: tokens.textSecondary, size: 20),
                  ),
                ],
              ),
              const SizedBox(height: ClairSpacing.xs),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
              Text(
                'Automated pipeline testing ${widget.project.name} safely inside container isolation.',
                style: TextStyle(fontSize: ClairTypography.small, color: tokens.textSecondary),
              ),
              const SizedBox(height: ClairSpacing.lg),
              CsStepper(steps: steps),
              if (_fixHint != null) ...[
                const SizedBox(height: ClairSpacing.md),
                Container(
                  padding: const EdgeInsets.all(ClairSpacing.md),
                  decoration: BoxDecoration(
                    color: tokens.warning.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(ClairRadius.md),
                    border: Border.all(color: tokens.warning.withValues(alpha: 0.4)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.lightbulb_outline, size: 16, color: tokens.warning),
                      const SizedBox(width: ClairSpacing.xs),
                      Expanded(
                        child: Text(
                          _fixHint!,
                          style: TextStyle(fontSize: ClairTypography.caption, color: tokens.warning),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: ClairSpacing.sm),
                Text(
                  _error!,
                  style: TextStyle(fontSize: ClairTypography.caption, color: tokens.critical),
                ),
              ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: ClairSpacing.lg),
              Divider(height: 1, color: tokens.border),
              const SizedBox(height: ClairSpacing.md),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (_scanId != null)
                    FilledButton.icon(
                      onPressed: () {
                        Navigator.of(context).pop();
                        context.go('/scans/$_scanId');
                      },
                      icon: const Icon(Icons.open_in_new, size: 16),
                      label: const Text('View Live Scan'),
                    )
                  else
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: Text(_pipelineStatus == 'completed' ? 'Close' : 'Cancel'),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
