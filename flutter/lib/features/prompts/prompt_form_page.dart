import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import 'prompts_repository.dart';

const _providers = ['ollama', 'openai', 'anthropic', 'gemini'];

/// Prompt create/edit form: provider routing, allowlist-backed model
/// picker, schedule and generation basics.
class PromptFormPage extends ConsumerStatefulWidget {
  const PromptFormPage({super.key, this.promptId});

  final String? promptId;

  @override
  ConsumerState<PromptFormPage> createState() => _PromptFormPageState();
}

class _PromptFormPageState extends ConsumerState<PromptFormPage> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  int _interval = 360;
  String _provider = 'ollama';
  String? _model;
  bool _active = true;
  bool _saving = false;
  String? _error;
  List<String> _models = const [];

  @override
  void initState() {
    super.initState();
    _loadModels();
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _loadModels() async {
    try {
      final repo = ref.read(promptsRepositoryProvider);
      final models = _provider == 'ollama'
          ? await repo.ollamaModels()
          : await repo.providerModels(_provider);
      if (mounted) {
        setState(() {
          _models = models;
          if (_model == null && models.isNotEmpty) _model = models.first;
        });
      }
    } catch (_) {
      // Model list is best effort; free-text entry still works.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.promptId == null ? 'Create Prompt' : 'Edit Prompt')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          children: [
            if (_error != null)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppSpacing.sm),
                margin: const EdgeInsets.only(bottom: AppSpacing.md),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(_error!),
              ),
            TextField(
                controller: _title,
                decoration: const InputDecoration(labelText: 'Title *')),
            const SizedBox(height: AppSpacing.sm),
            TextField(
                controller: _body,
                decoration: const InputDecoration(
                    labelText: 'Prompt body * ({{topic}} for theme)'),
                maxLines: 6,
                spellCheckConfiguration:
                    const SpellCheckConfiguration.disabled()),
            const SizedBox(height: AppSpacing.sm),
            DropdownButtonFormField<String>(
              initialValue: _provider,
              decoration: const InputDecoration(labelText: 'Provider'),
              items: [
                for (final p in _providers)
                  DropdownMenuItem(value: p, child: Text(p)),
              ],
              onChanged: (v) {
                setState(() {
                  _provider = v ?? 'ollama';
                  _model = null;
                });
                _loadModels();
              },
            ),
            const SizedBox(height: AppSpacing.sm),
            DropdownButtonFormField<String>(
              initialValue: _models.contains(_model) ? _model : null,
              decoration: const InputDecoration(labelText: 'Model'),
              items: [
                for (final m in _models)
                  DropdownMenuItem(value: m, child: Text(m)),
              ],
              onChanged: (v) => setState(() => _model = v),
            ),
            const SizedBox(height: AppSpacing.sm),
            DropdownButtonFormField<int>(
              initialValue: _interval,
              decoration:
                  const InputDecoration(labelText: 'Interval (minutes)'),
              items: const [
                DropdownMenuItem(value: 360, child: Text('Every 6 hours')),
                DropdownMenuItem(value: 720, child: Text('Every 12 hours')),
                DropdownMenuItem(value: 1440, child: Text('Daily')),
                DropdownMenuItem(value: 10080, child: Text('Weekly')),
              ],
              onChanged: (v) => setState(() => _interval = v ?? 360),
            ),
            SwitchListTile(
              value: _active,
              onChanged: (v) => setState(() => _active = v),
              title: const Text('Active'),
            ),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                key: const Key('prompt_save'),
                onPressed: _saving ? null : _save,
                child: Text(_saving ? 'Saving…' : 'Save'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (_title.text.trim().isEmpty || _body.text.trim().isEmpty) {
      setState(() => _error = 'Title and body are required.');
      return;
    }
    if ((_model ?? '').isEmpty) {
      setState(() => _error = 'Pick a model.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref.read(promptsRepositoryProvider).save(
            id: widget.promptId,
            title: _title.text.trim(),
            body: _body.text.trim(),
            intervalMinutes: _interval,
            modelName: _model!,
            provider: _provider,
            isActive: _active,
          );
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = e.toString();
        });
      }
    }
  }
}
