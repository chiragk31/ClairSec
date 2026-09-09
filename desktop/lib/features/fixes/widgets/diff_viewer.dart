import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/patch.dart';

/// Renders a unified diff with colour-coded additions/removals.
///
/// This is what the user reviews before any fix is trusted (SECURITY.md §7 —
/// "Provide a diff before applying a fix"), so it shows the real patch text
/// verbatim rather than a summary.
class DiffViewer extends StatelessWidget {
  final FileDiff fileDiff;

  const DiffViewer({super.key, required this.fileDiff});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // File header
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: const BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: BorderRadius.vertical(top: Radius.circular(7)),
            ),
            child: Row(
              children: [
                const Icon(Icons.insert_drive_file_outlined,
                    size: 13, color: AppColors.textSecondary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    fileDiff.path,
                    style: AppTheme.monoStyle(
                      fontSize: 12,
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                _CopyDiffButton(diff: fileDiff.diff),
              ],
            ),
          ),
          // Diff body — horizontally scrollable so long lines never wrap
          // (wrapped code is unreadable and misrepresents the patch).
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 600),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final line in fileDiff.lines) _DiffLineRow(line: line),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Copies the raw unified diff so it can be pasted into a review tool or
/// applied manually with `git apply`.
class _CopyDiffButton extends StatefulWidget {
  final String diff;
  const _CopyDiffButton({required this.diff});

  @override
  State<_CopyDiffButton> createState() => _CopyDiffButtonState();
}

class _CopyDiffButtonState extends State<_CopyDiffButton> {
  bool _copied = false;

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.diff));
    if (!mounted) return;
    setState(() => _copied = true);
    await Future<void>.delayed(const Duration(seconds: 2));
    if (mounted) setState(() => _copied = false);
  }

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: _copied ? 'Copied' : 'Copy diff',
      child: InkWell(
        onTap: _copy,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _copied ? Icons.check : Icons.copy_all_outlined,
                size: 13,
                color: _copied ? SeverityColors.success : AppColors.textSecondary,
              ),
              const SizedBox(width: 4),
              Text(
                _copied ? 'Copied' : 'Copy',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color:
                          _copied ? SeverityColors.success : AppColors.textSecondary,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DiffLineRow extends StatelessWidget {
  final DiffLine line;
  const _DiffLineRow({required this.line});

  static const _addBg = Color(0x2643D68C);
  static const _removeBg = Color(0x26FF3B3B);
  static const _hunkBg = Color(0x1A58A6FF);

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (line.kind) {
      DiffLineKind.addition => (_addBg, SeverityColors.success),
      DiffLineKind.removal => (_removeBg, SeverityColors.critical),
      DiffLineKind.hunk => (_hunkBg, AppColors.accent),
      DiffLineKind.meta => (Colors.transparent, AppColors.textDisabled),
      DiffLineKind.context => (Colors.transparent, AppColors.textSecondary),
    };

    return Container(
      width: double.infinity,
      color: bg,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 1.5),
      child: Text(
        line.text.isEmpty ? ' ' : line.text,
        style: AppTheme.monoStyle(fontSize: 12, color: fg),
        softWrap: false,
      ),
    );
  }
}

/// Compact +N / −N summary chip.
class DiffStatsChip extends StatelessWidget {
  final DiffStats stats;
  const DiffStatsChip({super.key, required this.stats});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '+${stats.added}',
          style: AppTheme.monoStyle(
            fontSize: 12,
            color: SeverityColors.success,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          '−${stats.removed}',
          style: AppTheme.monoStyle(
            fontSize: 12,
            color: SeverityColors.critical,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: 8),
        Text(
          '${stats.files} file${stats.files == 1 ? '' : 's'}',
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ],
    );
  }
}
