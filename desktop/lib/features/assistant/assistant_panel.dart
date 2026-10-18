import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/tokens.dart';
import '../../services/assistant_service.dart';

final assistantServiceProvider = Provider((ref) => AssistantService());

class _Turn {
  _Turn.user(this.text)
      : isUser = true,
        reply = null;
  _Turn.assistant(AssistantReply r)
      : isUser = false,
        text = r.answer,
        reply = r;

  final bool isUser;
  final String text;
  final AssistantReply? reply;
}

/// "Ask ClairSec" (FEATURES.md F11): a context-aware, read-only guide.
///
/// It explains what the platform recorded and links to where to look. It cannot
/// change anything: suggested actions are plain navigation the user chooses.
class AssistantPanel extends ConsumerStatefulWidget {
  const AssistantPanel({super.key, required this.currentPath, this.onClose});

  final String currentPath;
  final VoidCallback? onClose;

  @override
  ConsumerState<AssistantPanel> createState() => _AssistantPanelState();
}

class _AssistantPanelState extends ConsumerState<AssistantPanel> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<_Turn> _turns = [];
  List<String> _suggestions = const [];
  String? _conversationId;
  String _suggestionsFor = '';
  bool _simple = false;
  bool _busy = false;

  AssistantContext get _context => AssistantContext.fromPath(widget.currentPath);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadSuggestions();
  }

  @override
  void didUpdateWidget(covariant AssistantPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentPath != widget.currentPath) _loadSuggestions();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadSuggestions() async {
    final screen = _context.screen;
    if (screen == _suggestionsFor) return;
    _suggestionsFor = screen;
    try {
      final qs = await ref.read(assistantServiceProvider).suggestions(screen);
      if (mounted) setState(() => _suggestions = qs);
    } catch (_) {
      if (mounted) setState(() => _suggestions = const []);
    }
  }

  Future<void> _ask(String question) async {
    final q = question.trim();
    if (q.isEmpty || _busy) return;
    setState(() {
      _turns.add(_Turn.user(q));
      _busy = true;
      _input.clear();
    });
    try {
      final reply = await ref.read(assistantServiceProvider).ask(
            q,
            _context,
            explainSimply: _simple,
            conversationId: _conversationId,
          );
      _conversationId = reply.conversationId;
      if (mounted) setState(() => _turns.add(_Turn.assistant(reply)));
    } catch (e) {
      if (mounted) {
        setState(() => _turns.add(_Turn.assistant(AssistantReply(
              answer: 'I could not reach the ClairSec backend ($e). Check the readiness banner on the Dashboard.',
              mode: 'offline',
              conversationId: _conversationId ?? '',
            ))));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOutCubic);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    return Material(
      color: tokens.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(ClairSpacing.lg, ClairSpacing.md, ClairSpacing.sm, ClairSpacing.sm),
            child: Row(
              children: [
                Icon(Icons.auto_awesome, size: 18, color: tokens.agentAssistant),
                const SizedBox(width: ClairSpacing.sm),
                Expanded(child: Text('Ask ClairSec', style: Theme.of(context).textTheme.titleMedium)),
                if (widget.onClose != null)
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    tooltip: 'Close assistant (Ctrl+J)',
                    onPressed: widget.onClose,
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.lg),
            child: Text(
              'Explains what ClairSec recorded. It can\'t change any result.',
              style: TextStyle(color: tokens.textSecondary),
            ),
          ),
          SwitchListTile(
            dense: true,
            value: _simple,
            onChanged: (v) => setState(() => _simple = v),
            title: const Text('Explain simply'),
            contentPadding: const EdgeInsets.symmetric(horizontal: ClairSpacing.lg),
          ),
          Divider(height: 1, color: tokens.border),
          Expanded(
            child: _turns.isEmpty
                ? ListView(
                    padding: ClairInsets.allLg,
                    children: [
                      Text('Try asking', style: TextStyle(color: tokens.textMuted)),
                      const SizedBox(height: ClairSpacing.sm),
                      for (final q in _suggestions)
                        Padding(
                          padding: const EdgeInsets.only(bottom: ClairSpacing.sm),
                          child: ActionChip(label: Text(q), onPressed: () => _ask(q)),
                        ),
                    ],
                  )
                : ListView.builder(
                    controller: _scroll,
                    padding: ClairInsets.allMd,
                    itemCount: _turns.length + (_busy ? 1 : 0),
                    itemBuilder: (context, i) {
                      if (i >= _turns.length) {
                        return const Padding(
                          padding: ClairInsets.allMd,
                          child: LinearProgressIndicator(minHeight: 2),
                        );
                      }
                      return _Bubble(turn: _turns[i]);
                    },
                  ),
          ),
          if (_turns.isNotEmpty && _suggestions.isNotEmpty)
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
                children: [
                  for (final q in _suggestions)
                    Padding(
                      padding: const EdgeInsets.only(right: ClairSpacing.xs),
                      child: ActionChip(label: Text(q), onPressed: () => _ask(q)),
                    ),
                ],
              ),
            ),
          Padding(
            padding: ClairInsets.allMd,
            child: TextField(
              controller: _input,
              enabled: !_busy,
              textInputAction: TextInputAction.send,
              onSubmitted: _ask,
              decoration: InputDecoration(
                hintText: 'Ask about this screen...',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.send, size: 18),
                  tooltip: 'Send',
                  onPressed: () => _ask(_input.text),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.turn});

  final _Turn turn;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final reply = turn.reply;
    return Align(
      alignment: turn.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: ClairSpacing.sm),
        padding: ClairInsets.allMd,
        constraints: const BoxConstraints(maxWidth: 520),
        decoration: BoxDecoration(
          color: turn.isUser ? tokens.accentMuted : tokens.surfaceRaised,
          borderRadius: BorderRadius.circular(ClairRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(turn.text, style: TextStyle(color: tokens.textPrimary)),
            if (reply != null) ...[
              const SizedBox(height: ClairSpacing.xs),
              Text(
                reply.mode == 'llm' ? 'AI explanation · grounded in recorded data' : 'Offline assistant',
                style: TextStyle(color: tokens.textMuted, fontStyle: FontStyle.italic),
              ),
              if (reply.citations.isNotEmpty) ...[
                const SizedBox(height: ClairSpacing.xs),
                Wrap(
                  spacing: ClairSpacing.xs,
                  runSpacing: ClairSpacing.xs,
                  children: [
                    for (final c in reply.citations)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        avatar: const Icon(Icons.link, size: 14),
                        label: Text('${c.type}: ${c.label}'),
                      ),
                  ],
                ),
              ],
              if (reply.actions.isNotEmpty) ...[
                const SizedBox(height: ClairSpacing.xs),
                Wrap(
                  spacing: ClairSpacing.xs,
                  children: [
                    for (final a in reply.actions)
                      TextButton(onPressed: () => context.go(a.route), child: Text(a.label)),
                  ],
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}
