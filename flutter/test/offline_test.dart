import 'package:brainstormer/core/network/offline_cache.dart';
import 'package:brainstormer/core/notifications/notification_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('OfflineCache', () {
    test('fresh entries serve, expired do not', () {
      var now = DateTime(2026, 1, 1);
      final cache = OfflineCache(clock: () => now);
      cache.set('k', {'a': 1}, const Duration(minutes: 5));
      expect(cache.get('k'), {'a': 1});
      now = now.add(const Duration(minutes: 6));
      expect(cache.get('k'), isNull);
    });

    test('stale fallback survives expiry', () {
      var now = DateTime(2026, 1, 1);
      final cache = OfflineCache(clock: () => now);
      cache.set('k', 'v', const Duration(seconds: 1));
      now = now.add(const Duration(hours: 1));
      expect(cache.get('k'), isNull);
      expect(cache.getStale('k'), 'v');
    });

    test('prefix invalidation clears collections only', () {
      final cache = OfflineCache();
      cache.set('GET /api/v1/ideas?a=1', 1, const Duration(minutes: 5));
      cache.set('GET /api/v1/prompts', 2, const Duration(minutes: 5));
      cache.invalidatePrefix('/api/v1/ideas');
      expect(cache.get('GET /api/v1/ideas?a=1'), isNull);
      expect(cache.get('GET /api/v1/prompts'), 2);
    });

    test('keyFor distinguishes methods and queries', () {
      final cache = OfflineCache();
      final a = cache.keyFor('GET', '/x', 'a=1');
      final b = cache.keyFor('GET', '/x', 'a=2');
      final c = cache.keyFor('POST', '/x', 'a=1');
      expect({a, b, c}, hasLength(3));
    });
  });

  group('NotificationService', () {
    test('digest fires only for positive counts', () async {
      final seen = <List<String>>[];
      final service = NotificationService(
          delegate: (t, b) async => seen.add([t, b]));
      await service.init();
      expect(service.available, isTrue);
      await service.showIdeaDigest(0);
      expect(seen, isEmpty);
      await service.showIdeaDigest(3);
      expect(seen, hasLength(1));
      expect(seen.single[1], contains('3 new ideas'));
    });

    test('chat replies truncate long excerpts', () async {
      final seen = <List<String>>[];
      final service = NotificationService(
          delegate: (t, b) async => seen.add([t, b]));
      await service.init();
      await service.showChatReply('${'x' * 200}');
      expect(seen.single[1].endsWith('…'), isTrue);
    });
  });
}
