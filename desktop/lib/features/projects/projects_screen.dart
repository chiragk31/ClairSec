import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:file_picker/file_picker.dart' as fp;
import '../../core/theme/app_theme.dart';
import '../../models/project.dart';
import '../../providers/projects_provider.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class ProjectsScreen extends ConsumerWidget {
  const ProjectsScreen({super.key});

  Future<void> _handleImport(BuildContext context, WidgetRef ref) async {
    final String? selectedDirectory = await fp.FilePicker.getDirectoryPath(
      dialogTitle: 'Select FastAPI Project Folder',
    );

    if (selectedDirectory != null) {
      try {
        await ref.read(projectsProvider.notifier).importProject(selectedDirectory);
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Project imported successfully')),
          );
        }
      } catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to import project: $e'),
              backgroundColor: SeverityColors.error,
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectsAsync = ref.watch(projectsProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
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
                  return Padding(
                    padding: const EdgeInsets.all(24),
                    child: EmptyState(
                      icon: Icons.folder_open_outlined,
                      title: 'No projects imported',
                      description:
                          'Import a local FastAPI project to begin. ClairSec will validate '
                          'the project, create an isolated scan workspace, and run a '
                          'controlled security assessment.',
                      action: FilledButton.icon(
                        onPressed: () => _handleImport(context, ref),
                        icon: const Icon(Icons.add, size: 16),
                        label: const Text('Import Project'),
                      ),
                    ),
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.all(24),
                  itemCount: projects.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 16),
                  itemBuilder: (context, index) => _ProjectCard(project: projects[index]),
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, stack) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: EmptyState(
                    icon: Icons.error_outline,
                    title: 'Error loading projects',
                    description: err.toString(),
                  ),
                ),
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
    final isValid = project.validationStatus == 'valid';

    return Container(
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
              Icon(
                isValid ? Icons.check_circle : Icons.error,
                color: isValid ? SeverityColors.success : SeverityColors.error,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  project.name,
                  style: AppTheme.dark.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (project.isolationReady)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: SeverityColors.success.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: SeverityColors.success.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.shield_outlined, size: 12, color: SeverityColors.success),
                      const SizedBox(width: 4),
                      Text(
                        'Appears ready for isolation',
                        style: AppTheme.dark.textTheme.labelSmall?.copyWith(
                          color: SeverityColors.success,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            project.sourcePath,
            style: AppTheme.dark.textTheme.bodySmall?.copyWith(
              color: AppColors.textSecondary,
              fontFamily: 'JetBrainsMono',
            ),
          ),
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 16),
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
          if (!isValid && project.validationErrors.isNotEmpty) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: SeverityColors.error.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: SeverityColors.error.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.warning_amber_rounded, size: 16, color: SeverityColors.error),
                      const SizedBox(width: 8),
                      Text(
                        'Validation Failed',
                        style: AppTheme.dark.textTheme.titleSmall?.copyWith(
                          color: SeverityColors.error,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ...project.validationErrors.map(
                    (err) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('• ', style: TextStyle(color: SeverityColors.error)),
                          Expanded(
                            child: Text(
                              err,
                              style: AppTheme.dark.textTheme.bodySmall?.copyWith(
                                color: SeverityColors.error,
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: AppTheme.dark.textTheme.labelSmall?.copyWith(
            color: AppColors.textDisabled,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          content,
          style: AppTheme.dark.textTheme.bodyMedium?.copyWith(
            color: isError ? SeverityColors.error : AppColors.textPrimary,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
