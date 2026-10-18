import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/theme/tokens.dart';
import '../../core/theme/theme_provider.dart';
import '../../providers/readiness_provider.dart';
import '../../ui/ui.dart';

/// First-run onboarding wizard restyled on ClairTokens (UI_SYSTEM.md §2, PLAN.md Round 1).
class FirstRunWizardDialog extends ConsumerStatefulWidget {
  const FirstRunWizardDialog({super.key});

  static const String dontShowAgainPrefKey = 'clairsec_wizard_dismissed';

  static Future<void> show(BuildContext context) {
    return showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const FirstRunWizardDialog(),
    );
  }

  @override
  ConsumerState<FirstRunWizardDialog> createState() => _FirstRunWizardDialogState();
}

class _FirstRunWizardDialogState extends ConsumerState<FirstRunWizardDialog> {
  int _currentStep = 0;
  bool _dontShowAgain = false;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((prefs) {
      if (mounted) {
        setState(() {
          _dontShowAgain = prefs.getBool(FirstRunWizardDialog.dontShowAgainPrefKey) ?? false;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.tokens;
    final themeSettings = ref.watch(themeSettingsProvider);
    final themeNotifier = ref.read(themeSettingsProvider.notifier);
    final readiness = ref.watch(readinessProvider);

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      insetPadding: ClairInsets.xXlYXxl,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 680, maxHeight: 600),
          child: Container(
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: BorderRadius.circular(ClairRadius.lg),
              border: Border.all(color: tokens.border, width: 1.5),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.35),
                  blurRadius: 24,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header
                Container(
                  padding: const EdgeInsets.all(ClairSpacing.xl),
                  decoration: BoxDecoration(
                    color: tokens.surfaceRaised,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(ClairRadius.lg),
                    ),
                    border: Border(bottom: BorderSide(color: tokens.border)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(ClairSpacing.sm),
                        decoration: BoxDecoration(
                          color: tokens.accentMuted,
                          borderRadius: BorderRadius.circular(ClairRadius.sm),
                          border: Border.all(color: tokens.accent.withValues(alpha: 0.3)),
                        ),
                        child: Icon(Icons.shield, color: tokens.accent, size: 24),
                      ),
                      const SizedBox(width: ClairSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Welcome to ClairSec',
                              style: TextStyle(
                                fontSize: ClairTypography.h2,
                                fontWeight: FontWeight.w700,
                                color: tokens.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Autonomous Adversarial Security Platform for FastAPI',
                              style: TextStyle(
                                fontSize: ClairTypography.body,
                                color: tokens.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                // Body
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(ClairSpacing.xl),
                    child: _currentStep == 0
                        ? _buildWorkflowIntro(tokens)
                        : _buildThemeCustomizer(tokens, themeSettings, themeNotifier, readiness),
                  ),
                ),
                // Footer
                Container(
                  padding: const EdgeInsets.all(ClairSpacing.lg),
                  decoration: BoxDecoration(
                    color: tokens.surfaceRaised,
                    borderRadius: const BorderRadius.vertical(
                      bottom: Radius.circular(ClairRadius.lg),
                    ),
                    border: Border(top: BorderSide(color: tokens.border)),
                  ),
                  child: Row(
                    children: [
                      if (_currentStep > 0)
                        CsButton(
                          label: 'Back',
                          variant: CsButtonVariant.secondary,
                          onPressed: () => setState(() => _currentStep--),
                        ),
                      if (_currentStep > 0) const SizedBox(width: ClairSpacing.md),
                      InkWell(
                        onTap: () async {
                          final next = !_dontShowAgain;
                          setState(() => _dontShowAgain = next);
                          final prefs = await SharedPreferences.getInstance();
                          await prefs.setBool(FirstRunWizardDialog.dontShowAgainPrefKey, next);
                        },
                        borderRadius: BorderRadius.circular(ClairRadius.sm),
                        child: Padding(
                          padding: ClairInsets.xSmY3,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox(
                                width: 18,
                                height: 18,
                                child: Checkbox(
                                  value: _dontShowAgain,
                                  activeColor: tokens.accent,
                                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                  onChanged: (val) async {
                                    final next = val ?? false;
                                    setState(() => _dontShowAgain = next);
                                    final prefs = await SharedPreferences.getInstance();
                                    await prefs.setBool(FirstRunWizardDialog.dontShowAgainPrefKey, next);
                                  },
                                ),
                              ),
                              const SizedBox(width: ClairSpacing.xs),
                              Text(
                                "Don't show again",
                                style: TextStyle(
                                  fontSize: ClairTypography.small,
                                  color: tokens.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const Spacer(),
                      if (_currentStep == 0)
                        CsButton(
                          label: 'Next: Appearance & Readiness',
                          onPressed: () => setState(() => _currentStep = 1),
                        )
                      else
                        CsButton(
                          label: 'Get Started',
                          onPressed: () async {
                            if (_dontShowAgain) {
                              final prefs = await SharedPreferences.getInstance();
                              await prefs.setBool(FirstRunWizardDialog.dontShowAgainPrefKey, true);
                            }
                            if (context.mounted) Navigator.of(context).pop();
                          },
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWorkflowIntro(ClairTokens tokens) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'How ClairSec Secures Your Applications',
          style: TextStyle(
            fontSize: ClairTypography.h3,
            fontWeight: FontWeight.w600,
            color: tokens.textPrimary,
          ),
        ),
        const SizedBox(height: ClairSpacing.xs),
        Text(
          'ClairSec seals your application in a hardened Docker sandbox and deploys autonomous AI agents paired with deterministic verification oracles.',
          style: TextStyle(fontSize: ClairTypography.body, color: tokens.textSecondary, height: 1.4),
        ),
        const SizedBox(height: ClairSpacing.lg),
        const CsStepper(
          steps: [
            StepData(
              title: '1. Builder Agent',
              plainLanguage: 'Reads your FastAPI app and maps every route, auth scheme, and principal.',
              status: CsStepStatus.completed,
            ),
            StepData(
              title: '2. Attacker Agent',
              plainLanguage: 'Generates and fires targeted security exploits inside a sealed copy.',
              status: CsStepStatus.completed,
            ),
            StepData(
              title: '3. Evaluator Agent',
              plainLanguage: 'Adjudicates exploits with strict, deterministic code oracles — never guesses.',
              status: CsStepStatus.completed,
            ),
            StepData(
              title: '4. Fixer Agent',
              plainLanguage: 'Synthesizes targeted AST code changes to remediate confirmed vulnerabilities.',
              status: CsStepStatus.completed,
            ),
            StepData(
              title: '5. Verifier Agent',
              plainLanguage: 'Re-executes attacks against patched code and ensures functional tests pass.',
              status: CsStepStatus.completed,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildThemeCustomizer(
    ClairTokens tokens,
    ThemeSettings settings,
    ThemeSettingsNotifier notifier,
    AsyncValue readiness,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Choose Your Theme Preset',
          style: TextStyle(
            fontSize: ClairTypography.h3,
            fontWeight: FontWeight.w600,
            color: tokens.textPrimary,
          ),
        ),
        const SizedBox(height: ClairSpacing.sm),
        Wrap(
          spacing: ClairSpacing.sm,
          runSpacing: ClairSpacing.sm,
          children: ThemePreset.values.map((p) {
            final isSelected = p == settings.preset;
            return InkWell(
              onTap: () => notifier.setPreset(p),
              borderRadius: BorderRadius.circular(ClairRadius.sm),
              child: Container(
                padding: ClairInsets.xMdYSm,
                decoration: BoxDecoration(
                  color: isSelected ? tokens.accentMuted : tokens.surfaceRaised,
                  borderRadius: BorderRadius.circular(ClairRadius.sm),
                  border: Border.all(
                    color: isSelected ? tokens.accent : tokens.border,
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: Text(
                  p.label,
                  style: TextStyle(
                    fontSize: ClairTypography.code,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                    color: isSelected ? tokens.accent : tokens.textPrimary,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: ClairSpacing.xl),
        Text(
          'System Readiness Check',
          style: TextStyle(
            fontSize: ClairTypography.h3,
            fontWeight: FontWeight.w600,
            color: tokens.textPrimary,
          ),
        ),
        const SizedBox(height: ClairSpacing.sm),
        readiness.when(
          loading: () => const Text('Probing backend and Docker...'),
          error: (_, _) => const Text('Backend unreachable'),
          data: (r) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (r.mode != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: ClairSpacing.sm),
                  child: Row(
                    children: [
                      Text('Active Mode: ', style: TextStyle(color: tokens.textSecondary, fontSize: ClairTypography.body)),
                      ModeBadge(modeId: r.mode!.id, label: r.mode!.label),
                    ],
                  ),
                ),
              for (final c in r.checks)
                Padding(
                  padding: ClairInsets.yXxs,
                  child: Row(
                    children: [
                      Icon(c.ok ? Icons.check_circle : Icons.cancel,
                          size: 14, color: c.ok ? tokens.success : tokens.critical),
                      const SizedBox(width: ClairSpacing.sm),
                      Text(c.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: ClairTypography.small)),
                      const SizedBox(width: ClairSpacing.sm),
                      Text(c.detail, style: TextStyle(color: tokens.textSecondary, fontSize: ClairTypography.small)),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
