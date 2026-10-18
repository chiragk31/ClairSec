import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/glossary/glossary.dart';
import '../../../core/theme/tokens.dart';
import '../../../providers/scans_provider.dart';
import '../../../ui/components/code_views.dart';

/// Live proof (FEATURES.md F8): re-send the exact stored attack to the original
/// app and to the patched app, and show what each one answered. The verdict on
/// each side comes from the same platform oracle, never from an AI model.
class ReplayPanel extends StatelessWidget {
  const ReplayPanel({super.key, required this.findingId, required this.category});

  final String findingId;
  final String category;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final plain = kGlossaryEntries[category]?.plain;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (plain != null)
          Padding(
            padding: const EdgeInsets.only(bottom: ClairSpacing.md),
            child: Text(
              'What we replay: $plain',
              style: TextStyle(color: tokens.textSecondary),
            ),
          ),
        LayoutBuilder(
          builder: (context, c) {
            final wide = c.maxWidth > 760;
            final original = _ReplaySide(findingId: findingId, target: 'original', label: 'Original app');
            final patched = _ReplaySide(findingId: findingId, target: 'patched', label: 'Patched app');
            return wide
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: original),
                      const SizedBox(width: ClairSpacing.md),
                      Expanded(child: patched),
                    ],
                  )
                : Column(children: [original, const SizedBox(height: ClairSpacing.md), patched]);
          },
        ),
      ],
    );
  }
}

class _ReplaySide extends ConsumerStatefulWidget {
  const _ReplaySide({required this.findingId, required this.target, required this.label});

  final String findingId;
  final String target;
  final String label;

  @override
  ConsumerState<_ReplaySide> createState() => _ReplaySideState();
}

class _ReplaySideState extends ConsumerState<_ReplaySide> {
  Map<String, dynamic>? _replay;
  String? _error;
  bool _running = false;
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _running = true;
      _error = null;
      _replay = null;
    });
    final service = ref.read(scansServiceProvider);
    try {
      final started = await service.startReplay(widget.findingId, widget.target);
      final id = started['id'] as String;
      _poll?.cancel();
      _poll = Timer.periodic(const Duration(milliseconds: 600), (t) async {
        try {
          final r = await service.getReplay(id);
          if (!mounted) return;
          if (r['state'] == 'completed' || r['state'] == 'failed') {
            t.cancel();
            setState(() {
              _replay = r;
              _running = false;
            });
          }
        } catch (e) {
          t.cancel();
          if (mounted) {
            setState(() {
              _error = '$e';
              _running = false;
            });
          }
        }
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _running = false;
      });
    }
  }

  String? _asText(Object? body) {
    if (body == null) return null;
    if (body is String) return body;
    return const JsonEncoder.withIndent('  ').convert(body);
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final r = _replay;
    final fired = r?['oracle_fired'] == true;
    final completed = r?['state'] == 'completed';
    final verdictColor = !completed ? tokens.textMuted : (fired ? tokens.danger : tokens.success);

    final exchange = (r?['exchange'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};
    final req = (exchange['request'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};
    final resp = (exchange['response'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};

    return Container(
      padding: ClairInsets.allMd,
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: verdictColor.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(widget.label, style: Theme.of(context).textTheme.titleMedium)),
              FilledButton.icon(
                onPressed: _running ? null : _start,
                icon: _running
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.replay, size: 16),
                label: Text(_running ? 'Replaying...' : 'Replay attack'),
              ),
            ],
          ),
          const SizedBox(height: ClairSpacing.sm),
          if (_error != null)
            Text('Could not start the replay: $_error', style: TextStyle(color: tokens.danger))
          else if (r == null && !_running)
            Text(
              widget.target == 'original'
                  ? 'Sends the stored attack to the app as it was imported.'
                  : 'Sends the same attack to a build of the fixed code.',
              style: TextStyle(color: tokens.textSecondary),
            )
          else if (r != null && r['state'] == 'failed')
            Text(
              (r['error'] ?? r['rationale'] ?? 'Replay failed').toString(),
              style: TextStyle(color: tokens.warning),
            )
          else if (r != null) ...[
            Row(
              children: [
                Icon(fired ? Icons.dangerous : Icons.verified_user, color: verdictColor, size: 18),
                const SizedBox(width: ClairSpacing.xs),
                Expanded(
                  child: Text(
                    fired ? 'ORACLE FIRED: the attack worked' : 'ORACLE CLEAR: the attack was blocked',
                    style: TextStyle(fontWeight: FontWeight.w700, color: verdictColor),
                  ),
                ),
              ],
            ),
            const SizedBox(height: ClairSpacing.xs),
            Text((r['rationale'] ?? '').toString(), style: TextStyle(color: tokens.textSecondary)),
            const SizedBox(height: ClairSpacing.sm),
            HttpExchangeView(
              method: (req['method'] ?? 'GET').toString(),
              url: (req['url_path'] ?? req['path'] ?? '').toString(),
              requestHeaders: (req['headers'] as Map?)?.cast<String, dynamic>() ?? const {},
              requestBody: _asText(req['body']),
              responseStatus: (resp['status'] as num?)?.toInt() ?? 0,
              responseHeaders: (resp['headers'] as Map?)?.cast<String, dynamic>() ?? const {},
              responseBody: _asText(resp['body']),
            ),
          ],
        ],
      ),
    );
  }
}
