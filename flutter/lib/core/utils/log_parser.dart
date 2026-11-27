/// Read the managed-app logs payload from either the api_ok envelope or the
/// unwrapped body. The backend returns `lines`; older code looked for `logs`.
String logsFromPayload(dynamic data) {
  final payload = data is Map ? (data['data'] is Map ? data['data'] : data) : null;
  final lines = payload?['lines'];
  if (lines is List && lines.isNotEmpty) {
    return lines.map((line) => line.toString()).join('\n');
  }
  final logs = payload?['logs'];
  if (logs is String && logs.isNotEmpty) return logs;
  return 'No output yet.';
}
