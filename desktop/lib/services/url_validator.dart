/// URL and ref validator mirror for live UX validation in the UI (FEATURES.md F2).
///
/// Python backend remains authoritative; this mirror provides immediate feedback
/// in the import dialog before the request is submitted.
class GitUrlValidationResult {
  final bool isValid;
  final String? error;
  final String? owner;
  final String? repo;
  final String? normalizedUrl;

  const GitUrlValidationResult({
    required this.isValid,
    this.error,
    this.owner,
    this.repo,
    this.normalizedUrl,
  });
}

class GitUrlValidator {
  static final RegExp _pathRegex =
      RegExp(r'^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$');
  static final RegExp _refRegex = RegExp(r'^[A-Za-z0-9._/-]{1,100}$');

  static GitUrlValidationResult validate(String url, {String? ref}) {
    if (url.trim().isEmpty) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'URL cannot be empty.',
      );
    }

    final raw = url.trim();

    if (raw.startsWith('-')) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'URL cannot start with a dash.',
      );
    }

    if (raw.contains(RegExp(r'\s'))) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'URL cannot contain whitespace.',
      );
    }

    for (final prefix in [
      'file:',
      'ext:',
      'git@',
      'ssh:',
      'ftp:',
      'javascript:'
    ]) {
      if (raw.toLowerCase().startsWith(prefix)) {
        return GitUrlValidationResult(
          isValid: false,
          error: "Scheme '$prefix' is not allowed. Only HTTPS is supported.",
        );
      }
    }

    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Malformed URL.',
      );
    }

    if (uri.scheme.toLowerCase() != 'https') {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Only HTTPS URLs are allowed.',
      );
    }

    if (uri.userInfo.isNotEmpty) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Credentials in URL are strictly prohibited.',
      );
    }

    final schemeIdx = raw.indexOf('://');
    if (schemeIdx != -1) {
      final hostPart = raw.substring(schemeIdx + 3).split('/').first;
      if (hostPart.contains(':')) {
        return const GitUrlValidationResult(
          isValid: false,
          error: 'Explicit ports are prohibited.',
        );
      }
    }

    if (uri.hasQuery) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Query parameters are not permitted.',
      );
    }

    if (uri.hasFragment) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'URL fragments are not permitted.',
      );
    }

    final host = uri.host.toLowerCase();
    if (host != 'github.com') {
      return GitUrlValidationResult(
        isValid: false,
        error: 'Only github.com is supported.',
      );
    }

    if (uri.path.contains('..')) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Path traversal is not allowed.',
      );
    }

    final match = _pathRegex.firstMatch(uri.path);
    if (match == null) {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Expected format: https://github.com/<owner>/<repo>',
      );
    }

    final owner = match.group(1)!;
    final repo = match.group(2)!;

    if (owner == '.' || owner == '..' || repo == '.' || repo == '..') {
      return const GitUrlValidationResult(
        isValid: false,
        error: 'Invalid owner or repository name.',
      );
    }

    if (ref != null && ref.trim().isNotEmpty) {
      final cleanRef = ref.trim();
      if (cleanRef.startsWith('-')) {
        return const GitUrlValidationResult(
          isValid: false,
          error: 'Ref cannot start with a dash.',
        );
      }
      if (!_refRegex.hasMatch(cleanRef) || cleanRef.contains('..')) {
        return const GitUrlValidationResult(
          isValid: false,
          error: 'Invalid git ref (letters, numbers, dot, dash, slash only).',
        );
      }
    }

    return GitUrlValidationResult(
      isValid: true,
      owner: owner,
      repo: repo,
      normalizedUrl: 'https://$host/$owner/$repo',
    );
  }
}
