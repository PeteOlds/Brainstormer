/// Human-readable rendering for AI action results.
///
/// Models emit JSON; users need sections and bullets. Unknown keys still
/// render with a title-cased label, so a new action never shows raw braces.
const Map<String, String> _labels = {
  'summary': 'Summary',
  'scope': 'Scope',
  'architecture': 'Architecture',
  'screens': 'Screens',
  'data_model': 'Data model',
  'api_contracts': 'API contracts',
  'build_notes': 'Build notes',
  'open_questions': 'Open questions',
  'executive_summary': 'Executive summary',
  'user_personas': 'User personas',
  'product_scope': 'Product scope',
  'functional_requirements': 'Functional requirements',
  'non_functional_requirements': 'Non-functional requirements',
  'ux_guidelines': 'UX guidelines',
  'assumptions_risks': 'Assumptions, dependencies and risks',
  'screen_specs': 'Screens (structured)',
  'entity_specs': 'Data model (structured)',
  'endpoint_specs': 'API contracts (structured)',
  'strengths': 'Strengths',
  'gaps': 'Gaps',
  'suggested_features': 'Suggested features',
  'approach_suggestions': 'Approach suggestions',
  'risks': 'Risks',
};

/// Convert an action result map into readable Markdown.
String resultToMarkdown(Map<String, dynamic>? output) {
  if (output == null || output.isEmpty) return 'No content.';
  final buffer = StringBuffer();
  for (final entry in output.entries) {
    if (entry.value == null) continue;
    buffer.writeln('## ${_labelFor(entry.key)}');
    _writeValue(buffer, entry.value, 0);
    buffer.writeln();
  }
  return buffer.toString().trim();
}

String _labelFor(String key) =>
    _labels[key] ??
    key
        .replaceAll(RegExp(r'[_-]+'), ' ')
        .split(' ')
        .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
        .join(' ');

void _writeValue(StringBuffer buffer, dynamic value, int depth) {
  final indent = '  ' * depth;
  if (value is String) {
    final text = value.trim();
    if (text.isNotEmpty) buffer.writeln('$indent$text');
    return;
  }
  if (value is List) {
    for (final item in value) {
      if (item is Map) {
        _writeMapItem(buffer, item, depth);
      } else if (item != null) {
        buffer.writeln('$indent- $item');
      }
    }
    return;
  }
  if (value is Map) {
    value.forEach((key, val) {
      if (val == null) return;
      if (val is String || val is num || val is bool) {
        buffer.writeln('$indent${_labelFor(key.toString())}: $val');
      } else {
        buffer.writeln('$indent${_labelFor(key.toString())}:');
        _writeValue(buffer, val, depth + 1);
      }
    });
    return;
  }
  buffer.writeln('$indent$value');
}

void _writeMapItem(StringBuffer buffer, Map<dynamic, dynamic> item, int depth) {
  final indent = '  ' * depth;
  final entries = item.entries
      .where((e) => e.value != null)
      .map((e) => MapEntry(e.key.toString(), e.value))
      .toList();
  if (entries.isEmpty) return;
  final method = item['method']?.toString();
  final path = item['path']?.toString();
  final isEndpoint = method != null && path != null;
  final first = entries.first;
  final headline = isEndpoint
      ? '$method $path'
      : first.value is String || first.value is num
          ? '${_labelFor(first.key)}: ${first.value}'
          : _labelFor(first.key);
  buffer.writeln('$indent- $headline');
  final skip = isEndpoint ? {'method', 'path'} : {first.key};
  for (final entry in entries.where((e) => !skip.contains(e.key))) {
    if (entry.value is List) {
      final values = entry.value as List;
      final scalars = values
          .where((v) => v != null && v is! Map && v is! List)
          .map((v) => v.toString())
          .toList();
      final nested = values.where((v) => v is Map || v is List).toList();
      if (scalars.isNotEmpty) {
        buffer.writeln('$indent  ${_labelFor(entry.key)}: ${scalars.join(', ')}');
      }
      if (nested.isNotEmpty) {
        buffer.writeln('$indent  ${_labelFor(entry.key)}:');
        _writeValue(buffer, nested, depth + 2);
      }
    } else if (entry.value is Map) {
      buffer.writeln('$indent  ${_labelFor(entry.key)}:');
      _writeValue(buffer, entry.value, depth + 2);
    } else {
      buffer.writeln('$indent  ${_labelFor(entry.key)}: ${entry.value}');
    }
  }
}
