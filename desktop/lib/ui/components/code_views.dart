import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/theme/tokens.dart';

/// Code block with copy button and optional line numbers (UI_SYSTEM.md §7).
class CodeBlock extends StatefulWidget {
  const CodeBlock({
    super.key,
    required this.code,
    this.language,
    this.showLineNumbers = true,
  });

  final String code;
  final String? language;
  final bool showLineNumbers;

  @override
  State<CodeBlock> createState() => _CodeBlockState();
}

class _CodeBlockState extends State<CodeBlock> {
  bool _copied = false;

  void _copy() {
    Clipboard.setData(ClipboardData(text: widget.code));
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final lines = widget.code.split('\n');

    return Container(
      decoration: BoxDecoration(
        color: tokens.surfaceRaised,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header bar
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: ClairSpacing.md,
              vertical: ClairSpacing.xs,
            ),
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(ClairRadius.sm),
              ),
              border: Border(bottom: BorderSide(color: tokens.border)),
            ),
            child: Row(
              children: [
                if (widget.language != null)
                  Text(
                    widget.language!.toUpperCase(),
                    style: TextStyle(
                      fontFamily: 'JetBrainsMono',
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: tokens.textSecondary,
                    ),
                  ),
                const Spacer(),
                InkWell(
                  onTap: _copy,
                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: ClairSpacing.sm,
                      vertical: 2,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _copied ? Icons.check : Icons.copy,
                          size: 13,
                          color: _copied ? tokens.success : tokens.textSecondary,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          _copied ? 'Copied!' : 'Copy',
                          style: TextStyle(
                            fontSize: 11,
                            color: _copied ? tokens.success : tokens.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // Code content
          Padding(
            padding: const EdgeInsets.all(ClairSpacing.md),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (widget.showLineNumbers) ...[
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        for (int i = 1; i <= lines.length; i++)
                          Text(
                            '$i ',
                            style: TextStyle(
                              fontFamily: 'JetBrainsMono',
                              fontSize: 12.5,
                              color: tokens.textMuted,
                              height: 1.5,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(width: ClairSpacing.md),
                  ],
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final line in lines)
                        Text(
                          line.isEmpty ? ' ' : line,
                          style: TextStyle(
                            fontFamily: 'JetBrainsMono',
                            fontSize: 12.5,
                            color: tokens.textPrimary,
                            height: 1.5,
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Unified diff view with colored hunks and additions/deletions (UI_SYSTEM.md §7).
class DiffView extends StatelessWidget {
  const DiffView({
    super.key,
    required this.diffText,
    this.filePath,
  });

  final String diffText;
  final String? filePath;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final lines = diffText.split('\n');

    return Container(
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (filePath != null)
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: ClairSpacing.md,
                vertical: ClairSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: tokens.surfaceRaised,
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(ClairRadius.sm),
                ),
                border: Border(bottom: BorderSide(color: tokens.border)),
              ),
              child: Text(
                filePath!,
                style: TextStyle(
                  fontFamily: 'JetBrainsMono',
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: tokens.textPrimary,
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: ClairSpacing.xs),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final line in lines) _buildDiffLine(line, tokens),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDiffLine(String line, ClairTokens tokens) {
    Color lineBg = Colors.transparent;
    Color lineFg = tokens.textPrimary;

    if (line.startsWith('+') && !line.startsWith('+++')) {
      lineBg = tokens.diffAddBg;
      lineFg = tokens.success;
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      lineBg = tokens.diffRemoveBg;
      lineFg = tokens.danger;
    } else if (line.startsWith('@@')) {
      lineBg = tokens.diffHunkBg;
      lineFg = tokens.accent;
    }

    return Container(
      width: 1200,
      padding: const EdgeInsets.symmetric(horizontal: ClairSpacing.md, vertical: 1),
      color: lineBg,
      child: Text(
        line.isEmpty ? ' ' : line,
        style: TextStyle(
          fontFamily: 'JetBrainsMono',
          fontSize: 12,
          color: lineFg,
          height: 1.4,
        ),
      ),
    );
  }
}

/// HTTP exchange viewer: Request & Response with curl generator (UI_SYSTEM.md §7).
class HttpExchangeView extends StatelessWidget {
  const HttpExchangeView({
    super.key,
    required this.method,
    required this.url,
    this.requestHeaders = const {},
    this.requestBody,
    this.responseStatus = 200,
    this.responseHeaders = const {},
    this.responseBody,
  });

  final String method;
  final String url;
  final Map<String, dynamic> requestHeaders;
  final String? requestBody;
  final int responseStatus;
  final Map<String, dynamic> responseHeaders;
  final String? responseBody;

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;

    return Container(
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(ClairRadius.sm),
        border: Border.all(color: tokens.border),
      ),
      padding: const EdgeInsets.all(ClairSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Request line
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: tokens.accentMuted,
                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                  border: Border.all(color: tokens.accent.withValues(alpha: 0.3)),
                ),
                child: Text(
                  method.toUpperCase(),
                  style: TextStyle(
                    fontFamily: 'JetBrainsMono',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: tokens.accent,
                  ),
                ),
              ),
              const SizedBox(width: ClairSpacing.sm),
              Expanded(
                child: Text(
                  url,
                  style: TextStyle(
                    fontFamily: 'JetBrainsMono',
                    fontSize: 13,
                    color: tokens.textPrimary,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: (responseStatus >= 200 && responseStatus < 300
                          ? tokens.success
                          : (responseStatus >= 400 && responseStatus < 500 ? tokens.warning : tokens.danger))
                      .withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                ),
                child: Text(
                  '$responseStatus',
                  style: TextStyle(
                    fontFamily: 'JetBrainsMono',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: responseStatus >= 200 && responseStatus < 300
                        ? tokens.success
                        : (responseStatus >= 400 && responseStatus < 500 ? tokens.warning : tokens.danger),
                  ),
                ),
              ),
            ],
          ),
          if (requestBody != null) ...[
            const SizedBox(height: ClairSpacing.md),
            Text(
              'Request Body',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: tokens.textSecondary),
            ),
            const SizedBox(height: ClairSpacing.xs),
            CodeBlock(code: requestBody!, language: 'json', showLineNumbers: false),
          ],
          if (responseBody != null) ...[
            const SizedBox(height: ClairSpacing.md),
            Text(
              'Response Body',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: tokens.textSecondary),
            ),
            const SizedBox(height: ClairSpacing.xs),
            CodeBlock(code: responseBody!, language: 'json', showLineNumbers: false),
          ],
        ],
      ),
    );
  }
}
