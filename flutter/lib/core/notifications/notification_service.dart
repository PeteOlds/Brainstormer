import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Local notifications (digest + chat replies). Remote push (FCM) is
/// pending project credentials — see flutter/README.md; this service
/// owns the channel and call sites so the swap is localised.
///
/// Testability: pass a [delegate] to capture notifications in tests
/// without touching platform plugins.
class NotificationService {
  NotificationService({
    FlutterLocalNotificationsPlugin? plugin,
    Future<void> Function(String title, String body)? delegate,
  })  : _plugin = plugin ?? FlutterLocalNotificationsPlugin(),
        _delegate = delegate;

  final FlutterLocalNotificationsPlugin _plugin;
  final Future<void> Function(String title, String body)? _delegate;
  bool _ready = false;

  Future<void> init() async {
    if (_delegate != null) {
      _ready = true;
      return;
    }
    try {
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      const darwin = DarwinInitializationSettings();
      const linux = LinuxInitializationSettings(
          defaultActionName: 'Open Brainstormer');
      await _plugin.initialize(
        const InitializationSettings(
            android: android, iOS: darwin, macOS: darwin, linux: linux),
      );
      _ready = true;
    } catch (_) {
      // Unsupported platform (e.g. web): notifications stay unavailable
      // and every show() becomes a no-op rather than a crash.
      _ready = false;
    }
  }

  bool get available => _ready || _delegate != null;

  Future<void> showIdeaDigest(int newCount) {
    if (newCount <= 0) return Future.value();
    return _show(
      'Brainstormer',
      '$newCount new idea${newCount == 1 ? '' : 's'} since your last visit',
    );
  }

  Future<void> showChatReply(String excerpt) {
    final short =
        excerpt.length > 120 ? '${excerpt.substring(0, 120)}…' : excerpt;
    return _show('New AI reply', short);
  }

  Future<void> _show(String title, String body) async {
    final delegate = _delegate;
    if (delegate != null) {
      await delegate(title, body);
      return;
    }
    if (!_ready) return;
    try {
      await _plugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        title,
        body,
        const NotificationDetails(
          android: AndroidNotificationDetails(
              'brainstormer', 'Brainstormer updates'),
        ),
      );
    } catch (_) {
      // Best effort by design.
      return;
    }
    return;
  }
}
