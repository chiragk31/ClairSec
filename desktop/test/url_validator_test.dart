import 'package:flutter_test/flutter_test.dart';
import 'package:desktop/services/url_validator.dart';

void main() {
  group('GitUrlValidator (mirror tests)', () {
    final validCases = [
      'https://github.com/tiangolo/fastapi',
      'https://github.com/encode/starlette.git',
      'https://github.com/owner-name/repo_name.1',
      'https://github.com/owner/repo/',
      'https://github.com/org.team/app-service_v2.git/',
    ];

    for (final url in validCases) {
      test('valid URL passes: $url', () {
        final res = GitUrlValidator.validate(url);
        expect(res.isValid, isTrue, reason: res.error);
        expect(res.owner, isNotNull);
        expect(res.repo, isNotNull);
      });
    }

    final invalidCases = [
      'http://github.com/owner/repo',
      'file:///etc/passwd',
      'file://localhost/path',
      'ext::sh -c evil',
      'git@github.com:owner/repo.git',
      'ssh://git@github.com/owner/repo',
      'ftp://github.com/owner/repo',
      'javascript:alert(1)',
      'https://user:pw@github.com/owner/repo',
      'https://user@github.com/owner/repo',
      'https://github.com.evil.com/owner/repo',
      'https://evil-github.com/owner/repo',
      'https://notgithub.org/owner/repo',
      'https://github.com:443/owner/repo',
      'https://github.com:8080/owner/repo',
      'https://github.com/owner/repo?token=secret',
      'https://github.com/owner/repo#readme',
      'https://github.com/owner/repo/../evil/repo',
      'https://github.com/owner/repo/sub/dir',
      'https://github.com/owner',
      'https://github.com/',
      'https://github.com',
      '--upload-pack=evil',
      'https://github.com/owner/repo;rm -rf /',
    ];

    for (final url in invalidCases) {
      test('invalid URL rejected: $url', () {
        final res = GitUrlValidator.validate(url);
        expect(res.isValid, isFalse, reason: 'Expected $url to be rejected');
      });
    }

    test('ref validation rules', () {
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: 'main').isValid, isTrue);
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: 'v1.0.0').isValid, isTrue);
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: 'feat/branch-1').isValid, isTrue);

      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: '--upload-pack').isValid, isFalse);
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: '-b').isValid, isFalse);
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: 'has spaces').isValid, isFalse);
      expect(GitUrlValidator.validate('https://github.com/owner/repo', ref: 'heads/../traversal').isValid, isFalse);
    });
  });
}
