import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/tokens.dart';
import '../../../providers/projects_provider.dart';
import '../../../services/url_validator.dart';
import '../../../ui/components/cs_stepper.dart';
import '../../../ui/components/file_tree.dart';

enum ImportType { local, github, demo }

class ImportProjectDialog extends ConsumerStatefulWidget {
  const ImportProjectDialog({
    super.key,
    this.initialType = ImportType.local,
  });

  final ImportType initialType;

  @override
  ConsumerState<ImportProjectDialog> createState() => _ImportProjectDialogState();
}

class _ImportProjectDialogState extends ConsumerState<ImportProjectDialog> {
  late ImportType _selectedType;

  @override
  void initState() {
    super.initState();
    _selectedType = widget.initialType;
  }

  // Local folder state
  String? _localPath;

  // GitHub import state
  final TextEditingController _urlController = TextEditingController();
  final TextEditingController _refController = TextEditingController();
  final TextEditingController _subdirController = TextEditingController();
  bool _authorized = false;
  String? _urlError;

  // Progress state
  bool _isImporting = false;
  List<StepData> _steps = [];
  List<FileNode> _previewTree = [];
  List<String> _importNotes = [];
  String? _importError;

  @override
  void dispose() {
    _urlController.dispose();
    _refController.dispose();
    _subdirController.dispose();
    super.dispose();
  }

  void _validateUrl(String value) {
    if (value.trim().isEmpty) {
      setState(() => _urlError = null);
      return;
    }
    final res = GitUrlValidator.validate(value, ref: _refController.text);
    setState(() => _urlError = res.isValid ? null : res.error);
  }

  Future<void> _pickLocalFolder() async {
    final result = await FilePicker.getDirectoryPath(
      dialogTitle: 'Select FastAPI Project Root',
    );
    if (result != null) {
      setState(() => _localPath = result);
    }
  }

  Future<void> _executeLocalImport() async {
    if (_localPath == null) return;
    setState(() => _isImporting = true);
    try {
      await ref.read(projectsProvider.notifier).importProject(_localPath!);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      setState(() {
        _isImporting = false;
        _importError = e.toString();
      });
    }
  }

  Future<void> _executeDemoImport(String fixture) async {
    setState(() {
      _isImporting = true;
      _importError = null;
    });
    try {
      final service = ref.read(projectsServiceProvider);
      await service.importDemoProject(fixture: fixture);
      await ref.read(projectsProvider.notifier).refresh();
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      setState(() {
        _isImporting = false;
        _importError = e.toString();
      });
    }
  }

