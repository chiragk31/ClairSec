import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/tokens.dart';

class CommandPaletteAction {
  const CommandPaletteAction({
    required this.title,
    this.subtitle,
    required this.icon,
    required this.onPerform,
    this.shortcut,
  });

  final String title;
  final String? subtitle;
  final IconData icon;
  final void Function(BuildContext context) onPerform;
  final String? shortcut;
}

/// Command palette dialog triggered by Ctrl+K (UI_SYSTEM.md §6, §7, FEATURES.md F14).
class CommandPalette extends StatefulWidget {
  const CommandPalette({
    super.key,
    this.extraActions = const [],
  });

  final List<CommandPaletteAction> extraActions;

  static void show(BuildContext context) {
    showDialog(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.5),
      builder: (_) => const CommandPalette(),
    );
  }

  static List<CommandPaletteAction> getDefaultActions({bool isDebug = kDebugMode}) {
    return [
      CommandPaletteAction(
        title: 'Dashboard',
        subtitle: 'View system posture score and active scans',
        icon: Icons.dashboard_outlined,
        shortcut: 'G D',
        onPerform: (ctx) => ctx.go('/'),
      ),
      CommandPaletteAction(
        title: 'Projects',
        subtitle: 'Import and manage FastAPI repositories',
        icon: Icons.folder_outlined,
        shortcut: 'G P',
        onPerform: (ctx) => ctx.go('/projects'),
      ),
      CommandPaletteAction(
        title: 'Scans',
        subtitle: 'View security scan runs and agent activity',
        icon: Icons.radar,
        shortcut: 'G S',
        onPerform: (ctx) => ctx.go('/scans'),
      ),
      CommandPaletteAction(
        title: 'Findings',
        subtitle: 'Inspect confirmed vulnerabilities and evidence',
        icon: Icons.shield_outlined,
        shortcut: 'G F',
        onPerform: (ctx) => ctx.go('/vulnerabilities'),
      ),
      CommandPaletteAction(
        title: 'Fix Review',
        subtitle: 'Review and verify AST-generated code patches',
        icon: Icons.build_outlined,
        shortcut: 'G R',
        onPerform: (ctx) => ctx.go('/fixes'),
      ),
      CommandPaletteAction(
        title: 'Agents',
        subtitle: 'Inspect autonomous multi-agent pipeline and tools',
        icon: Icons.smart_toy_outlined,
        shortcut: 'G A',
        onPerform: (ctx) => ctx.go('/agents'),
      ),
      CommandPaletteAction(
        title: 'Reports',
        subtitle: 'Export executive and technical audit reports',
        icon: Icons.description_outlined,
        shortcut: 'G E',
        onPerform: (ctx) => ctx.go('/reports'),
      ),
      CommandPaletteAction(
        title: 'Settings',
        subtitle: 'Appearance, themes, LLM configuration, and keys',
        icon: Icons.settings_outlined,
        shortcut: 'G ,',
        onPerform: (ctx) => ctx.go('/settings'),
      ),
      if (isDebug)
        CommandPaletteAction(
          title: 'Component Gallery',
          subtitle: 'Debug gallery of all UI tokens and components',
          icon: Icons.palette_outlined,
          onPerform: (ctx) => ctx.go('/_gallery'),
        ),
    ];
  }

  @override
  State<CommandPalette> createState() => _CommandPaletteState();
}

class _CommandPaletteState extends State<CommandPalette> {
  final TextEditingController _searchController = TextEditingController();
  int _selectedIndex = 0;

  List<CommandPaletteAction> _defaultActions(BuildContext context) {
    return [
      ...CommandPalette.getDefaultActions(),
      ...widget.extraActions,
    ];
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final allActions = _defaultActions(context);
    final query = _searchController.text.trim().toLowerCase();

    final filtered = allActions.where((a) {
      if (query.isEmpty) return true;
      return a.title.toLowerCase().contains(query) ||
          (a.subtitle != null && a.subtitle!.toLowerCase().contains(query));
    }).toList();

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 580, maxHeight: 460),
          child: Container(
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: BorderRadius.circular(ClairRadius.lg),
              border: Border.all(color: tokens.border, width: 1.5),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.35),
                  blurRadius: 24,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Search input
                Padding(
                  padding: const EdgeInsets.all(ClairSpacing.md),
                  child: TextField(
                    controller: _searchController,
                    autofocus: true,
                    style: TextStyle(fontSize: 14, color: tokens.textPrimary),
                    decoration: InputDecoration(
                      prefixIcon: Icon(Icons.search, size: 20, color: tokens.accent),
                      suffixIcon: query.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear, size: 16),
                              onPressed: () {
                                _searchController.clear();
                                setState(() => _selectedIndex = 0);
                              },
                            )
                          : Container(
                              margin: const EdgeInsets.all(ClairSpacing.sm),
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: tokens.surfaceRaised,
                                borderRadius: BorderRadius.circular(ClairRadius.sm),
                                border: Border.all(color: tokens.border),
                              ),
                              child: Text(
                                'ESC',
                                style: TextStyle(
                                  fontFamily: 'JetBrainsMono',
                                  fontSize: 10,
                                  color: tokens.textSecondary,
                                ),
                              ),
                            ),
                      hintText: 'Search actions, screens, or jump to…',
                      hintStyle: TextStyle(fontSize: 14, color: tokens.textMuted),
                      border: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(vertical: ClairSpacing.md),
                    ),
                    onChanged: (_) => setState(() => _selectedIndex = 0),
                  ),
                ),
                Divider(height: 1, color: tokens.border),
                // Action list
                Flexible(
                  child: filtered.isEmpty
                      ? Padding(
                          padding: const EdgeInsets.all(ClairSpacing.xxl),
                          child: Text(
                            'No matching commands found',
                            style: TextStyle(color: tokens.textMuted, fontSize: 13),
                          ),
                        )
                      : ListView.builder(
                          shrinkWrap: true,
                          padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xs),
                          itemCount: filtered.length,
                          itemBuilder: (context, index) {
                            final action = filtered[index];
                            final isSelected = index == _selectedIndex;

                            return InkWell(
                              onTap: () {
                                Navigator.of(context).pop();
                                action.onPerform(context);
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: ClairSpacing.lg,
                                  vertical: ClairSpacing.sm,
                                ),
                                color: isSelected ? tokens.accentMuted : Colors.transparent,
                                child: Row(
                                  children: [
                                    Icon(
                                      action.icon,
                                      size: 18,
                                      color: isSelected ? tokens.accent : tokens.textSecondary,
                                    ),
                                    const SizedBox(width: ClairSpacing.md),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            action.title,
                                            style: TextStyle(
                                              fontSize: 13.5,
                                              fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                                              color: isSelected ? tokens.accent : tokens.textPrimary,
                                            ),
                                          ),
                                          if (action.subtitle != null) ...[
                                            const SizedBox(height: 2),
                                            Text(
                                              action.subtitle!,
                                              style: TextStyle(
                                                fontSize: 12,
                                                color: tokens.textSecondary,
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
                                    ),
                                    if (action.shortcut != null) ...[
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: tokens.surfaceRaised,
                                          borderRadius: BorderRadius.circular(ClairRadius.sm),
                                          border: Border.all(color: tokens.border),
                                        ),
                                        child: Text(
                                          action.shortcut!,
                                          style: TextStyle(
                                            fontFamily: 'JetBrainsMono',
                                            fontSize: 11,
                                            color: tokens.textSecondary,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
