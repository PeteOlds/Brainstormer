/// Tiny TTL cache for idempotent GETs. Stale entries serve as the
/// offline fallback; mutations invalidate by collection prefix.
class OfflineCache {
  OfflineCache({DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final DateTime Function() _now;
  final Map<String, _Entry> _entries = {};

  String keyFor(String method, String path, String query) =>
      '$method $path?$query';

  dynamic get(String key) {
    final entry = _entries[key];
    if (entry == null) return null;
    // Expired entries stay cached: getStale() serves them offline.
    if (_now().isAfter(entry.expiresAt)) return null;
    return entry.value;
  }

  dynamic getStale(String key) => _entries[key]?.value;

  void set(String key, dynamic value, Duration ttl) {
    _entries[key] =
        _Entry(value, _now().add(ttl), _now());
  }

  void invalidate() => _entries.clear();

  void invalidatePrefix(String prefix) {
    _entries.removeWhere((key, _) => key.contains(prefix));
  }

  int get length => _entries.length;
}

class _Entry {
  _Entry(this.value, this.expiresAt, this.storedAt);

  final dynamic value;
  final DateTime expiresAt;
  final DateTime storedAt;
}
