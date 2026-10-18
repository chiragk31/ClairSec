import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/theme/tokens.dart';
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
    final tokens = context.tokens;

    return Container(
      decoration: BoxDecoration(
        color: tokens.bg,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // File header
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(
              horizontal: ClairSpacing.md,
              vertical: ClairSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: tokens.surfaceRaised,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(ClairRadius.md - 1)),
            ),
            child: Row(
              children: [
                Icon(Icons.insert_drive_file_outlined,
                    size: 13, color: tokens.textSecondary),
                const SizedBox(width: ClairSpacing.xs),
                Expanded(
                  child: Text(
                    fileDiff.path,
                    style: AppTheme.monoStyle(
                      fontSize: ClairTypography.small,
                      color: tokens.textPrimary,
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
    final tokens = context.tokens;

    return Tooltip(
      message: _copied ? 'Copied' : 'Copy diff',
      child: InkWell(
        onTap: _copy,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        child: Padding(
          padding: ClairInsets.x6Y3,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _copied ? Icons.check : Icons.copy_all_outlined,
                size: 13,
                color: _copied ? tokens.success : tokens.textSecondary,
              ),
              const SizedBox(width: ClairSpacing.xs),
              Text(
                _copied ? 'Copied' : 'Copy',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: _copied ? tokens.success : tokens.textSecondary,
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

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    final (bg, fg) = switch (line.kind) {
      DiffLineKind.addition => (tokens.diffAddBg, tokens.success),
      DiffLineKind.removal => (tokens.diffRemoveBg, tokens.critical),
      DiffLineKind.hunk => (tokens.diffHunkBg, tokens.accent),
      DiffLineKind.meta => (Colors.transparent, tokens.textMuted),
      DiffLineKind.context => (Colors.transparent, tokens.textSecondary),
    };

    return Container(
      width: double.infinity,
      color: bg,
      padding: ClairInsets.diffLine,
      child: Text(
        line.text.isEmpty ? ' ' : line.text,
        style: AppTheme.monoStyle(fontSize: ClairTypography.small, color: fg),
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
    final tokens = context.tokens;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '+${stats.added}',
          style: AppTheme.monoStyle(
            fontSize: ClairTypography.small,
            color: tokens.success,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: ClairSpacing.sm),
        Text(
          '−${stats.removed}',
          style: AppTheme.monoStyle(
            fontSize: ClairTypography.small,
            color: tokens.critical,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: ClairSpacing.sm),
        Text(
          '${stats.files} file${stats.files == 1 ? '' : 's'}',
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ],
    );
  }
}
