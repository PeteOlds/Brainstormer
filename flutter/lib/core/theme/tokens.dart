import 'package:flutter/material.dart';

/// Design tokens. Never hardcode colours, spacing or type in widgets —
/// map everything through here (mirrors the Tailwind/Inter web theme).
abstract final class AppColors {
  static const primary50 = Color(0xFFEFF6FF);
  static const primary100 = Color(0xFFDBEAFE);
  static const primary500 = Color(0xFF3B82F6);
  static const primary600 = Color(0xFF2563EB);
  static const primary700 = Color(0xFF1D4ED8);

  static const spark = Color(0xFF3B82F6);
  static const scope = Color(0xFF8B5CF6);
  static const map = Color(0xFF06B6D4);
  static const ship = Color(0xFF6366F1);
  static const scale = Color(0xFF10B981);
  static const drop = Color(0xFF94A3B8);
  static const freeze = Color(0xFFA855F7);
  static const archive = Color(0xFFF59E0B);

  static Color statusColor(String status) {
    switch (status.toUpperCase()) {
      case 'SPARK':
        return spark;
      case 'SCOPE':
        return scope;
      case 'MAP':
        return map;
      case 'SHIP':
        return ship;
      case 'SCALE':
        return scale;
      case 'DROP':
        return drop;
      case 'FREEZE':
        return freeze;
      case 'ARCHIVE':
        return archive;
      default:
        return spark;
    }
  }
}

abstract final class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
}

abstract final class AppText {
  static const String fontFamily = 'Inter';
}

/// Build version. Mirrors the backend VERSION file — bump together
/// (golden rule: the build number is always available, shown in the
/// footer of every screen).
const String kAppVersion = '0.40.0';

ThemeData buildTheme({required bool dark}) {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.primary600,
    brightness: dark ? Brightness.dark : Brightness.light,
  );
  return ThemeData(
    colorScheme: scheme,
    fontFamily: AppText.fontFamily,
    useMaterial3: true,
  );
}
