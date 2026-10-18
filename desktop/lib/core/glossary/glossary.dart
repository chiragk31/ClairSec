/// Plain-language glossary (UI_SYSTEM.md §9, FEATURES.md F6, F7, VULN_TAXONOMY.md §2).
/// Shared technical vocabulary with plain-language definitions for reports, offline assistant, and UI tooltips.
/// Tested for key parity with backend/app/core/glossary.py.
library;

class GlossaryEntry {
  const GlossaryEntry({
    required this.term,
    required this.plain,
  });

  final String term;
  final String plain;
}

const Map<String, GlossaryEntry> kGlossaryEntries = {
  'builder_agent': GlossaryEntry(
    term: 'Builder agent',
    plain: 'Reads your app and maps every door into it.',
  ),
  'attacker_agent': GlossaryEntry(
    term: 'Attacker agent',
    plain: 'Tries those doors the way a real attacker would — safely, inside a sealed copy.',
  ),
  'evaluator_agent': GlossaryEntry(
    term: 'Evaluator agent',
    plain: 'Double-checks every attack with hard rules, so nothing is reported on a hunch.',
  ),
  'fixer_agent': GlossaryEntry(
    term: 'Fixer agent',
    plain: 'Writes a code change that closes the door.',
  ),
  'verifier_agent': GlossaryEntry(
    term: 'Verifier',
    plain: 'Tries the same attack again, and checks the app still works.',
  ),
  'isolation_container': GlossaryEntry(
    term: 'Isolation / container',
    plain: 'A sealed copy of your app that can\'t touch your computer or network.',
  ),
  'BOLA': GlossaryEntry(
    term: 'BOLA (Broken Object Level Authorization)',
    plain: 'Anyone can open anyone else\'s records just by changing a number in the address.',
  ),
  'BROKEN_AUTH': GlossaryEntry(
    term: 'Broken authentication',
    plain: 'The lock on the front door can be opened without the right key.',
  ),
  'BOPLA_MASS_ASSIGN': GlossaryEntry(
    term: 'Mass assignment (BOPLA_MASS_ASSIGN)',
    plain: 'The app lets people change fields they should never control, like their own role.',
  ),
  'BOPLA_DATA_EXPOSURE': GlossaryEntry(
    term: 'Excessive data exposure (BOPLA_DATA_EXPOSURE)',
    plain: 'The app sends back more private details than the screen needs, like passwords or emails of others.',
  ),
  'BFLA': GlossaryEntry(
    term: 'BFLA (Broken Function Level Authorization)',
    plain: 'A regular user can press buttons that should only work for admins.',
  ),
  'RESOURCE_CONSUMPTION': GlossaryEntry(
    term: 'Unrestricted resource consumption (RESOURCE_CONSUMPTION)',
    plain: 'Nothing stops someone from hammering the app until it slows down or runs up costs.',
  ),
  'INJECTION': GlossaryEntry(
    term: 'Injection',
    plain: 'The app runs text a visitor typed as if it were its own instructions.',
  ),
  'SECURITY_MISCONFIG': GlossaryEntry(
    term: 'Security misconfiguration',
    plain: 'A setting was left in an unsafe default, like a debug page open to everyone.',
  ),
  'oracle': GlossaryEntry(
    term: 'Oracle',
    plain: 'A strict, automatic rule that decides whether an attack really worked.',
  ),
  'confirmed': GlossaryEntry(
    term: 'Confirmed',
    plain: 'We proved it: the attack worked, more than once.',
  ),
  'inconclusive': GlossaryEntry(
    term: 'Inconclusive',
    plain: 'Something looked wrong, but we could not prove it.',
  ),
  'regressed': GlossaryEntry(
    term: 'Regressed',
    plain: 'The fix stopped the attack but broke something else, so we don\'t count it as fixed.',
  ),
  'cvss': GlossaryEntry(
    term: 'CVSS',
    plain: 'A standard 0–10 scale for how serious a problem is.',
  ),
  'posture_score': GlossaryEntry(
    term: 'Posture score',
    plain: 'A summary of what we found and fixed — not a guarantee that nothing else exists.',
  ),
};

List<String> get kGlossaryKeys => kGlossaryEntries.keys.toList()..sort();
