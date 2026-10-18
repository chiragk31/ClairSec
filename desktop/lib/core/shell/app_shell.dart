import '../../features/assistant/assistant_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../layout/breakpoints.dart';
import '../routing/app_router.dart';
import '../theme/tokens.dart';
import '../theme/theme_provider.dart';
import '../../features/wizard/first_run_wizard.dart';
import '../../providers/projects_provider.dart';
import '../../providers/readiness_provider.dart';
import '../../services/health_service.dart';
import '../../services/readiness_service.dart';
import '../../ui/ui.dart';

class _NavItem {
  final String label;
  final IconData icon;
  final IconData activeIcon;
  final String route;

  const _NavItem({
    required this.label,
    required this.icon,
    required this.activeIcon,
    required this.route,
  });
}

const _navItems = [
  _NavItem(
    label: 'Dashboard',
    icon: Icons.grid_view_outlined,
    activeIcon: Icons.grid_view,
    route: AppRoutes.dashboard,
  ),
  _NavItem(
    label: 'Projects',
    icon: Icons.folder_outlined,
    activeIcon: Icons.folder,
    route: AppRoutes.projects,
  ),
  _NavItem(
    label: 'Scans',
    icon: Icons.radar_outlined,
    activeIcon: Icons.radar,
    route: AppRoutes.scans,
  ),
  _NavItem(
    label: 'Vulnerabilities',
    icon: Icons.shield_outlined,
    activeIcon: Icons.shield,
    route: AppRoutes.vulnerabilities,
  ),
  _NavItem(
    label: 'Fix Review',
    icon: Icons.build_outlined,
    activeIcon: Icons.build,
    route: AppRoutes.fixes,
  ),
  _NavItem(
    label: 'Agents',
    icon: Icons.smart_toy_outlined,
    activeIcon: Icons.smart_toy,
    route: AppRoutes.agents,
  ),
  _NavItem(
    label: 'Reports',
    icon: Icons.description_outlined,
    activeIcon: Icons.description,
    route: AppRoutes.reports,
  ),
  _NavItem(
    label: 'Research',
    icon: Icons.science_outlined,
    activeIcon: Icons.science,
    route: AppRoutes.research,
  ),
];

const _bottomNavItems = [
  _NavItem(
    label: 'Settings',
    icon: Icons.settings_outlined,
    activeIcon: Icons.settings,
    route: AppRoutes.settings,
  ),
];

/// The responsive application shell (UI_SYSTEM.md §5–§6).
/// Top bar + Navigation Rail/Drawer + Status Bar.
class AppShell extends ConsumerStatefulWidget {
  final Widget child;
  const AppShell({super.key, required this.child});

  /// Tracks whether the wizard was auto-shown in the current app session (B3).
  static bool wizardShownThisLaunch = false;

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> with WidgetsBindingObserver {
  final FocusNode _keyboardFocusNode = FocusNode();

  /// "Ask ClairSec" side panel (FEATURES.md F11), toggled with Ctrl+J.
  bool _assistantOpen = false;
  String _lastPath = AppRoutes.dashboard;

  void _toggleAssistant(bool docked) {
    if (docked) {
      setState(() => _assistantOpen = !_assistantOpen);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SizedBox(
        height: MediaQuery.of(ctx).size.height * 0.85,
        child: AssistantPanel(currentPath: _lastPath, onClose: () => Navigator.pop(ctx)),
      ),
    );
  }

  bool _assistantDocked = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkAutoShowWizard();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _keyboardFocusNode.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final visible = state == AppLifecycleState.resumed;
    ref.read(isAppVisibleProvider.notifier).setVisible(visible);
  }

  void _checkAutoShowWizard() {
    if (AppShell.wizardShownThisLaunch) return;

    final projectsAsync = ref.read(projectsProvider);
    final readinessAsync = ref.read(readinessProvider);

    final projects = projectsAsync.asData?.value;
    final readiness = readinessAsync.asData?.value;

    if (projects != null && readiness != null) {
      final hasZeroProjects = projects.isEmpty;
      final isReadinessRed = !readiness.ready;

      if (hasZeroProjects || isReadinessRed) {
        SharedPreferences.getInstance().then((prefs) {
          final dismissed = prefs.getBool(FirstRunWizardDialog.dontShowAgainPrefKey) ?? false;
          if (!dismissed && mounted && !AppShell.wizardShownThisLaunch) {
            AppShell.wizardShownThisLaunch = true;
            FirstRunWizardDialog.show(context);
          }
        });
      }
    }
  }

