import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../core/theme/tokens.dart';

/// Radial posture score gauge with grade letter and sweep animation (UI_SYSTEM.md §7, §8).
class ScoreGauge extends StatefulWidget {
  const ScoreGauge({
    super.key,
    required this.score,
    this.previousScore,
    this.coverage,
    this.basis,
    this.size = 140,
    this.animate = true,
  });

  final double score; // 0 to 100
  final double? previousScore;
  final double? coverage; // 0.0 to 1.0
  final String? basis;
  final double size;
  final bool animate;

  static String scoreToGrade(double score) {
    if (score >= 90) return 'A';
    if (score >= 80) return 'B';
    if (score >= 70) return 'C';
    if (score >= 55) return 'D';
    return 'F';
  }

  @override
  State<ScoreGauge> createState() => _ScoreGaugeState();
}

class _ScoreGaugeState extends State<ScoreGauge> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.animate ? const Duration(milliseconds: 900) : Duration.zero,
    );
    _animation = Tween<double>(
      begin: widget.previousScore ?? 0.0,
      end: widget.score,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

    _controller.forward();
  }

  @override
  void didUpdateWidget(ScoreGauge oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.score != widget.score) {
      _animation = Tween<double>(
        begin: oldWidget.score,
        end: widget.score,
      ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
      _controller.forward(from: 0.0);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final grade = ScoreGauge.scoreToGrade(widget.score);
    final isLimitedCoverage = widget.coverage != null && widget.coverage! < 0.50;

    Color scoreColor(double s) {
      if (isLimitedCoverage) return tokens.textSecondary;
      if (s >= 80) return tokens.success;
      if (s >= 55) return tokens.warning;
      return tokens.critical;
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: _animation,
          builder: (context, child) {
            final current = _animation.value;
            final color = scoreColor(current);

            return SizedBox(
              width: widget.size,
              height: widget.size,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  CustomPaint(
                    size: Size(widget.size, widget.size),
                    painter: _GaugePainter(
                      fraction: (current / 100.0).clamp(0.0, 1.0),
                      trackColor: tokens.surfaceRaised,
                      fillColor: color,
                      strokeWidth: widget.size * 0.09,
                    ),
                  ),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        grade,
                        style: TextStyle(
                          fontSize: widget.size * 0.28,
                          fontWeight: FontWeight.w700,
                          color: isLimitedCoverage ? tokens.textMuted : color,
                          height: 1.0,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${current.round()}/100',
                        style: TextStyle(
                          fontSize: widget.size * 0.13,
                          fontWeight: FontWeight.w600,
                          color: tokens.textSecondary,
                        ),
                      ),
                      if (isLimitedCoverage) ...[
                        const SizedBox(height: 2),
                        Text(
                          'Limited coverage',
                          style: TextStyle(
                            fontSize: widget.size * 0.08,
                            fontWeight: FontWeight.w500,
                            color: tokens.textMuted,
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            );
          },
        ),
        if (widget.basis != null) ...[
          const SizedBox(height: ClairSpacing.sm),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md),
            child: Text(
              widget.basis!,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: ClairTypography.caption,
                color: tokens.textMuted,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _GaugePainter extends CustomPainter {
  const _GaugePainter({
    required this.fraction,
    required this.trackColor,
    required this.fillColor,
    required this.strokeWidth,
  });

  final double fraction;
  final Color trackColor;
  final Color fillColor;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    const startAngle = math.pi * 0.75;
    const sweepTotal = math.pi * 1.5;

    final trackPaint = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final fillPaint = Paint()
      ..color = fillColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepTotal,
      false,
      trackPaint,
    );

    if (fraction > 0) {
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        sweepTotal * fraction,
        false,
        fillPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GaugePainter old) =>
      old.fraction != fraction || old.fillColor != fillColor || old.trackColor != trackColor;
}