  Future<void> _executeGitImport() async {
    final url = _urlController.text.trim();
    final res = GitUrlValidator.validate(url, ref: _refController.text);
    if (!res.isValid) {
      setState(() => _urlError = res.error);
      return;
    }

    if (!_authorized) {
      setState(() => _importError = 'You must affirm authorization before importing.');
      return;
    }

    setState(() {
      _isImporting = true;
      _importError = null;
      _steps = [
        const StepData(title: 'Checking URL', plainLanguage: 'Validating GitHub repo format', status: CsStepStatus.running),
        const StepData(title: 'Fetching repository', plainLanguage: 'Downloading archive or cloning', status: CsStepStatus.pending),
        const StepData(title: 'Extracting files', plainLanguage: 'Safe extraction with data filter', status: CsStepStatus.pending),
        const StepData(title: 'Validating FastAPI application', plainLanguage: 'Detecting entry point and dependencies', status: CsStepStatus.pending),
        const StepData(title: 'Ready', plainLanguage: 'Structure preview available', status: CsStepStatus.pending),
      ];
    });

    final service = ref.read(projectsServiceProvider);
    try {
      final importRes = await service.importGitProject(
        url: url,
        ref: _refController.text.trim().isEmpty ? null : _refController.text.trim(),
        subdir: _subdirController.text.trim().isEmpty ? null : _subdirController.text.trim(),
        authorizationAffirmed: _authorized,
      );

      final projectId = importRes['project_id'] as String;
      final jobId = importRes['job_id'] as String?;

      // Wait for the REAL import job (download, extraction, validation) instead of
      // marking every step done immediately: the project only exists once it finishes.
      setState(() => _steps = [
            const StepData(title: 'Checking URL', status: CsStepStatus.completed),
            const StepData(title: 'Fetching repository', plainLanguage: 'Downloading and checking the archive', status: CsStepStatus.running),
            const StepData(title: 'Extracting files', status: CsStepStatus.pending),
            const StepData(title: 'Validating FastAPI application', status: CsStepStatus.pending),
            const StepData(title: 'Ready', status: CsStepStatus.pending),
          ]);
      if (jobId != null) {
        for (var i = 0; i < 600; i++) {
          final job = await service.getJob(jobId);
          final status = (job['status'] ?? '').toString();
          if (status == 'completed' || status == 'succeeded') break;
          if (status == 'failed' || status == 'cancelled' || status == 'interrupted') {
            throw Exception((job['error'] ?? 'Import $status').toString());
          }
          await Future<void>.delayed(const Duration(milliseconds: 700));
          if (!mounted) return;
        }
      }
      final project = await service.getProjectJson(projectId);
      if ((project['validation_status'] ?? '') != 'valid') {
        final errs = (project['validation_errors'] as List? ?? const []).join('; ');
        throw Exception('Downloaded, but not a runnable FastAPI project: $errs');
      }
      final rawNotes = project['import_notes'] ?? importRes['import_notes'];
      final notesList = rawNotes is List ? rawNotes.map((n) => n.toString()).toList() : <String>[];

      setState(() {
        _importNotes = notesList;
        _steps = [
          const StepData(title: 'Checking URL', status: CsStepStatus.completed),
          const StepData(title: 'Fetching repository', status: CsStepStatus.completed),
          const StepData(title: 'Extracting files', status: CsStepStatus.completed),
          const StepData(title: 'Validating FastAPI application', status: CsStepStatus.completed),
          const StepData(title: 'Ready', plainLanguage: 'Project successfully imported', status: CsStepStatus.completed),
        ];
      });

      // Fetch file tree preview
      try {
        final treeData = await service.getProjectTree(projectId, depth: 3);
        final nodes = _parseFileTree(treeData);
        setState(() => _previewTree = nodes);
      } catch (_) {}

      await ref.read(projectsProvider.notifier).refresh();
    } catch (e) {
      setState(() {
        _isImporting = false;
        _importError = e.toString();
        _steps = [
          ..._steps.where((s) => s.status == CsStepStatus.completed),
          StepData(title: 'Import failed', status: CsStepStatus.failed, error: e.toString()),
        ];
      });
    }
  }

  List<FileNode> _parseFileTree(Map<String, dynamic> data) {
    final children = (data['children'] as List<dynamic>? ?? []).map((c) {
      final childMap = Map<String, dynamic>.from(c as Map);
      return FileNode(
        name: childMap['name'] as String? ?? '',
        isDirectory: childMap['type'] == 'directory',
        sizeBytes: childMap['size'] as int?,
        children: childMap['children'] != null ? _parseFileTree(childMap) : const [],
      );
    }).toList();

    return [
      FileNode(
        name: data['name'] as String? ?? 'root',
        isDirectory: true,
        children: children,
      )
    ];
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Dialog(
      backgroundColor: tokens.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ClairRadius.lg),
        side: BorderSide(color: tokens.border),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 640,
          maxHeight: (MediaQuery.sizeOf(context).height * 0.9).clamp(320.0, 720.0),
        ),
        child: Padding(
          padding: const EdgeInsets.all(ClairSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Import Project',
                    style: TextStyle(
                      fontSize: ClairTypography.h2,
                      fontWeight: FontWeight.w700,
                      color: tokens.textPrimary,
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: Icon(Icons.close, color: tokens.textSecondary, size: 20),
                  ),
                ],
              ),
              const SizedBox(height: ClairSpacing.md),