  void _handleKeyEvent(KeyEvent event) {
    if (event is KeyDownEvent) {
      final isCtrlOrCmd = HardwareKeyboard.instance.isControlPressed ||
          HardwareKeyboard.instance.isMetaPressed;
      if (isCtrlOrCmd && event.logicalKey == LogicalKeyboardKey.keyK) {
        CommandPalette.show(context);
      }
      if (isCtrlOrCmd && event.logicalKey == LogicalKeyboardKey.keyJ) {
        _toggleAssistant(_assistantDocked);
      }
      if (event.logicalKey == LogicalKeyboardKey.f11) {
        final notifier = ref.read(themeSettingsProvider.notifier);
        notifier.setPresenterMode(!ref.read(themeSettingsProvider).presenterMode);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(projectsProvider, (prev, next) {
      if (next.hasValue) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _checkAutoShowWizard());
      }
    });
    ref.listen(readinessProvider, (prev, next) {
      if (next.hasValue) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _checkAutoShowWizard());
      }
    });

    final tokens = context.tokens;
    final readiness = ref.watch(readinessProvider);
    final themeNotifier = ref.read(themeSettingsProvider.notifier);

    String currentPath = AppRoutes.dashboard;
    try {
      currentPath = GoRouterState.of(context).uri.path;
    } catch (_) {}
    _lastPath = currentPath;

    return KeyboardListener(
      focusNode: _keyboardFocusNode,
      autofocus: true,
      onKeyEvent: _handleKeyEvent,
      child: ResponsiveLayout(
        builder: (context, sizeClass, constraints) {
          final isCompact = sizeClass.isCompact;
          final isMedium = sizeClass.isMedium;
          // Docked side panel on wide windows; a sheet on narrow ones (UI_SYSTEM.md section 5).
          _assistantDocked = constraints.maxWidth >= 1200;

          return Scaffold(
            backgroundColor: tokens.bg,
            drawer: isCompact
                ? Drawer(
                    backgroundColor: tokens.surface,
                    child: _buildNavContent(context, currentPath, isCollapsed: false),
                  )
                : null,
            body: Column(
              children: [
                // ── Top Bar (UI_SYSTEM.md §6) ────────────────────────────────
                Container(
                  height: 50,
                  padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
                  decoration: BoxDecoration(
                    color: tokens.surface,
                    border: Border(bottom: BorderSide(color: tokens.border)),
                  ),
                  child: Row(
                    children: [
                      if (isCompact) ...[
                        Builder(
                          builder: (ctx) => IconButton(
                            icon: const Icon(Icons.menu, size: 20),
                            onPressed: () => Scaffold.of(ctx).openDrawer(),
                          ),
                        ),
                        const SizedBox(width: ClairSpacing.xs),
                      ],
                      // Logo icon
                      Container(
                        width: 26,
                        height: 26,
                        decoration: BoxDecoration(
                          color: tokens.accentMuted,
                          borderRadius: BorderRadius.circular(ClairRadius.sm),
                          border: Border.all(color: tokens.accent.withValues(alpha: 0.3)),
                        ),
                        child: Icon(Icons.shield, size: 16, color: tokens.accent),
                      ),
                      const SizedBox(width: ClairSpacing.sm),
                      Text(
                        'ClairSec',
                        style: TextStyle(
                          fontSize: ClairTypography.bodyLarge,
                          fontWeight: FontWeight.w700,
                          letterSpacing: -0.3,
                          color: tokens.textPrimary,
                        ),
                      ),
                      const SizedBox(width: ClairSpacing.lg),
                      // Ctrl+K Search button
                      Expanded(
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 380),
                            child: InkWell(
                              onTap: () => CommandPalette.show(context),
                              borderRadius: BorderRadius.circular(ClairRadius.sm),
                              child: Container(
                                height: 32,
                                padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
                                decoration: BoxDecoration(
                                  color: tokens.surfaceRaised,
                                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                                  border: Border.all(color: tokens.border),
                                ),
                                child: Row(
                                  children: [
                                    Icon(Icons.search, size: 16, color: tokens.textMuted),
                                    const SizedBox(width: ClairSpacing.sm),
                                    Expanded(
                                      child: Text(
                                        'Search or jump to…',
                                        style: TextStyle(fontSize: ClairTypography.code, color: tokens.textMuted),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    Container(
                                      padding: ClairInsets.badge,
                                      decoration: BoxDecoration(
                                        color: tokens.surface,
                                        borderRadius: BorderRadius.circular(4),
                                        border: Border.all(color: tokens.border),
                                      ),
                                      child: Text(
                                        'Ctrl+K',
                                        style: TextStyle(
                                          fontFamily: 'JetBrainsMono',
                                          fontSize: ClairTypography.badge,
                                          color: tokens.textSecondary,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: ClairSpacing.md),
                      // Experience mode badge
                      readiness.when(
                        data: (r) => Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (r.mode != null)
                              ModeBadge(modeId: r.mode!.id, label: r.mode!.label, isSmall: true),
                            if (r.temporaryStorage) ...[
                              const SizedBox(width: ClairSpacing.xs),
                              const TemporaryStorageBadge(),
                            ],
                          ],
                        ),
                        loading: () => const SizedBox.shrink(),
                        error: (_, _) => const SizedBox.shrink(),
                      ),
                      const SizedBox(width: ClairSpacing.sm),
                      // Ask ClairSec
                      IconButton(
                        icon: Icon(Icons.auto_awesome, size: 18, color: tokens.agentAssistant),
                        tooltip: 'Ask ClairSec (Ctrl+J)',
                        onPressed: () => _toggleAssistant(_assistantDocked),
                      ),
                      // Theme toggle
                      IconButton(
                        icon: Icon(tokens.isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined, size: 18),
                        tooltip: 'Toggle theme mode',
                        onPressed: () {
                          themeNotifier.setMode(tokens.isDark ? ThemeMode.light : ThemeMode.dark);
                        },
                      ),
                      // Help / First-run wizard trigger
                      IconButton(
                        icon: const Icon(Icons.help_outline, size: 18),
                        tooltip: 'Welcome Guide & Architecture',
                        onPressed: () => FirstRunWizardDialog.show(context),
                      ),
                    ],
                  ),
                ),
                // ── Main Content Area with Navigation Rail ───────────────────
                Expanded(
                  child: Row(
                    children: [
                      if (!isCompact) ...[
                        _buildNavContent(context, currentPath, isCollapsed: isMedium),
                        VerticalDivider(width: 1, color: tokens.border),
                      ],
                      Expanded(
                        child: widget.child,
                      ),
                      if (_assistantOpen && _assistantDocked) ...[
                        VerticalDivider(width: 1, color: tokens.border),
                        SizedBox(
                          width: 360,
                          child: AssistantPanel(
                            currentPath: currentPath,
                            onClose: () => setState(() => _assistantOpen = false),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                // ── Status Bar (UI_SYSTEM.md §6) ─────────────────────────────
                Container(
                  height: 28,
                  padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
                  decoration: BoxDecoration(
                    color: tokens.surface,
                    border: Border(top: BorderSide(color: tokens.border)),
                  ),
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        minWidth: (constraints.maxWidth - ClairSpacing.md * 2).clamp(0.0, double.infinity),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              _buildBackendDot(tokens),
                              const SizedBox(width: ClairSpacing.md),
                              _buildDockerDot(readiness, tokens),
                              const SizedBox(width: ClairSpacing.md),
                              _buildMongoDot(readiness, tokens),
                            ],
                          ),
                          if (!isCompact)
                            Text(
                              'ClairSec v2.0 · Sealed Sandbox',
                              style: TextStyle(
                                fontSize: ClairTypography.caption,
                                color: tokens.textMuted,
                                fontFamily: 'JetBrainsMono',
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildNavContent(BuildContext context, String currentPath, {required bool isCollapsed}) {
    final tokens = context.tokens;
    final width = isCollapsed ? 64.0 : 200.0;

    bool isActive(String route) {
      if (route == AppRoutes.dashboard) return currentPath == '/';
      return currentPath.startsWith(route);
    }

    return Container(
      width: width,
      color: tokens.surface,
      child: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.xs, vertical: ClairSpacing.sm),
              children: _navItems.map((item) {
                final active = isActive(item.route);
                return _NavTile(
                  item: item,
                  isActive: active,
                  isCollapsed: isCollapsed,
                );
              }).toList(),
            ),
          ),
          Divider(height: 1, color: tokens.border),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.xs, vertical: ClairSpacing.xs),
            child: Column(
              children: _bottomNavItems.map((item) {
                final active = isActive(item.route);
                return _NavTile(
                  item: item,
                  isActive: active,
                  isCollapsed: isCollapsed,
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBackendDot(ClairTokens tokens) {
    final statusAsync = ref.watch(backendStatusProvider);
    final BackendStatus status = statusAsync.value ?? BackendStatus.disconnected;

    final (color, label) = switch (status) {
      BackendStatus.connected => (tokens.success, 'Backend: connected'),
      BackendStatus.tokenMissing => (tokens.warning, 'Backend: token missing'),
      BackendStatus.disconnected => (tokens.danger, 'Backend: disconnected'),
    };

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 7, height: 7, decoration: BoxDecoration(shape: BoxShape.circle, color: color)),
        const SizedBox(width: 5),
        Text(label, style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary)),
      ],
    );
  }

  Widget _buildDockerDot(AsyncValue readiness, ClairTokens tokens) {
    return readiness.when(
      data: (r) {
        final dockerCheck = r.checks.firstWhere(
          (c) => c.name.toLowerCase() == 'docker',
          orElse: () => const ReadinessCheck(name: 'Docker', ok: false, detail: ''),
        );
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: dockerCheck.ok ? tokens.success : tokens.textMuted,
              ),
            ),
            const SizedBox(width: 5),
            Text(
              dockerCheck.ok ? 'Docker: running' : 'Docker: offline',
              style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary),
            ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }

  Widget _buildMongoDot(AsyncValue readiness, ClairTokens tokens) {
    return readiness.when(
      data: (r) {
        final mongoCheck = r.checks.firstWhere(
          (c) => c.name.toLowerCase() == 'mongodb',
          orElse: () => const ReadinessCheck(name: 'MongoDB', ok: false, detail: ''),
        );
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: mongoCheck.ok ? tokens.success : tokens.textMuted,
              ),
            ),
            const SizedBox(width: 5),
            Text(
              mongoCheck.ok ? 'Mongo: connected' : 'Mongo: offline',
              style: TextStyle(fontSize: ClairTypography.caption, color: tokens.textSecondary),
            ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

class _NavTile extends StatefulWidget {
  final _NavItem item;
  final bool isActive;
  final bool isCollapsed;

  const _NavTile({
    required this.item,
    required this.isActive,
    required this.isCollapsed,
  });

  @override
  State<_NavTile> createState() => _NavTileState();
}

class _NavTileState extends State<_NavTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final active = widget.isActive;

    Widget tile = MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: () {
          context.go(widget.item.route);
          if (Scaffold.maybeOf(context)?.isDrawerOpen ?? false) {
            Navigator.of(context).pop();
          }
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          margin: ClairInsets.y1,
          padding: EdgeInsets.symmetric(
            horizontal: widget.isCollapsed ? 0 : ClairSpacing.md,
            vertical: ClairSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: active
                ? tokens.accentMuted
                : _hovered
                    ? tokens.surfaceRaised
                    : Colors.transparent,
            borderRadius: BorderRadius.circular(ClairRadius.sm),
            border: Border.all(
              color: active ? tokens.accent.withValues(alpha: 0.35) : Colors.transparent,
              width: 1,
            ),
          ),
          alignment: widget.isCollapsed ? Alignment.center : Alignment.centerLeft,
          child: Row(
            mainAxisAlignment: widget.isCollapsed ? MainAxisAlignment.center : MainAxisAlignment.start,
            children: [
              Icon(
                active ? widget.item.activeIcon : widget.item.icon,
                size: 18,
                color: active ? tokens.accent : tokens.textSecondary,
              ),
              if (!widget.isCollapsed) ...[
                const SizedBox(width: ClairSpacing.md),
                Expanded(
                  child: Text(
                    widget.item.label,
                    style: TextStyle(
                      fontSize: ClairTypography.body,
                      fontWeight: active ? FontWeight.w600 : FontWeight.w500,
                      color: active ? tokens.accent : tokens.textPrimary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ] else ...[
                SizedBox(
                  width: 0,
                  height: 0,
                  child: OverflowBox(
                    minWidth: 0,
                    maxWidth: 0,
                    minHeight: 0,
                    maxHeight: 0,
                    child: Text(
                      widget.item.label,
                      style: const TextStyle(fontSize: ClairTypography.micro),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );

    if (widget.isCollapsed) {
      tile = Tooltip(
        message: widget.item.label,
        waitDuration: const Duration(milliseconds: 300),
        child: tile,
      );
    }

    return tile;
  }
}
