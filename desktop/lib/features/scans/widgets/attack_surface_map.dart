import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';

/// Single node in the attack surface tree (FEATURES.md F10).
class SurfaceNode {
  final String id;
  final String path;
  final List<String> methods;
  final String auth; // "public", "login", "admin"
  final String? worstSeverity; // "critical", "high", "medium", "low", "informational", or null
  final List<String> findingIds;
  final int testsRun;

  const SurfaceNode({
    required this.id,
    required this.path,
    required this.methods,
    required this.auth,
    this.worstSeverity,
    this.findingIds = const [],
    this.testsRun = 0,
  });

  factory SurfaceNode.fromJson(Map<String, dynamic> json) {
    return SurfaceNode(
      id: json['id'] as String? ?? 'unknown',
      path: json['path'] as String? ?? '/',
      methods: ((json['methods'] as List<dynamic>?) ?? const [])
          .map((m) => m.toString())
          .toList(),
      auth: json['auth'] as String? ?? 'public',
      worstSeverity: json['worst_severity'] as String? ?? json['worstSeverity'] as String?,
      findingIds: ((json['finding_ids'] as List<dynamic>?) ??
              (json['findingIds'] as List<dynamic>?) ??
              const [])
          .map((f) => f.toString())
          .toList(),
      testsRun: (json['tests_run'] ?? json['testsRun'] ?? 0) as int,
    );
  }
}

/// Hierarchical edge connecting a parent path segment to a child path (FEATURES.md F10).
class SurfaceEdge {
  final String from;
  final String to;

  const SurfaceEdge({required this.from, required this.to});

  factory SurfaceEdge.fromJson(Map<String, dynamic> json) {
    return SurfaceEdge(
      from: json['from'] as String? ?? '',
      to: json['to'] as String? ?? '',
    );
  }
}

/// Attack Surface Map widget (FEATURES.md F10).
/// Features:
/// 1. CustomPainter tidy-tree layout with pan/zoom (InteractiveViewer).
/// 2. Keyboard-navigable accessible list alternative.
/// 3. Method pills, worst severity indicator, auth icons.
class AttackSurfaceMap extends StatefulWidget {
  final List<SurfaceNode> nodes;
  final List<SurfaceEdge> edges;
  final ValueChanged<SurfaceNode>? onNodeSelected;
  final String? initialSelectedNodeId;

  const AttackSurfaceMap({
    super.key,
    required this.nodes,
    this.edges = const [],
    this.onNodeSelected,
    this.initialSelectedNodeId,
  });

  @override
  State<AttackSurfaceMap> createState() => _AttackSurfaceMapState();
}

class _AttackSurfaceMapState extends State<AttackSurfaceMap> {
  bool _isListView = false;
  String? _selectedNodeId;

