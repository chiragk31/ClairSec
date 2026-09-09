import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// The four pipeline agents, in execution order.
enum AgentRole { builder, attacker, evaluator, fixer }

extension AgentRoleX on AgentRole {
  String get label => switch (this) {
        AgentRole.builder => 'Builder',
        AgentRole.attacker => 'Attacker',
        AgentRole.evaluator => 'Evaluator',
        AgentRole.fixer => 'Fixer',
      };

  IconData get icon => switch (this) {
        AgentRole.builder => Icons.search_outlined,
        AgentRole.attacker => Icons.bolt_outlined,
        AgentRole.evaluator => Icons.fact_check_outlined,
        AgentRole.fixer => Icons.build_outlined,
      };
}

/// Mirrors the backend agent state machine (ARCHITECTURE.md §5) for a single
/// agent's slice of a scan. Never inferred client-side — always set from an
/// actual backend event.
enum AgentStatus { idle, running, completed, failed, skipped }

extension AgentStatusX on AgentStatus {
  String get label => switch (this) {
        AgentStatus.idle => 'Waiting',
        AgentStatus.running => 'Running',
        AgentStatus.completed => 'Completed',
        AgentStatus.failed => 'Failed',
        AgentStatus.skipped => 'Skipped',
      };

  IconData get icon => switch (this) {
        AgentStatus.idle => Icons.radio_button_unchecked,
        AgentStatus.running => Icons.autorenew,
        AgentStatus.completed => Icons.check_circle_outline,
        AgentStatus.failed => Icons.error_outline,
        AgentStatus.skipped => Icons.remove_circle_outline,
      };

  Color get color => switch (this) {
        AgentStatus.idle => AppColors.textDisabled,
        AgentStatus.running => AppColors.accent,
        AgentStatus.completed => SeverityColors.success,
        AgentStatus.failed => SeverityColors.error,
        AgentStatus.skipped => AppColors.textDisabled,
      };
}

/// State for one agent card. `progress` is null whenever the backend has not
/// reported a measurable value — RULES.md §6 forbids faking progress bars, so
/// the UI must render "no bar" rather than an animated placeholder.
class AgentCardState {
  final AgentRole role;
  final AgentStatus status;
  final String? currentTask;
  final double? progress; // 0.0–1.0, or null if not measurable
  final int eventCount;
  final Duration elapsed;

  const AgentCardState({
    required this.role,
    this.status = AgentStatus.idle,
    this.currentTask,
    this.progress,
    this.eventCount = 0,
    this.elapsed = Duration.zero,
  });

  static AgentCardState idleFor(AgentRole role) => AgentCardState(role: role);
}

enum ScanEventLevel { info, warning, error }

/// One entry in the live event stream. Backed by `agent_events` server-side
/// (DATA_MODEL.md §3) — `seq` is the ordering/gap-detection key on reconnect.
class ScanEventEntry {
  final int seq;
  final DateTime timestamp;
  final AgentRole agent;
  final ScanEventLevel level;
  final String message;

  const ScanEventEntry({
    required this.seq,
    required this.timestamp,
    required this.agent,
    required this.message,
    this.level = ScanEventLevel.info,
  });
}

/// Rollup counters shown beneath the agent cards (DESIGN.md §6).
class ScanRunSummary {
  final int endpointsDiscovered;
  final int testsExecuted;
  final int findingsDiscovered;
  final int findingsConfirmed;
  final int fixesGenerated;
  final int fixesVerified;

  const ScanRunSummary({
    this.endpointsDiscovered = 0,
    this.testsExecuted = 0,
    this.findingsDiscovered = 0,
    this.findingsConfirmed = 0,
    this.fixesGenerated = 0,
    this.fixesVerified = 0,
  });
}

/// Full state for the live scan screen. `null` (not this class) is the
/// "no live connection" case — see ScanDetailScreen's empty state.
class ScanDetailState {
  final String scanId;
  final Map<AgentRole, AgentCardState> agentCards;
  final List<ScanEventEntry> events;
  final ScanRunSummary summary;

  const ScanDetailState({
    required this.scanId,
    required this.agentCards,
    this.events = const [],
    this.summary = const ScanRunSummary(),
  });

  AgentCardState cardFor(AgentRole role) =>
      agentCards[role] ?? AgentCardState.idleFor(role);

  /// True once no agent can still change state, so live polling can stop.
  bool get isTerminal => agentCards.values.every(
        (c) =>
            c.status == AgentStatus.completed ||
            c.status == AgentStatus.failed ||
            c.status == AgentStatus.skipped,
      );
}
