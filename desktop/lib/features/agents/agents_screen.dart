import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PageHeader(
            title: 'Agents',
            subtitle: 'Inspect agent activity across scans',
          ),
          Expanded(child: _AgentsContent()),
        ],
      ),
    );
  }
}

class _AgentsContent extends StatelessWidget {
  const _AgentsContent();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AgentRoleCards(),
          const SizedBox(height: 24),
          const Expanded(
            child: EmptyState(
              icon: Icons.smart_toy_outlined,
              title: 'No agent activity',
              description:
                  'Structured agent events — tasks, actions, results, and '
                  'durations — will appear here during and after a scan. '
                  'Raw chain-of-thought is not exposed.',
            ),
          ),
        ],
      ),
    );
  }
}

class _AgentRoleCards extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    const agents = [
      _AgentRoleCard(
        name: 'Builder',
        icon: Icons.search_outlined,
        role: 'Understand the target',
        description: 'Inspects project structure, discovers routes and auth mechanisms, extracts OpenAPI context.',
      ),
      _AgentRoleCard(
        name: 'Attacker',
        icon: Icons.bolt_outlined,
        role: 'Challenge the target',
        description: 'Selects test categories, generates controlled payloads, records request/response evidence.',
      ),
      _AgentRoleCard(
        name: 'Evaluator',
        icon: Icons.fact_check_outlined,
        role: 'Validate independently',
        description: 'Reviews attacker evidence, reproduces candidates, filters false positives, assigns severity.',
      ),
      _AgentRoleCard(
        name: 'Fixer',
        icon: Icons.build_outlined,
        role: 'Remediate findings',
        description: 'Generates minimal source patches, applies them only to the isolated workspace, triggers re-test.',
      ),
    ];

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: agents,
    );
  }
}

class _AgentRoleCard extends StatelessWidget {
  final String name;
  final IconData icon;
  final String role;
  final String description;

  const _AgentRoleCard({
    required this.name,
    required this.icon,
    required this.role,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 16, color: AppColors.accent),
                const SizedBox(width: 8),
                Text(name, style: Theme.of(context).textTheme.headlineMedium),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              role.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: AppColors.accent,
                    letterSpacing: 0.8,
                  ),
            ),
            const SizedBox(height: 8),
            Text(description, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
