import 'package:flutter/material.dart';

/// Window classes by width (UI_SYSTEM.md §5).
enum WindowSizeClass {
  compact, // < 720
  medium, // 720–1199
  expanded, // 1200–1599
  large; // >= 1600

  bool get isCompact => this == WindowSizeClass.compact;
  bool get isMedium => this == WindowSizeClass.medium;
  bool get isExpanded => this == WindowSizeClass.expanded;
  bool get isLarge => this == WindowSizeClass.large;
}

/// Helper for responsive layouts using BoxConstraints (UI_SYSTEM.md §5).
/// Screens use this rather than reading MediaQuery.size directly.
class Breakpoints {
  const Breakpoints._();

  static const double compactMax = 719.0;
  static const double mediumMax = 1199.0;
  static const double expandedMax = 1599.0;
  static const double maxContentWidth = 1440.0;

  static WindowSizeClass fromWidth(double width) {
    if (width < 720) return WindowSizeClass.compact;
    if (width < 1200) return WindowSizeClass.medium;
    if (width < 1600) return WindowSizeClass.expanded;
    return WindowSizeClass.large;
  }

  static WindowSizeClass of(BuildContext context) {
    final media = MediaQuery.maybeOf(context);
    if (media == null) return WindowSizeClass.medium;
    return fromWidth(media.size.width);
  }
}

/// Responsive builder widget passing WindowSizeClass.
class ResponsiveLayout extends StatelessWidget {
  const ResponsiveLayout({
    super.key,
    required this.builder,
  });

  final Widget Function(BuildContext context, WindowSizeClass sizeClass, BoxConstraints constraints) builder;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final sizeClass = Breakpoints.fromWidth(constraints.maxWidth);
        return builder(context, sizeClass, constraints);
      },
    );
  }
}
