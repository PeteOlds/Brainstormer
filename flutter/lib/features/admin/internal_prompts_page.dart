import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'admin_repository.dart';

/// Site-admin page for viewing and maintaining shared AI prompt templates.
/// Per-instance idea prompts are deliberately not shown here.
class InternalPromptsPage extends ConsumerStatefulWidget {
  const InternalPromptsPage({super.key});

  @override
  ConsumerState<InternalPromptsPage> createState() => _InternalPromptsPageState();
}

class _InternalPromptsPageState extends ConsumerState<InternalPromptsPage> {
  List<Map<String, dynamic>> _rows = [];
  String? _selectedKey;
  final _controller = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final rows = await ref.read(adminRepositoryProvider).internalPrompts();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
        _error = null;
        _selectedKey ??= rows.isNotEmpty ? rows.first['key']?.toString() : null;
        _syncEditor();
      });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _syncEditor() {
    final row = _selectedRow;
    _controller.text = row?['body']?.toString() ?? '';
  }

  Map<String, dynamic>? get _selectedRow {
    if (_selectedKey == null) return null;
    for (final row in _rows) {
      if (row['key']?.toString() == _selectedKey) return row;
    }
    return null;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(adminRepositoryProvider)
          .saveInternalPrompt(_selectedKey!, _controller.text);
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Prompt saved')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _reset() async {
    setState(() => _saving = true);
    try {
      await ref.read(adminRepositoryProvider).resetInternalPrompt(_selectedKey!);
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Reset to shipped default')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      title: 'Internal AI Prompts',
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Failed to load: $_error'))
              : LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth >= 900;
                    final list = SizedBox(
                      height: wide ? double.infinity : 280,
                      child: ListView(
                        children: [
                          for (final row in _rows)
                            ListTile(
                              key: Key('prompt_${row['key']}'),
                              selected: row['key']?.toString() == _selectedKey,
                              title: Text(row['label']?.toString() ?? ''),
                              subtitle: Text(
                                '${row['key']} · ${row['source']}',
                              ),
                              onTap: () => setState(() {
                                _selectedKey = row['key']?.toString();
                                _syncEditor();
                              }),
                            ),
                        ],
                      ),
                    );
                    final editor = _selectedRow == null
                        ? const Text('Select a prompt.')
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    _selectedRow!['label']?.toString() ?? '',
                                    style:
                                        Theme.of(context).textTheme.titleMedium,
                                  ),
                                  const Spacer(),
                                  Chip(
                                    label: Text(
                                      _selectedRow!['source']?.toString() ?? '',
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: AppSpacing.sm),
                              Text(
                                'Placeholders: ${(_selectedRow!['required_placeholders'] as List? ?? []).join(', ')}',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                              const SizedBox(height: AppSpacing.sm),
                              TextField(
                                key: const Key('prompt_body'),
                                controller: _controller,
                                maxLines: 18,
                                minLines: 10,
                                decoration: const InputDecoration(
                                  labelText: 'Prompt body',
                                  border: OutlineInputBorder(),
                                ),
                              ),
                              const SizedBox(height: AppSpacing.sm),
                              Wrap(
                                spacing: AppSpacing.sm,
                                children: [
                                  FilledButton(
                                    key: const Key('prompt_save'),
                                    onPressed: _saving ? null : _save,
                                    child: Text(_saving ? 'Saving…' : 'Save'),
                                  ),
                                  if (_selectedRow!['source'] == 'override')
                                    OutlinedButton(
                                      key: const Key('prompt_reset'),
                                      onPressed: _saving ? null : _reset,
                                      child: const Text('Reset to default'),
                                    ),
                                ],
                              ),
                            ],
                          );
                    return wide
                        ? Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(child: list),
                              const SizedBox(width: AppSpacing.md),
                              Expanded(flex: 2, child: editor),
                            ],
                          )
                        : ListView(
                            children: [
                              list,
                              const SizedBox(height: AppSpacing.md),
                              editor,
                            ],
                          );
                  },
                ),
    );
  }
}