  @override
  void initState() {
    super.initState();
    _selectedNodeId = widget.initialSelectedNodeId;
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.md),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header / Toolbar
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: ClairSpacing.md,
              vertical: ClairSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: tokens.surfaceRaised,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(ClairRadius.md),
                topRight: Radius.circular(ClairRadius.md),
              ),
              border: Border(bottom: BorderSide(color: tokens.border)),
            ),
            child: Row(
              children: [
                Icon(Icons.account_tree_outlined, size: 16, color: tokens.accent),
                const SizedBox(width: ClairSpacing.sm),
                Text(
                  'Attack-surface map (${widget.nodes.length} routes)',
                  style: TextStyle(
                    fontSize: ClairTypography.body,
                    fontWeight: FontWeight.w600,
                    color: tokens.textPrimary,
                  ),
                ),
                const Spacer(),
                // View toggle: Tree vs List (Accessibility requirement)
                Container(
                  decoration: BoxDecoration(
                    color: tokens.surface,
                    borderRadius: BorderRadius.circular(ClairRadius.sm),
                    border: Border.all(color: tokens.border),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        key: const Key('toggle_tree_view'),
                        icon: const Icon(Icons.hub_outlined, size: 16),
                        color: !_isListView ? tokens.accent : tokens.textMuted,
                        onPressed: () => setState(() => _isListView = false),
                        tooltip: 'Tree view',
                      ),
                      IconButton(
                        key: const Key('toggle_list_view'),
                        icon: const Icon(Icons.list_alt_outlined, size: 16),
                        color: _isListView ? tokens.accent : tokens.textMuted,
                        onPressed: () => setState(() => _isListView = true),
                        tooltip: 'List (Accessible)',
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // Content
          Expanded(
            child: widget.nodes.isEmpty
                ? Center(
                    child: Text(
                      'No attack surface nodes discovered yet.',
                      style: TextStyle(
                        fontSize: ClairTypography.body,
                        color: tokens.textMuted,
                      ),
                    ),
                  )
                : _isListView
                    ? _buildListView(tokens)
                    : _buildTreeView(tokens),
          ),
        ],
      ),
    );
  }

  /// Keyboard-navigable accessible list alternative (FEATURES.md F10).
  Widget _buildListView(ClairTokens tokens) {
    return ListView.separated(
      key: const Key('attack_surface_list_view'),
      padding: const EdgeInsets.all(ClairSpacing.md),
      itemCount: widget.nodes.length,
      separatorBuilder: (context, index) => const SizedBox(height: ClairSpacing.sm),
      itemBuilder: (context, index) {
        final node = widget.nodes[index];
        final isSelected = node.id == _selectedNodeId;
        final sevColor = _severityColor(node.worstSeverity, tokens);

        return InkWell(
          key: Key('node_item_${node.id}'),
          onTap: () {
            setState(() => _selectedNodeId = node.id);
            widget.onNodeSelected?.call(node);
          },
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          child: Container(
            padding: const EdgeInsets.all(ClairSpacing.md),
            decoration: BoxDecoration(
              color: isSelected ? tokens.surfaceRaised : tokens.surface,
              borderRadius: BorderRadius.circular(ClairRadius.sm),
              border: Border.all(
                color: isSelected
                    ? tokens.accent
                    : (sevColor != null
                        ? sevColor.withValues(alpha: 0.5)
                        : tokens.border),
                width: isSelected ? 1.5 : 1.0,
              ),
            ),
            child: Row(
              children: [
                _authIcon(node.auth, tokens),
                const SizedBox(width: ClairSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        node.path,
                        style: TextStyle(
                          fontFamily: 'JetBrainsMono',
                          fontSize: ClairTypography.code,
                          fontWeight: FontWeight.w600,
                          color: tokens.textPrimary,
                        ),
                      ),
                      const SizedBox(height: ClairSpacing.xs),
                      Wrap(
                        spacing: ClairSpacing.xs,
                        children: [
                          for (final m in node.methods)
                            _methodPill(m, tokens),
                          if (node.testsRun > 0)
                            Text(
                              '${node.testsRun} tests',
                              style: TextStyle(
                                fontSize: ClairTypography.caption,
                                color: tokens.textMuted,
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
                if (node.worstSeverity != null)
                  _severityBadge(node.worstSeverity!, tokens),
              ],
            ),
          ),
        );
      },
    );
  }

  /// Interactive tidy-tree layout with CustomPainter.
  Widget _buildTreeView(ClairTokens tokens) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final positions = _calculateNodePositions(widget.nodes, widget.edges, constraints);
        final contentSize = _calculateContentBounds(positions);

        return InteractiveViewer(
          boundaryMargin: ClairInsets.allXxl,
          minScale: 0.4,
          maxScale: 2.5,
          child: SizedBox(
            width: math.max(constraints.maxWidth, contentSize.width + 120),
            height: math.max(constraints.maxHeight, contentSize.height + 120),
            child: Stack(
              children: [
                // CustomPainter connects parent-child nodes
                Positioned.fill(
                  child: CustomPaint(
                    painter: _TreeEdgesPainter(
                      edges: widget.edges,
                      positions: positions,
                      lineColor: tokens.border,
                      activeColor: tokens.accent,
                    ),
                  ),
                ),
                // Node pills
                for (final node in widget.nodes)
                  if (positions.containsKey(node.id))
                    Positioned(
                      left: positions[node.id]!.dx,
                      top: positions[node.id]!.dy,
                      child: _buildNodeCard(node, tokens),
                    ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildNodeCard(SurfaceNode node, ClairTokens tokens) {
    final isSelected = node.id == _selectedNodeId;
    final sevColor = _severityColor(node.worstSeverity, tokens);

    return InkWell(
      key: Key('node_tree_${node.id}'),
      onTap: () {
        setState(() => _selectedNodeId = node.id);
        widget.onNodeSelected?.call(node);
      },
      borderRadius: BorderRadius.circular(ClairRadius.sm),
      child: Container(
        width: 170,
        padding: const EdgeInsets.symmetric(
          horizontal: ClairSpacing.sm,
          vertical: ClairSpacing.xs + 2,
        ),
        decoration: BoxDecoration(
          color: isSelected
              ? tokens.accent.withValues(alpha: 0.15)
              : tokens.surfaceRaised,
          borderRadius: BorderRadius.circular(ClairRadius.sm),
          border: Border.all(
            color: isSelected
                ? tokens.accent
                : (sevColor != null
                    ? sevColor.withValues(alpha: 0.7)
                    : tokens.border),
            width: isSelected ? 1.5 : 1.0,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                _authIcon(node.auth, tokens),
                const SizedBox(width: ClairSpacing.xs),
                Expanded(
                  child: Text(
                    node.path,
                    style: TextStyle(
                      fontFamily: 'JetBrainsMono',
                      fontSize: ClairTypography.caption,
                      fontWeight: FontWeight.w600,
                      color: tokens.textPrimary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 3),
            Wrap(
              spacing: 4,
              runSpacing: 2,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                for (final m in node.methods.take(2))
                  _methodPill(m, tokens),
                if (node.worstSeverity != null)
                  _severityBadge(node.worstSeverity!, tokens),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _authIcon(String auth, ClairTokens tokens) {
    final (icon, color) = switch (auth.toLowerCase()) {
      'admin' => (Icons.admin_panel_settings_outlined, tokens.critical),
      'login' => (Icons.lock_outline, tokens.warning),
      _ => (Icons.lock_open_outlined, tokens.textMuted),
    };
    return Icon(icon, size: 13, color: color);
  }

  Widget _methodPill(String method, ClairTokens tokens) {
    final m = method.toUpperCase();
    final color = switch (m) {
      'GET' => tokens.info,
      'POST' => tokens.success,
      'PUT' || 'PATCH' => tokens.warning,
      'DELETE' => tokens.critical,
      _ => tokens.textSecondary,
    };
    return Container(
      padding: ClairInsets.badge,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        m,
        style: TextStyle(
          fontFamily: 'JetBrainsMono',
          fontSize: ClairTypography.badge,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }

  Widget _severityBadge(String severity, ClairTokens tokens) {
    final color = _severityColor(severity, tokens) ?? tokens.textMuted;
    return Container(
      padding: ClairInsets.badge,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(ClairRadius.pill),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        severity.toUpperCase(),
        style: TextStyle(
          fontSize: ClairTypography.badge,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }

  Color? _severityColor(String? severity, ClairTokens tokens) {
    if (severity == null) return null;
    return switch (severity.toLowerCase()) {
      'critical' => tokens.critical,
      'high' => tokens.high,
      'medium' => tokens.medium,
      'low' => tokens.low,
      _ => tokens.info,
    };
  }

  Map<String, Offset> _calculateNodePositions(
    List<SurfaceNode> nodes,
    List<SurfaceEdge> edges,
    BoxConstraints constraints,
  ) {
    final positions = <String, Offset>{};
    if (nodes.isEmpty) return positions;

    // Build parent -> children map
    final childrenMap = <String, List<String>>{};
    final hasParent = <String>{};

    for (final edge in edges) {
      childrenMap.setdefault(edge.from, []).add(edge.to);
      hasParent.add(edge.to);
    }

    // Root nodes
    final roots = nodes.where((n) => !hasParent.contains(n.id)).toList();
    if (roots.isEmpty && nodes.isNotEmpty) {
      roots.add(nodes.first);
    }

    double currentX = 30.0;
    const double levelYSpacing = 80.0;
    const double nodeXSpacing = 190.0;

    void layoutSubtree(String nodeId, int depth) {
      final y = 30.0 + depth * levelYSpacing;
      final children = childrenMap[nodeId] ?? const [];

      if (children.isEmpty) {
        positions[nodeId] = Offset(currentX, y);
        currentX += nodeXSpacing;
      } else {
        final startX = currentX;
        for (final child in children) {
          if (!positions.containsKey(child)) {
            layoutSubtree(child, depth + 1);
          }
        }
        final endX = currentX - nodeXSpacing;
        positions[nodeId] = Offset((startX + endX) / 2, y);
      }
    }

    for (final root in roots) {
      layoutSubtree(root.id, 0);
    }

    // Catch any disconnected nodes
    for (final node in nodes) {
      if (!positions.containsKey(node.id)) {
        positions[node.id] = Offset(currentX, 30.0);
        currentX += nodeXSpacing;
      }
    }

    return positions;
  }

  Size _calculateContentBounds(Map<String, Offset> positions) {
    double maxX = 0;
    double maxY = 0;
    for (final pos in positions.values) {
      if (pos.dx > maxX) maxX = pos.dx;
      if (pos.dy > maxY) maxY = pos.dy;
    }
    return Size(maxX + 200, maxY + 100);
  }
}

extension _MapDefault<K, V> on Map<K, V> {
  V setdefault(K key, V defaultValue) {
    return putIfAbsent(key, () => defaultValue);
  }
}

/// CustomPainter for tidy-tree bezier edges connecting parent nodes to children.
class _TreeEdgesPainter extends CustomPainter {
  final List<SurfaceEdge> edges;
  final Map<String, Offset> positions;
  final Color lineColor;
  final Color activeColor;

  _TreeEdgesPainter({
    required this.edges,
    required this.positions,
    required this.lineColor,
    required this.activeColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = lineColor.withValues(alpha: 0.6)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    for (final edge in edges) {
      final p1 = positions[edge.from];
      final p2 = positions[edge.to];
      if (p1 == null || p2 == null) continue;

      // Card anchor points: center bottom of parent to center top of child
      final start = Offset(p1.dx + 85, p1.dy + 45);
      final end = Offset(p2.dx + 85, p2.dy);

      final path = Path();
      path.moveTo(start.dx, start.dy);
      final midY = (start.dy + end.dy) / 2;
      path.cubicTo(start.dx, midY, end.dx, midY, end.dx, end.dy);
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _TreeEdgesPainter oldDelegate) {
    return oldDelegate.positions != positions || oldDelegate.edges != edges;
  }
}
