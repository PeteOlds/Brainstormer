import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import 'prompts_repository.dart';
import 'package:brainstormer/core/widgets/site_header.dart';

const _providers = ['ollama', 'openai', 'anthropic', 'gemini', 'opencode'];

const _intervalLabels = {
  360: 'Every 6 hours',
  720: 'Every 12 hours',
  1440: 'Daily',
  10080: 'Weekly',
};

/// Prompt create/edit form: provider routing, allowlist-backed model
/// picker, schedule and generation basics.
///
/// Editing loads the prompt first so dropdowns show the saved values
/// instead of blank defaults (activity drill-down relies on this).
class PromptFormPage extends ConsumerStatefulWidget {
  const PromptFormPage({super.key, this.promptId});

  final String? promptId;

  @override
  ConsumerState<PromptFormPage> createState() => _PromptFormPageState();
}

class _PromptFormPageState extends ConsumerState<PromptFormPage> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  final _temperature = TextEditingController(text: '0.7');
  final _topP = TextEditingController(text: '0.9');
  final _repeatPenalty = TextEditingController(text: '1.1');
  final _numPredict = TextEditingController(text: '1000');
  final _seed = TextEditingController();
  final _keepAlive = TextEditingController(text: '2h');
  final _cronExpression = TextEditingController();
  final _slackChannel = TextEditingController();
  int _interval = 360;
  String _provider = 'ollama';
  String? _model;
  bool _active = true;
  bool _saving = false;
  bool _loading = false;
  String? _error;
  List<String> _models = const [];

  bool get _editing => widget.promptId != null;

  @override
  void initState() {
    super.initState();
    if (_editing) {
      _loading = true;
      _loadPrompt();
    } else {
      _loadModels();
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    _temperature.dispose();
    _topP.dispose();
    _repeatPenalty.dispose();
    _numPredict.dispose();
    _seed.dispose();
    _keepAlive.dispose();
    _cronExpression.dispose();
    _slackChannel.dispose();
    super.dispose();
  }

  Future<void> _loadPrompt() async {
    try {
      final prompt = await ref
          .read(promptsRepositoryProvider)
          .get(widget.promptId!);
      if (!mounted) return;
      final model = (prompt['model_name'] ?? '').toString().trim();
      setState(() {
        _title.text = (prompt['title'] ?? '').toString();
        _body.text = (prompt['prompt_body'] ?? '').toString();
        _temperature.text =
            (prompt['temperature'] ?? 0.7).toString();
        _topP.text = (prompt['top_p'] ?? 0.9).toString();
        _repeatPenalty.text =
            (prompt['repeat_penalty'] ?? 1.1).toString();
        _numPredict.text =
            (prompt['num_predict'] ?? 1000).toString();
        _seed.text = (prompt['seed'] ?? '').toString();
        _keepAlive.text = (prompt['keep_alive'] ?? '2h').toString();
        _cronExpression.text =
            (prompt['cron_expression'] ?? '').toString();
        _slackChannel.text =
            (prompt['slack_channel'] ?? '').toString();
        _provider = (prompt['provider'] ?? 'ollama').toString();
        _model = model.isEmpty ? null : model;
        _interval = (prompt['interval_minutes'] as num?)?.toInt() ?? 360;
        _active = prompt['is_active'] as bool? ?? true;
        _loading = false;
      });
      await _loadModels();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load prompt: $e';
      });
    }
  }

  Future<void> _loadModels() async {
    try {
      final repo = ref.read(promptsRepositoryProvider);
      final provider = _provider;
      final models = provider == 'ollama'
          ? await repo.ollamaModels()
          : await repo.providerModels(provider);
      if (mounted && provider == _provider) {
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
      appBar: SiteHeader(title: 'Brainstormer'),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
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
                    key: const Key('prompt_title'),
                    controller: _title,
                    decoration: const InputDecoration(labelText: 'Title *'),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  TextField(
                    key: const Key('prompt_body'),
                    controller: _body,
                    decoration: const InputDecoration(
                      labelText: 'Prompt body *',
                    ),
                    maxLines: 6,
                    spellCheckConfiguration:
                        const SpellCheckConfiguration.disabled(),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  DropdownButtonFormField<String>(
                    key: const Key('prompt_provider'),
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
                        _models = const [];
                      });
                      _loadModels();
                    },
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  DropdownButtonFormField<String>(
                    key: const Key('prompt_model'),
                    initialValue: _model,
                    decoration: const InputDecoration(labelText: 'Model'),
                    items: [
                      for (final m in <String>{..._models, ?_model})
                        DropdownMenuItem(value: m, child: Text(m)),
                    ],
                    onChanged: (v) => setState(() => _model = v),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  DropdownButtonFormField<int>(
                    key: const Key('prompt_interval'),
                    initialValue: _interval,
                    decoration: const InputDecoration(
                      labelText: 'Interval (minutes)',
                    ),
                    items: [
                      for (final minutes in <int>{
                        ..._intervalLabels.keys,
                        _interval,
                      })
                        DropdownMenuItem(
                          value: minutes,
                          child: Text(
                            _intervalLabels[minutes] ??
                                'Every $minutes minutes',
                          ),
                        ),
                    ],
                    onChanged: (v) => setState(() => _interval = v ?? 360),
                  ),
                  SwitchListTile(
                    key: const Key('prompt_active'),
                    value: _active,
                    onChanged: (v) => setState(() => _active = v),
                    title: const Text('Active'),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  ExpansionTile(
                    title: const Text('Advanced'),
                    children: [
                      TextField(
                        controller: _temperature,
                        decoration:
                            const InputDecoration(labelText: 'Temperature'),
                        keyboardType: TextInputType.number,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _topP,
                        decoration:
                            const InputDecoration(labelText: 'Top P'),
                        keyboardType: TextInputType.number,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _repeatPenalty,
                        decoration: const InputDecoration(
                            labelText: 'Repeat penalty'),
                        keyboardType: TextInputType.number,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _numPredict,
                        decoration: const InputDecoration(
                            labelText: 'Num predict'),
                        keyboardType: TextInputType.number,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _seed,
                        decoration: const InputDecoration(labelText: 'Seed'),
                        keyboardType: TextInputType.number,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _keepAlive,
                        decoration: const InputDecoration(
                            labelText: 'Keep alive'),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _cronExpression,
                        decoration: const InputDecoration(
                            labelText: 'Cron expression'),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      TextField(
                        controller: _slackChannel,
                        decoration: const InputDecoration(
                            labelText: 'Slack channel'),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                    ],
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
      await ref
          .read(promptsRepositoryProvider)
          .save(
            id: widget.promptId,
            title: _title.text.trim(),
            body: _body.text.trim(),
            intervalMinutes: _interval,
            modelName: _model!,
            provider: _provider,
            isActive: _active,
            temperature: double.tryParse(_temperature.text.trim()),
            topP: double.tryParse(_topP.text.trim()),
            repeatPenalty: double.tryParse(_repeatPenalty.text.trim()),
            numPredict: int.tryParse(_numPredict.text.trim()),
            seed: int.tryParse(_seed.text.trim()),
            keepAlive: _keepAlive.text.trim(),
            cronExpression: _cronExpression.text.trim(),
            slackChannel: _slackChannel.text.trim(),
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