              // Segmented selector
              SegmentedButton<ImportType>(
                segments: const [
                  ButtonSegment(
                    value: ImportType.local,
                    label: Text('Local folder'),
                    icon: Icon(Icons.folder_open, size: 16),
                  ),
                  ButtonSegment(
                    value: ImportType.github,
                    label: Text('GitHub URL'),
                    icon: Icon(Icons.link, size: 16),
                  ),
                  ButtonSegment(
                    value: ImportType.demo,
                    label: Text('Demo app'),
                    icon: Icon(Icons.play_circle_outline, size: 16),
                  ),
                ],
                selected: {_selectedType},
                onSelectionChanged: (set) {
                  setState(() {
                    _selectedType = set.first;
                    _importError = null;
                  });
                },
              ),
              const SizedBox(height: ClairSpacing.lg),

              // Body based on segment
              Expanded(
                child: SingleChildScrollView(
                  child: _buildSegmentContent(tokens),
                ),
              ),

              // Footer
              if (!_isImporting || _previewTree.isNotEmpty) ...[
                const SizedBox(height: ClairSpacing.md),
                Divider(height: 1, color: tokens.border),
                const SizedBox(height: ClairSpacing.md),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Cancel'),
                    ),
                    const SizedBox(width: ClairSpacing.sm),
                    if (_previewTree.isNotEmpty)
                      FilledButton(
                        onPressed: () => Navigator.of(context).pop(true),
                        child: const Text('Done'),
                      )
                    else if (_selectedType == ImportType.local)
                      FilledButton(
                        onPressed: _localPath != null ? _executeLocalImport : null,
                        child: const Text('Import Local Folder'),
                      )
                    else if (_selectedType == ImportType.github)
                      FilledButton(
                        onPressed: (_urlError == null &&
                                _urlController.text.isNotEmpty &&
                                _authorized)
                            ? _executeGitImport
                            : null,
                        child: const Text('Import Repository'),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSegmentContent(ClairTokens tokens) {
    if (_steps.isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CsStepper(steps: _steps),
          if (_previewTree.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.lg),
            Text(
              'File Structure Preview',
              style: TextStyle(
                fontSize: ClairTypography.h3,
                fontWeight: FontWeight.w600,
                color: tokens.textPrimary,
              ),
            ),
            const SizedBox(height: ClairSpacing.xs),
            Container(
              padding: const EdgeInsets.all(ClairSpacing.md),
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                borderRadius: BorderRadius.circular(ClairRadius.md),
                border: Border.all(color: tokens.border),
              ),
              constraints: const BoxConstraints(maxHeight: 220),
              child: SingleChildScrollView(
                child: FileTree(nodes: _previewTree),
              ),
            ),
          ],
          if (_importNotes.isNotEmpty) ...[
            const SizedBox(height: ClairSpacing.md),
            Text(
              'Import Notes (${_importNotes.length})',
              style: TextStyle(
                fontSize: ClairTypography.caption,
                fontWeight: FontWeight.w600,
                color: tokens.textSecondary,
              ),
            ),
            const SizedBox(height: ClairSpacing.xs),
            ..._importNotes.map(
              (n) => Padding(
                padding: const EdgeInsets.only(bottom: ClairSpacing.xxs),
                child: Text('• $n', style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textMuted)),
              ),
            ),
          ],
          if (_importError != null) ...[
            const SizedBox(height: ClairSpacing.md),
            Text(_importError!, style: TextStyle(color: tokens.critical)),
          ],
        ],
      );
    }

    switch (_selectedType) {
      case ImportType.local:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Select a directory containing a FastAPI application.',
              style: TextStyle(fontSize: ClairTypography.body, color: tokens.textSecondary),
            ),
            const SizedBox(height: ClairSpacing.md),
            OutlinedButton.icon(
              onPressed: _pickLocalFolder,
              icon: const Icon(Icons.folder_open, size: 16),
              label: Text(_localPath == null ? 'Browse Folder...' : _localPath!),
            ),
            if (_importError != null) ...[
              const SizedBox(height: ClairSpacing.sm),
              Text(_importError!, style: TextStyle(color: tokens.critical)),
            ],
          ],
        );

      case ImportType.github:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _urlController,
              decoration: InputDecoration(
                labelText: 'GitHub Repository URL',
                hintText: 'https://github.com/owner/repo',
                errorText: _urlError,
                prefixIcon: const Icon(Icons.link, size: 18),
              ),
              onChanged: _validateUrl,
            ),
            const SizedBox(height: ClairSpacing.md),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _refController,
                    decoration: const InputDecoration(
                      labelText: 'Branch / Tag / Commit (optional)',
                      hintText: 'main',
                    ),
                    onChanged: (v) => _validateUrl(_urlController.text),
                  ),
                ),
                const SizedBox(width: ClairSpacing.md),
                Expanded(
                  child: TextField(
                    controller: _subdirController,
                    decoration: const InputDecoration(
                      labelText: 'Subdirectory (monorepo)',
                      hintText: 'backend',
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: ClairSpacing.md),
            CheckboxListTile(
              value: _authorized,
              onChanged: (v) => setState(() => _authorized = v ?? false),
              title: Text(
                'I am authorised to test this code',
                style: TextStyle(fontSize: ClairTypography.body, color: tokens.textPrimary),
              ),
              subtitle: Text(
                'Required by ETHICS.md §1: Never test systems without authorization.',
                style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textMuted),
              ),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            if (_importError != null) ...[
              const SizedBox(height: ClairSpacing.sm),
              Text(_importError!, style: TextStyle(color: tokens.critical)),
            ],
          ],
        );

      case ImportType.demo:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Select a bundled demo application. Scans run immediately with mock intelligence even without Docker isolation.',
              style: TextStyle(fontSize: ClairTypography.body, color: tokens.textSecondary),
            ),
            const SizedBox(height: ClairSpacing.lg),
            // Card 1: Vulnerable Demo App
            Container(
              padding: const EdgeInsets.all(ClairSpacing.lg),
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                borderRadius: BorderRadius.circular(ClairRadius.md),
                border: Border.all(color: tokens.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.bug_report, size: 20, color: tokens.warning),
                      const SizedBox(width: ClairSpacing.sm),
                      Expanded(
                        child: Text(
                          'Demo: Vulnerable FastAPI App',
                          style: TextStyle(
                            fontSize: ClairTypography.h3,
                            fontWeight: FontWeight.w600,
                            color: tokens.textPrimary,
                          ),
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: _isImporting ? null : () => _executeDemoImport('vulnerable'),
                        icon: const Icon(Icons.play_arrow, size: 16),
                        label: const Text('Scan Demo'),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xs),
                  Text(
                    'Bundled fixture containing realistic BOLA, SQL/command injection, and broken authentication vulnerabilities. Verifies real exploit detection, AST patch synthesis, and regression checking.',
                    style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary),
                  ),
                ],
              ),
            ),
            const SizedBox(height: ClairSpacing.md),
            // Card 2: Trust Check (Secure App)
            Container(
              padding: const EdgeInsets.all(ClairSpacing.lg),
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                borderRadius: BorderRadius.circular(ClairRadius.md),
                border: Border.all(color: tokens.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.verified_user, size: 20, color: tokens.success),
                      const SizedBox(width: ClairSpacing.sm),
                      Expanded(
                        child: Text(
                          'Trust Check: Secure App',
                          style: TextStyle(
                            fontSize: ClairTypography.h3,
                            fontWeight: FontWeight.w600,
                            color: tokens.textPrimary,
                          ),
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: _isImporting ? null : () => _executeDemoImport('secure'),
                        icon: const Icon(Icons.check_circle_outline, size: 16),
                        label: const Text('Run Trust Check'),
                      ),
                    ],
                  ),
                  const SizedBox(height: ClairSpacing.xs),
                  Text(
                    'Reference correctly-secured FastAPI application. Runs full scanner suite and confirms zero false positives (0 confirmed findings).',
                    style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary),
                  ),
                ],
              ),
            ),
            if (_importError != null) ...[
              const SizedBox(height: ClairSpacing.md),
              Text(_importError!, style: TextStyle(color: tokens.critical)),
            ],
          ],
        );
    }
  }
}
