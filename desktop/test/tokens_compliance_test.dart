import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Token Compliance Gate (Audit Defect B1)', () {
    final libDir = Directory('lib');

    List<File> getDartFiles(Directory dir) {
      return dir
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'))
          .where((f) {
            final normalized = f.path.replaceAll('\\', '/');
            return !normalized.contains('lib/core/theme/') &&
                !normalized.contains('lib/ui/');
          })
          .toList();
    }

    test('Zero raw fontSize literals outside lib/core/theme and lib/ui', () {
      final dartFiles = getDartFiles(libDir);
      final fontSizePattern = RegExp(r'fontSize:\s*\d');
      final violations = <String>[];

      for (final file in dartFiles) {
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (fontSizePattern.hasMatch(line)) {
            final normalized = file.path.replaceAll('\\', '/');
            violations.add('$normalized:${i + 1}: ${line.trim()}');
          }
        }
      }

      expect(
        violations,
        isEmpty,
        reason:
            'Found raw fontSize numeric literals outside lib/core/theme and lib/ui.\n'
            'Must use ClairTypography.* tokens instead.\n'
            'Violations (${violations.length}):\n${violations.join('\n')}',
      );
    });

    test('Zero numeric EdgeInsets literals outside lib/core/theme and lib/ui', () {
      final dartFiles = getDartFiles(libDir);
      final edgeInsetsNumericPattern =
          RegExp(r'EdgeInsets\s*(\.\s*(all|symmetric|only|fromLTRB))?\s*\([^)]*\d');
      final violations = <String>[];

      for (final file in dartFiles) {
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (edgeInsetsNumericPattern.hasMatch(line)) {
            final normalized = file.path.replaceAll('\\', '/');
            violations.add('$normalized:${i + 1}: ${line.trim()}');
          }
        }
      }

      expect(
        violations,
        isEmpty,
        reason:
            'Found raw EdgeInsets numeric literals outside lib/core/theme and lib/ui.\n'
            'Must use ClairSpacing / ClairInsets tokens instead.\n'
            'Violations (${violations.length}):\n${violations.join('\n')}',
      );
    });
  });
}
