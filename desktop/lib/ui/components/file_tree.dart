import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

class FileNode {
  const FileNode({
    required this.name,
    this.isDirectory = false,
    this.sizeBytes,
    this.children = const [],
  });

  final String name;
  final bool isDirectory;
  final int? sizeBytes;
  final List<FileNode> children;
}

/// Collapsible file tree viewer with file-type icons and sizes (UI_SYSTEM.md §7).
class FileTree extends StatefulWidget {
  const FileTree({
    super.key,
    required this.nodes,
    this.onSelectFile,
  });

  final List<FileNode> nodes;
  final ValueChanged<FileNode>? onSelectFile;

  @override
  State<FileTree> createState() => _FileTreeState();
}

class _FileTreeState extends State<FileTree> {
  final Set<String> _expandedPaths = {};

  void _toggle(String path) {
    setState(() {
      if (_expandedPaths.contains(path)) {
        _expandedPaths.remove(path);
      } else {
        _expandedPaths.add(path);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final node in widget.nodes)
          _buildNode(node, '', 0),
      ],
    );
  }

  Widget _buildNode(FileNode node, String parentPath, int depth) {
    final path = parentPath.isEmpty ? node.name : '$parentPath/${node.name}';
    final isExpanded = _expandedPaths.contains(path);
    final tokens = context.tokens;

    final icon = node.isDirectory
        ? (isExpanded ? Icons.folder_open : Icons.folder)
        : (node.name.endsWith('.py')
            ? Icons.code
            : (node.name.endsWith('.json') || node.name.endsWith('.yaml') || node.name.endsWith('.toml')
                ? Icons.data_object
                : Icons.insert_drive_file_outlined));

    final iconColor = node.isDirectory
        ? tokens.accent
        : (node.name.endsWith('.py') ? tokens.warning : tokens.textSecondary);

    String sizeLabel(int bytes) {
      if (bytes < 1024) return '$bytes B';
      if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            if (node.isDirectory) {
              _toggle(path);
            } else {
              widget.onSelectFile?.call(node);
            }
          },
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          child: Padding(
            padding: EdgeInsets.only(
              left: depth * 16.0 + ClairSpacing.sm,
              right: ClairSpacing.sm,
              top: 3,
              bottom: 3,
            ),
            child: Row(
              children: [
                if (node.isDirectory)
                  Icon(
                    isExpanded ? Icons.arrow_drop_down : Icons.arrow_right,
                    size: 16,
                    color: tokens.textSecondary,
                  )
                else
                  const SizedBox(width: 16),
                Icon(icon, size: 15, color: iconColor),
                const SizedBox(width: ClairSpacing.sm),
                Expanded(
                  child: Text(
                    node.name,
                    style: TextStyle(
                      fontFamily: 'JetBrainsMono',
                      fontSize: 12,
                      color: tokens.textPrimary,
                    ),
                  ),
                ),
                if (node.sizeBytes != null)
                  Text(
                    sizeLabel(node.sizeBytes!),
                    style: TextStyle(
                      fontFamily: 'JetBrainsMono',
                      fontSize: 11,
                      color: tokens.textMuted,
                    ),
                  ),
              ],
            ),
          ),
        ),
        if (node.isDirectory && isExpanded)
          for (final child in node.children)
            _buildNode(child, path, depth + 1),
      ],
    );
  }
}
