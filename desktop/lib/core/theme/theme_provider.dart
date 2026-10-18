import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'tokens.dart';

enum DensitySetting {
  comfortable,
  compact;

  String get label => switch (this) {
        DensitySetting.comfortable => 'Comfortable',
        DensitySetting.compact => 'Compact',
      };
}

enum ReduceMotionSetting {
  system,
  on,
  off;

  String get label => switch (this) {
        ReduceMotionSetting.system => 'System',
        ReduceMotionSetting.on => 'On',
        ReduceMotionSetting.off => 'Off',
      };
}

class ThemeSettings {
  const ThemeSettings({
    this.mode = ThemeMode.system,
    this.preset = ThemePreset.midnightDaylight,
    this.density = DensitySetting.comfortable,
    this.textScale = 1.0,
    this.reduceMotion = ReduceMotionSetting.system,
    this.presenterMode = false,
  });

  final ThemeMode mode;
  final ThemePreset preset;
  final DensitySetting density;
  final double textScale;
  final ReduceMotionSetting reduceMotion;

  /// Presenter mode (FEATURES.md F14): larger type for projectors, developer
  /// details such as the token/cost meter hidden.
  final bool presenterMode;

  /// Text scale actually applied: presenter mode never goes below 1.25.
  double get effectiveTextScale => presenterMode && textScale < 1.25 ? 1.25 : textScale;

  ThemeSettings copyWith({
    ThemeMode? mode,
    ThemePreset? preset,
    DensitySetting? density,
    double? textScale,
    ReduceMotionSetting? reduceMotion,
    bool? presenterMode,
  }) {
    return ThemeSettings(
      mode: mode ?? this.mode,
      preset: preset ?? this.preset,
      density: density ?? this.density,
      textScale: textScale ?? this.textScale,
      reduceMotion: reduceMotion ?? this.reduceMotion,
      presenterMode: presenterMode ?? this.presenterMode,
    );
  }
}

class ThemeSettingsNotifier extends Notifier<ThemeSettings> {
  SharedPreferences? _prefs;

  static const _keyMode = 'clairsec_theme_mode';
  static const _keyPreset = 'clairsec_theme_preset';
  static const _keyDensity = 'clairsec_theme_density';
  static const _keyTextScale = 'clairsec_text_scale';
  static const _keyReduceMotion = 'clairsec_reduce_motion';
  static const _keyPresenter = 'clairsec_presenter_mode';

  @override
  ThemeSettings build() {
    _init();
    return const ThemeSettings();
  }

  Future<void> _init() async {
    _prefs ??= await SharedPreferences.getInstance();
    final p = _prefs!;

    final modeIndex = p.getInt(_keyMode);
    final presetIndex = p.getInt(_keyPreset);
    final densityIndex = p.getInt(_keyDensity);
    final textScale = p.getDouble(_keyTextScale);
    final reduceMotionIndex = p.getInt(_keyReduceMotion);

    state = ThemeSettings(
      mode: modeIndex != null && modeIndex >= 0 && modeIndex < ThemeMode.values.length
          ? ThemeMode.values[modeIndex]
          : ThemeMode.system,
      preset: presetIndex != null && presetIndex >= 0 && presetIndex < ThemePreset.values.length
          ? ThemePreset.values[presetIndex]
          : ThemePreset.midnightDaylight,
      density: densityIndex != null && densityIndex >= 0 && densityIndex < DensitySetting.values.length
          ? DensitySetting.values[densityIndex]
          : DensitySetting.comfortable,
      textScale: textScale != null && textScale >= 0.8 && textScale <= 1.5 ? textScale : 1.0,
      reduceMotion: reduceMotionIndex != null &&
              reduceMotionIndex >= 0 &&
              reduceMotionIndex < ReduceMotionSetting.values.length
          ? ReduceMotionSetting.values[reduceMotionIndex]
          : ReduceMotionSetting.system,
      presenterMode: (_prefs?.getBool(_keyPresenter)) ?? false,
    );
  }

  void loadFromPrefs(SharedPreferences prefs) {
    _prefs = prefs;
    final modeIndex = prefs.getInt(_keyMode);
    final presetIndex = prefs.getInt(_keyPreset);
    final densityIndex = prefs.getInt(_keyDensity);
    final textScale = prefs.getDouble(_keyTextScale);
    final reduceMotionIndex = prefs.getInt(_keyReduceMotion);

    state = ThemeSettings(
      mode: modeIndex != null && modeIndex >= 0 && modeIndex < ThemeMode.values.length
          ? ThemeMode.values[modeIndex]
          : ThemeMode.system,
      preset: presetIndex != null && presetIndex >= 0 && presetIndex < ThemePreset.values.length
          ? ThemePreset.values[presetIndex]
          : ThemePreset.midnightDaylight,
      density: densityIndex != null && densityIndex >= 0 && densityIndex < DensitySetting.values.length
          ? DensitySetting.values[densityIndex]
          : DensitySetting.comfortable,
      textScale: textScale != null && textScale >= 0.8 && textScale <= 1.5 ? textScale : 1.0,
      reduceMotion: reduceMotionIndex != null &&
              reduceMotionIndex >= 0 &&
              reduceMotionIndex < ReduceMotionSetting.values.length
          ? ReduceMotionSetting.values[reduceMotionIndex]
          : ReduceMotionSetting.system,
      presenterMode: (_prefs?.getBool(_keyPresenter)) ?? false,
    );
  }

  Future<void> setPresenterMode(bool on) async {
    state = state.copyWith(presenterMode: on);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setBool(_keyPresenter, on);
  }

  Future<void> setMode(ThemeMode mode) async {
    state = state.copyWith(mode: mode);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setInt(_keyMode, mode.index);
  }

  Future<void> setPreset(ThemePreset preset) async {
    state = state.copyWith(preset: preset);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setInt(_keyPreset, preset.index);
  }

  Future<void> setDensity(DensitySetting density) async {
    state = state.copyWith(density: density);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setInt(_keyDensity, density.index);
  }

  Future<void> setTextScale(double scale) async {
    final clamped = scale.clamp(0.9, 1.3);
    state = state.copyWith(textScale: clamped);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setDouble(_keyTextScale, clamped);
  }

  Future<void> setReduceMotion(ReduceMotionSetting reduceMotion) async {
    state = state.copyWith(reduceMotion: reduceMotion);
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setInt(_keyReduceMotion, reduceMotion.index);
  }
}

final themeSettingsProvider =
    NotifierProvider<ThemeSettingsNotifier, ThemeSettings>(() {
  return ThemeSettingsNotifier();
});
