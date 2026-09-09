import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../routing/app_router.dart';
import '../theme/app_theme.dart';
import '../../providers/projects_provider.dart';
import '../../services/health_service.dart';

/// Navigation destination model for the left rail.
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
    icon: Icons.bug_report_outlined,
    activeIcon: Icons.bug_report,
    route: AppRoutes.vulnerabilities,
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

/// The persistent shell wrapping all pages — provides left navigation rail.
class AppShell extends StatelessWidget {
  final Widget child;
  const AppShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Row(
        children: [
          _NavigationRail(currentLocation: GoRouterState.of(context).uri.path),
          const VerticalDivider(width: 1),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _NavigationRail extends StatelessWidget {
  final String currentLocation;
  const _NavigationRail({required this.currentLocation});

  bool _isActive(String route) {
    if (route == AppRoutes.dashboard) return currentLocation == '/';
    return currentLocation.startsWith(route);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 200,
      color: AppColors.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _AppLogo(),
          const SizedBox(height: 8),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              children: _navItems
                  .map((item) => _NavTile(item: item, isActive: _isActive(item.route)))
                  .toList(),
            ),
          ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            child: Column(
              children: _bottomNavItems
                  .map((item) => _NavTile(item: item, isActive: _isActive(item.route)))
                  .toList(),
            ),
          ),
          _BackendStatusIndicator(),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}

class _AppLogo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: AppColors.accent.withValues(alpha: 0.4)),
            ),
            child: const Icon(Icons.shield_outlined, size: 16, color: AppColors.accent),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'ClairSec',
                  style: AppTheme.dark.textTheme.titleMedium?.copyWith(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.3,
                  ),
                ),
                Text(
                  'Security Platform',
                  style: AppTheme.dark.textTheme.labelSmall?.copyWith(
                    color: AppColors.textDisabled,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _NavTile extends StatefulWidget {
  final _NavItem item;
  final bool isActive;

  const _NavTile({required this.item, required this.isActive});

  @override
  State<_NavTile> createState() => _NavTileState();
}

class _NavTileState extends State<_NavTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final active = widget.isActive;
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: () => context.go(widget.item.route),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          margin: const EdgeInsets.symmetric(vertical: 1),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            color: active
                ? AppColors.selectedOverlay
                : _hovered
                    ? AppColors.hoverOverlay
                    : Colors.transparent,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: active ? AppColors.accent.withValues(alpha: 0.3) : Colors.transparent,
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Icon(
                active ? widget.item.activeIcon : widget.item.icon,
                size: 16,
                color: active ? AppColors.accent : AppColors.textSecondary,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.item.label,
                  style: AppTheme.dark.textTheme.bodyMedium?.copyWith(
                    color: active ? AppColors.accent : AppColors.textSecondary,
                    fontWeight: active ? FontWeight.w600 : FontWeight.w400,
                    fontSize: 13,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BackendStatusIndicator extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(backendStatusProvider);
    final status = statusAsync.value ?? BackendStatus.disconnected;

    final Color color;
    final String text;

    switch (status) {
      case BackendStatus.connected:
        color = SeverityColors.success;
        text = 'Backend: connected';
      case BackendStatus.tokenMissing:
        color = SeverityColors.warning;
        text = 'Backend: token missing';
      case BackendStatus.disconnected:
        color = AppColors.textDisabled;
        text = 'Backend: disconnected';
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
      child: Row(
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              style: AppTheme.dark.textTheme.labelSmall?.copyWith(
                fontSize: 10,
                color: status == BackendStatus.connected
                    ? AppColors.textSecondary
                    : (status == BackendStatus.tokenMissing
                        ? SeverityColors.warning
                        : AppColors.textDisabled),
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
