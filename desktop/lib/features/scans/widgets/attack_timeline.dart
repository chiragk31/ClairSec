import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/theme/theme_provider.dart';
import '../../../models/agent_event.dart';

/// Attack Timeline widget replacing polled event stream (FEATURES.md F5, UI_SYSTEM.md §10).
class AttackTimeline extends ConsumerStatefulWidget {
  const AttackTimeline({
    super.key,
    required this.events,
    this.onSelectFinding,
  });

  final List<AgentEvent> events;
  final void Function(String findingId)? onSelectFinding;

  @override
  ConsumerState<AttackTimeline> createState() => _AttackTimelineState();
}

class _AttackTimelineState extends ConsumerState<AttackTimeline> {
  String _agentFilter = 'all';
  bool _followLive = true;
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Color _agentColor(String agent, ClairTokens tokens) {
    switch (agent.toLowerCase()) {
      case 'builder':
        return tokens.accent;
      case 'attacker':
        return tokens.warning;
      case 'evaluator':
        return tokens.info;
      case 'fixer':
        return tokens.accentMuted;
      case 'verifier':
        return tokens.success;
      default:
        return tokens.textSecondary;
    }
  }

  IconData _eventIcon(String kind) {
    switch (kind) {
      case 'stage_started':
        return Icons.play_arrow;
      case 'stage_finished':
        return Icons.check_circle_outline;
      case 'endpoint_discovered':
        return Icons.hub_outlined;
      case 'test_planned':
        return Icons.bug_report_outlined;
      case 'request_sent':
        return Icons.send_outlined;
      case 'oracle_fired':
        return Icons.warning_amber_rounded;
      case 'finding_confirmed':
        return Icons.error_outline;
      case 'finding_rejected':
        return Icons.remove_circle_outline;
      case 'finding_inconclusive':
        return Icons.help_outline;
      case 'patch_proposed':
        return Icons.code;
      case 'verification_started':
        return Icons.sync;
      case 'verification_result':
        return Icons.verified_outlined;
      case 'budget':
        return Icons.account_balance_wallet_outlined;
      case 'error':
        return Icons.error;
      default:
        return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final themeSettings = ref.watch(themeSettingsProvider);
    final isReduceMotion = themeSettings.reduceMotion == ReduceMotionSetting.on;

    final filteredEvents = widget.events.where((e) {
      if (_agentFilter == 'all') return true;
      return e.agent.toLowerCase() == _agentFilter.toLowerCase();
    }).toList();

    // Reverse to display newest at top if followLive is on
    final displayEvents = _followLive
        ? filteredEvents.reversed.toList()
        : filteredEvents;

    return Container(
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header with Title & Filter Chips
          Padding(
            padding: const EdgeInsets.all(ClairSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: ClairSpacing.sm,
                  runSpacing: ClairSpacing.xs,
                  children: [
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.timeline, size: 18, color: tokens.accent),
                        const SizedBox(width: ClairSpacing.xs),
                        Text(
                          'Attack Timeline',
                          style: TextStyle(
                            fontSize: ClairTypography.h3,
                            fontWeight: FontWeight.w600,
                            color: tokens.textPrimary,
                          ),
                        ),
                      ],
                    ),
                    // Follow Live toggle
                    InkWell(
                      onTap: () => setState(() => _followLive = !_followLive),
                      borderRadius: BorderRadius.circular(ClairRadius.sm),
                      child: Padding(
                        padding: ClairInsets.xSmY3,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              _followLive
                                  ? Icons.radio_button_checked
                                  : Icons.radio_button_unchecked,
                              size: 14,
                              color: _followLive ? tokens.success : tokens.textMuted,
                            ),
                            const SizedBox(width: ClairSpacing.xxs),
                            Text(
                              'Follow live',
                              style: TextStyle(
                                fontSize: ClairTypography.caption,
                                color: _followLive
                                    ? tokens.textPrimary
                                    : tokens.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: ClairSpacing.xs),
                Text(
                  'Chronological feed of agent activities, targeted tests, oracle decisions, and verified fixes.',
                  style: TextStyle(
                    fontSize: ClairTypography.small,
                    color: tokens.textSecondary,
                  ),
                ),
                const SizedBox(height: ClairSpacing.sm),
                // Filter chips
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      'all',
                      'builder',
                      'attacker',
                      'evaluator',
                      'fixer',
                      'verifier',
                    ].map((agent) {
                      final isSelected = _agentFilter == agent;
                      final label = agent == 'all'
                          ? 'All Events'
                          : agent.substring(0, 1).toUpperCase() + agent.substring(1);
                      return Padding(
                        padding: const EdgeInsets.only(right: ClairSpacing.xs),
                        child: InkWell(
                          onTap: () => setState(() => _agentFilter = agent),
                          borderRadius: BorderRadius.circular(ClairRadius.sm),
                          child: Container(
                            padding: ClairInsets.xSmY3,
                            decoration: BoxDecoration(
                              color: isSelected ? tokens.accentMuted : tokens.surfaceRaised,
                              borderRadius: BorderRadius.circular(ClairRadius.sm),
                              border: Border.all(
                                color: isSelected ? tokens.accent : tokens.border,
                              ),
                            ),
                            child: Text(
                              label,
                              style: TextStyle(
                                fontSize: ClairTypography.caption,
                                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                                color: isSelected ? tokens.accent : tokens.textSecondary,
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: tokens.border),
          // Event feed
          SizedBox(
            height: 380,
            child: displayEvents.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(ClairSpacing.lg),
                      child: Text(
                        'Waiting for agent activity...',
                        style: TextStyle(
                          fontSize: ClairTypography.body,
                          color: tokens.textMuted,
                        ),
                      ),
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xs),
                    itemCount: displayEvents.length,
                    itemBuilder: (context, index) {
                      final event = displayEvents[index];
                      final agentColor = _agentColor(event.agent, tokens);
                      final icon = _eventIcon(event.kind);
                      final isConfirmed = event.kind == 'finding_confirmed';
                      final ts = event.timestamp;
                      final timeStr =
                          '${ts.hour.toString().padLeft(2, '0')}:${ts.minute.toString().padLeft(2, '0')}:${ts.second.toString().padLeft(2, '0')}';
                      final findingId = event.refs['finding_id'] as String?;

                      return InkWell(
                        onTap: findingId != null && widget.onSelectFinding != null
                            ? () => widget.onSelectFinding!(findingId)
                            : null,
                        child: Container(
                          padding: ClairInsets.xMdYSm,
                          decoration: BoxDecoration(
                            color: isConfirmed && !isReduceMotion
                                ? tokens.critical.withValues(alpha: 0.08)
                                : Colors.transparent,
                            border: Border(
                              bottom: BorderSide(
                                color: tokens.border.withValues(alpha: 0.5),
                              ),
                            ),
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Icon & Agent tag
                              Container(
                                padding: const EdgeInsets.all(ClairSpacing.xxs),
                                decoration: BoxDecoration(
                                  color: agentColor.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                                ),
                                child: Icon(icon, size: 14, color: agentColor),
                              ),
                              const SizedBox(width: ClairSpacing.sm),
                              // Content
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          event.agent.toUpperCase(),
                                          style: TextStyle(
                                            fontSize: ClairTypography.caption,
                                            fontWeight: FontWeight.w700,
                                            color: agentColor,
                                            letterSpacing: 0.5,
                                          ),
                                        ),
                                        const SizedBox(width: ClairSpacing.xs),
                                        Expanded(
                                          child: Text(
                                            event.title,
                                            style: TextStyle(
                                              fontSize: ClairTypography.small,
                                              fontWeight: FontWeight.w600,
                                              color: isConfirmed
                                                  ? tokens.critical
                                                  : tokens.textPrimary,
                                            ),
                                            overflow: TextOverflow.ellipsis,
                                          ),
                                        ),
                                        Text(
                                          timeStr,
                                          style: TextStyle(
                                            fontSize: ClairTypography.caption,
                                            color: tokens.textMuted,
                                          ),
                                        ),
                                      ],
                                    ),
                                    if (event.plain.isNotEmpty) ...[
                                      const SizedBox(height: 2),
                                      Text(
                                        event.plain,
                                        style: TextStyle(
                                          fontSize: ClairTypography.small,
                                          color: tokens.textSecondary,
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
