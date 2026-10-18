import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/tokens.dart';
import '../../models/project.dart';
import '../../providers/projects_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';
import 'widgets/autopilot_dialog.dart';
import 'widgets/import_project_dialog.dart';
import 'widgets/isolation_controls.dart';

class ProjectsScreen extends ConsumerWidget {
  const ProjectsScreen({super.key});

  Future<void> _handleImport(BuildContext context, WidgetRef ref) async {
    final imported = await showDialog<bool>(
      context: context,
      builder: (_) => const ImportProjectDialog(),
    );
    if (imported == true && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Project imported successfully')),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tokens = context.tokens;
    final projectsAsync = ref.watch(projectsProvider);

    return Scaffold(
      backgroundColor: tokens.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          PageHeader(
            title: 'Projects',
            subtitle: 'Manage imported FastAPI projects',
            actions: [
              FilledButton.icon(
                onPressed: () => _handleImport(context, ref),
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Import Project'),
              ),
            ],
          ),
          Expanded(
            child: projectsAsync.when(
              data: (projects) {
                if (projects.isEmpty) {
                  return EmptyState(
                    icon: Icons.folder_open,
                    title: 'No projects imported',
                    description: 'Import a FastAPI project to begin vulnerability scanning.',
                    action: FilledButton.icon(
                      onPressed: () => _handleImport(context, ref),
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('Import Project'),
                    ),
                  );
                }

                return ListView.separated(
                  padding: const EdgeInsets.all(ClairSpacing.xl),
                  itemCount: projects.length,
                  separatorBuilder: (context, index) => const SizedBox(height: ClairSpacing.lg),
                  itemBuilder: (context, index) {
                    final project = projects[index];
                    return _ProjectCard(project: project);
                  },
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, stack) => Center(
                child: Text('Error loading projects: $err'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProjectCard extends StatelessWidget {
  final ProjectRecord project;

  const _ProjectCard({required this.project});

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final isValid = project.validationStatus == 'valid';

    return Container(
      padding: const EdgeInsets.all(ClairSpacing.lg),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
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
                  Icon(
                    isValid ? Icons.check_circle : Icons.error,
                    color: isValid ? tokens.success : tokens.critical,
                    size: 20,
                  ),
                  const SizedBox(width: ClairSpacing.sm),
                  Text(
                    project.name,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
              if (project.isolationReady)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.sm, vertical: ClairSpacing.xs),
                  decoration: BoxDecoration(
                    color: tokens.success.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(ClairRadius.sm),
                    border: Border.all(color: tokens.success.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.shield_outlined, size: 12, color: tokens.success),
                      const SizedBox(width: ClairSpacing.xs),
                      Flexible(
                        child: Text(
                          'Ready for isolation',
                          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: tokens.success,
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: ClairSpacing.sm),
          Text(
            project.sourcePath,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: tokens.textSecondary,
              fontFamily: 'JetBrainsMono',
            ),
          ),
          const SizedBox(height: ClairSpacing.lg),
          Divider(height: 1, color: tokens.border),
          const SizedBox(height: ClairSpacing.lg),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _InfoSection(
                  title: 'Entry Point',
                  content: project.entryPoint ?? 'Not detected',
                  isError: !isValid && project.entryPoint == null,
                ),
              ),
              Expanded(
                child: _InfoSection(
                  title: 'Dependencies',
                  content: project.dependencyFile != null
                      ? '${project.dependencyFile} (${project.dependencies.length} packages)'
                      : 'Dependency manifest not detected',
                  isError: false,
                ),
              ),
            ],
          ),
          if (project.importNotes.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.md),
            Container(
              padding: const EdgeInsets.all(ClairSpacing.md),
              decoration: BoxDecoration(
                color: tokens.info.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(ClairRadius.sm),
                border: Border.all(color: tokens.info.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.info_outline, size: 14, color: tokens.info),
                      const SizedBox(width: ClairSpacing.xs),
                      Text(
                        'Import Notes',
                        style: TextStyle(
                          fontSize: ClairTypography.caption,
                          fontWeight: FontWeight.w600,
                          color: tokens.info,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xs),
                  for (final note in project.importNotes)
                    Padding(
                      padding: const EdgeInsets.only(bottom: ClairSpacing.xxs),
                      child: Text(
                        '• $note',
                        style: TextStyle(
                          fontSize: ClairTypography.caption,
                          color: tokens.textSecondary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
          if (project.exposedSecrets.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.md),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(ClairSpacing.md),
              decoration: BoxDecoration(
                color: tokens.danger.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(ClairRadius.sm),
                border: Border.all(color: tokens.danger.withValues(alpha: 0.35)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.key_off, size: 14, color: tokens.danger),
                      const SizedBox(width: ClairSpacing.xs),
                      Expanded(
                        child: Text(
                          'Exposed secrets (${project.exposedSecrets.length}) — values masked, rotate them',
                          style: TextStyle(
                            fontSize: ClairTypography.caption,
                            fontWeight: FontWeight.w600,
                            color: tokens.danger,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xs),
                  for (final s in project.exposedSecrets.take(8))
                    Text(
                      '${s['type']} · ${s['file']}:${s['line']} · ${s['preview']}',
                      style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary),
                    ),
                ],
              ),
            ),
          ],
          if (isValid) ...[
            const SizedBox(height: ClairSpacing.lg),
            Divider(height: 1, color: tokens.border),
            const SizedBox(height: ClairSpacing.md),
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: ClairSpacing.md,
              runSpacing: ClairSpacing.sm,
              children: [
                FilledButton.icon(
                  onPressed: () => showDialog(
                    context: context,
                    builder: (_) => AutopilotDialog(project: project),
                  ),
                  icon: const Icon(Icons.bolt, size: 16),
                  label: const Text('Run full check'),
                ),
                IsolationControls(
                  projectId: project.id,
                  isolationReady: project.isolationReady,
                ),
              ],
            ),
          ],
          if (!isValid && project.validationErrors.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.lg),
            Container(
              padding: const EdgeInsets.all(ClairSpacing.md),
              decoration: BoxDecoration(
                color: tokens.critical.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(ClairRadius.sm),
                border: Border.all(color: tokens.critical.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.warning_amber_rounded, size: 16, color: tokens.critical),
                      const SizedBox(width: ClairSpacing.sm),
                      Text(
                        'Validation Failed',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: tokens.critical,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.sm),
                  ...project.validationErrors.map(
                    (err) => Padding(
                      padding: const EdgeInsets.only(bottom: ClairSpacing.xs),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('• ', style: TextStyle(color: tokens.critical)),
                          Expanded(
                            child: Text(
                              err,
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: tokens.critical,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _InfoSection extends StatelessWidget {
  final String title;
  final String content;
  final bool isError;

  const _InfoSection({
    required this.title,
    required this.content,
    this.isError = false,
  });

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: tokens.textMuted,
          ),
        ),
        const SizedBox(height: ClairSpacing.xs),
        Text(
          content,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: isError ? tokens.critical : tokens.textPrimary,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
