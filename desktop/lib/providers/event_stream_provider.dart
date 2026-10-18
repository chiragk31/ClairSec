import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/agent_event.dart';
import '../services/event_stream_client.dart';

final eventStreamClientProvider = Provider.family<EventStreamClient, String>((ref, scanId) {
  final client = EventStreamClient();
  client.connect(scanId);
  ref.onDispose(client.dispose);
  return client;
});

class ScanEventsNotifier extends Notifier<List<AgentEvent>> {
  @override
  List<AgentEvent> build() {
    return [];
  }

  void addEvent(AgentEvent event) {
    if (state.any((e) => e.seq == event.seq)) return;
    state = [...state, event]..sort((a, b) => a.seq.compareTo(b.seq));
  }

  void setEvents(List<AgentEvent> events) {
    state = [...events]..sort((a, b) => a.seq.compareTo(b.seq));
  }
}

final scanEventsProvider =
    NotifierProvider.family<ScanEventsNotifier, List<AgentEvent>, String>(
  (arg) => ScanEventsNotifier(),
);

/// Live stream provider that connects the client to the scanEventsProvider.
final scanEventStreamSubscriptionProvider =
    Provider.family<void, String>((ref, scanId) {
  final client = ref.watch(eventStreamClientProvider(scanId));
  final sub = client.stream.listen((event) {
    ref.read(scanEventsProvider(scanId).notifier).addEvent(event);
  });
  ref.onDispose(sub.cancel);
});

class LiveCounters {
  final int endpoints;
  final int testsExecuted;
  final int oracleHits;
  final int confirmed;
  final int patches;
  final int fixesVerified;

  const LiveCounters({
    this.endpoints = 0,
    this.testsExecuted = 0,
    this.oracleHits = 0,
    this.confirmed = 0,
    this.patches = 0,
    this.fixesVerified = 0,
  });
}

final scanLiveCountersProvider =
    Provider.family<LiveCounters, String>((ref, scanId) {
  final events = ref.watch(scanEventsProvider(scanId));

  int endpoints = 0;
  int tests = 0;
  int hits = 0;
  int confirmed = 0;
  int patches = 0;
  int verified = 0;

  for (final e in events) {
    switch (e.kind) {
      case 'endpoint_discovered':
        endpoints++;
        break;
      case 'request_sent':
        tests++;
        break;
      case 'oracle_fired':
        hits++;
        break;
      case 'finding_confirmed':
        confirmed++;
        break;
      case 'patch_proposed':
        patches++;
        break;
      case 'verification_result':
        if (e.title.toLowerCase().contains('fixed') ||
            e.detail.toLowerCase().contains('fixed')) {
          verified++;
        }
        break;
    }
  }

  return LiveCounters(
    endpoints: endpoints,
    testsExecuted: tests,
    oracleHits: hits,
    confirmed: confirmed,
    patches: patches,
    fixesVerified: verified,
  );
});

final scanBudgetProvider =
    Provider.family<Map<String, dynamic>?, String>((ref, scanId) {
  final events = ref.watch(scanEventsProvider(scanId));
  final budgetEvents = events.where((e) => e.kind == 'budget' && e.budget != null);
  if (budgetEvents.isEmpty) return null;
  return budgetEvents.last.budget;
});
