import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/tokens.dart';
import '../../../providers/scans_provider.dart';

/// "Watch a recorded run" (FEATURES.md F4): loads a bundle captured from a real
/// earlier scan. Everything shown is what that run recorded; the scan is badged
/// RECORDED RUN so it is never mistaken for a live result.
class RecordedRunDialog extends ConsumerStatefulWidget {
  const RecordedRunDialog({super.key});

  static Future<void> show(BuildContext context) =>
      showDialog<void>(context: context, builder: (_) => const RecordedRunDialog());

  @override
  ConsumerState<RecordedRunDialog> createState() => _RecordedRunDialogState();
}

class _RecordedRunDialogState extends ConsumerState<RecordedRunDialog> {
  late final Future<List<Map<String, dynamic>>> _bundles =
      ref.read(scansServiceProvider).listBundles();
  String? _loading;
  String? _error;

  Future<void> _open(String fileName) async {
    setState(() {
      _loading = fileName;
      _error = null;
    });
    try {
      final scanId = await ref.read(scansServiceProvider).replayBundle(fileName);
      ref.invalidate(scansProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      context.go('/scans/$scanId');
    } catch (e) {
      setState(() {
        _loading = null;
        _error = 'Could not load this recording: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return AlertDialog(
      title: const Text('Watch a recorded run'),
      content: SizedBox(
        width: 520,
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: _bundles,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const SizedBox(height: 80, child: Center(child: CircularProgressIndicator()));
            }
            if (snap.hasError) {
              return Text('Recordings unavailable: ${snap.error}', style: TextStyle(color: tokens.danger));
            }
            final bundles = snap.data ?? const [];
            if (bundles.isEmpty) {
              return Text(
                'No recordings found in demo/bundles. Create one with '
                'python scripts/record_demo_bundle.py',
                style: TextStyle(color: tokens.textSecondary),
              );
            }
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Each recording is a real earlier scan, replayed as it happened. It is clearly '
                  'marked RECORDED RUN and is not your project.',
                  style: TextStyle(color: tokens.textSecondary),
                ),
                const SizedBox(height: ClairSpacing.md),
                for (final b in bundles)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.history, color: tokens.accent),
                    title: Text((b['project_name'] ?? b['file_name']).toString()),
                    subtitle: Text(
                      'Recorded ${b['recorded_at'] ?? 'unknown date'} · '
                      '${b['findings_count']} finding(s) · ${b['events_count']} events',
                    ),
                    trailing: _loading == b['file_name']
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : FilledButton(
                            onPressed: _loading == null ? () => _open(b['file_name'] as String) : null,
                            child: const Text('Watch'),
                          ),
                  ),
                if (_error != null) Text(_error!, style: TextStyle(color: tokens.danger)),
              ],
            );
          },
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    );
  }
}
