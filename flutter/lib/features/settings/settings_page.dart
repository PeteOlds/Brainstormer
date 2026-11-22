import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import '../admin/admin_repository.dart';

const _providers = ['ollama', 'openai', 'anthropic', 'gemini', 'opencode'];
const _stages = ['SPARK', 'SCOPE', 'MAP', 'SHIP', 'SCALE'];
const _cutoffBehaviours = ['refuse', 'queue', 'degrade'];

/// Instance settings: editable AI provider configs, per-phase AI defaults
/// and spend. Instance admins only — enforced server-side.
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  int _tab = 0;

  String? get _instanceId => ref.watch(currentInstanceProvider);

  void _refresh(String iid) {
    ref.invalidate(settingsBundleProvider(iid));
  }

  @override
  Widget build(BuildContext context) {
    final iid = _instanceId;
    if (iid == null) {
      return const AppShell(
        title: 'Instance settings',
        child: Center(child: Text('Pick an instance first.')),
      );
    }
    final bundle = ref.watch(settingsBundleProvider(iid));
    return AppShell(
      title: 'Instance settings',
      child: bundle.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load settings: $e')),
        data: (data) {
          final configs = (data['configs'] as List)
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final stages = (data['stages'] as List)
              .map((e) => (e as Map).map((k, v) => MapEntry(k.toString(), v)))
              .toList();
          final spend = data['spend'] as Map<String, dynamic>;
          final discovery =
              data['discovery'] as Map<String, List<Map<String, dynamic>>>;
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: SegmentedButton<int>(
                  key: const Key('settings_tabs'),
                  segments: const [
                    ButtonSegment(
                      value: 0,
                      label: Text('AI providers'),
                      icon: Icon(Icons.key_outlined),
                    ),
                    ButtonSegment(
                      value: 1,
                      label: Text('Phase defaults'),
                      icon: Icon(Icons.tune),
                    ),
                    ButtonSegment(
                      value: 2,
                      label: Text('Spend'),
                      icon: Icon(Icons.payments_outlined),
                    ),
                    ButtonSegment(
                      value: 3,
                      label: Text('Guides'),
                      icon: Icon(Icons.description_outlined),
                    ),
                  ],
                  selected: {_tab},
                  onSelectionChanged: (v) => setState(() => _tab = v.first),
                ),
              ),
              Expanded(
                child: switch (_tab) {
                  1 => _StagesTab(
                    instanceId: iid,
                    stages: stages,
                    discovery: discovery,
                    onSaved: () => _refresh(iid),
                  ),
                  2 => _SpendTab(spend: spend),
                  3 => _GuidesTab(instanceId: iid),
                  _ => _ProvidersTab(
                    instanceId: iid,
                    configs: configs,
                    isSiteAdmin:
                        ref.watch(currentUserProvider)?['is_site_admin'] ==
                        true,
                    onSaved: () => _refresh(iid),
                  ),
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// AI providers
// ---------------------------------------------------------------------------

class _ProvidersTab extends StatelessWidget {
  const _ProvidersTab({
    required this.instanceId,
    required this.configs,
    required this.isSiteAdmin,
    required this.onSaved,
  });

  final String instanceId;
  final List<Map<String, dynamic>> configs;
  final bool isSiteAdmin;
  final VoidCallback onSaved;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.md,
      ),
      children: [
        const Text(
          'Provider configs are stored per instance. Keys are write-only: '
          'leave the key blank to keep the saved one.',
        ),
        const SizedBox(height: AppSpacing.md),
        for (final provider in _providers)
          _ProviderCard(
            provider: provider,
            config: configs.where((c) => c['provider'] == provider).firstOrNull,
            instanceId: instanceId,
            isSiteAdmin: isSiteAdmin,
            onSaved: onSaved,
          ),
      ],
    );
  }
}

extension<T> on Iterable<T> {
  T? get firstOrNull {
    for (final item in this) {
      return item;
    }
    return null;
  }
}

class _ProviderCard extends ConsumerWidget {
  const _ProviderCard({
    required this.provider,
    required this.config,
    required this.instanceId,
    required this.isSiteAdmin,
    required this.onSaved,
  });

  final String provider;
  final Map<String, dynamic>? config;
  final String instanceId;
  final bool isSiteAdmin;
  final VoidCallback onSaved;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final configured = config != null;
    final allowlist = (config?['model_allowlist'] as List? ?? []).join(', ');
    final budget = config?['budget_cents'];
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Semantics(
        button: true,
        label: '$provider ${configured ? 'configured' : 'inherits'}',
        child: ListTile(
          key: Key('provider_card_$provider'),
          onTap: () => showDialog<void>(
            context: context,
            builder: (context) => _ProviderDialog(
              provider: provider,
              config: config,
              instanceId: instanceId,
              isSiteAdmin: isSiteAdmin,
              onSaved: onSaved,
            ),
          ),
          title: Row(
            children: [
              Text(
                provider,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(width: AppSpacing.sm),
              Chip(
                visualDensity: VisualDensity.compact,
                label: Text(configured ? 'configured' : 'inherits'),
              ),
            ],
          ),
          subtitle: Text(
            [
              if (configured && config?['has_key'] == true) 'key saved',
              if (allowlist.isNotEmpty) 'models: $allowlist',
              if (budget is num)
                'budget \$${(budget / 100).toStringAsFixed(2)}',
              if (configured && config?['chat_enabled'] == true) 'chat on',
              if (configured && config?['use_proxy'] == true) 'proxy',
            ].join(' · '),
          ),
          trailing: Text(
            configured ? 'Edit' : 'Configure',
            style: TextStyle(color: Theme.of(context).colorScheme.primary),
          ),
        ),
      ),
    );
  }
}

class _ProviderDialog extends ConsumerStatefulWidget {
  const _ProviderDialog({
    required this.provider,
    required this.config,
    required this.instanceId,
    required this.isSiteAdmin,
    required this.onSaved,
  });

  final String provider;
  final Map<String, dynamic>? config;
  final String instanceId;
  final bool isSiteAdmin;
  final VoidCallback onSaved;

  @override
  ConsumerState<_ProviderDialog> createState() => _ProviderDialogState();
}

class _ProviderDialogState extends ConsumerState<_ProviderDialog> {
  @override
  void initState() {
    super.initState();
    _selectedAllowlist = {
      for (final m in (widget.config?['model_allowlist'] as List? ?? []))
        m.toString(),
    };
    _loadModels();
  }

  Future<void> _loadModels() async {
    setState(() => _loadingModels = true);
    try {
      // Use include_catalogue so the picker shows all catalogue models
      // plus the currently selected allowlist entries.
      final data = await ref
          .read(apiClientProvider)
          .get('/api/v1/ollama/models',
              query: {
                'provider': widget.provider,
                'include_catalogue': '1',
              });
      final list = ((data as Map<String, dynamic>)['models'] as List? ?? []);
      if (mounted) {
        setState(() {
          _models = [for (final e in list) e.toString()];
          _loadingModels = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingModels = false);
    }
  }

  late final _key = TextEditingController();
  late final _endpoint = TextEditingController(
    text: (widget.config?['endpoint'] ?? '').toString(),
  );
  late Set<String> _selectedAllowlist;
  List<String> _models = const [];
  bool _loadingModels = false;
  late final _embeddingModel = TextEditingController(
    text: (widget.config?['embedding_model'] ?? '').toString(),
  );
  late final _budget = TextEditingController(
    text: widget.config?['budget_cents'] == null
        ? ''
        : (widget.config!['budget_cents'] / 100).toStringAsFixed(2),
  );
  late final _degradeModel = TextEditingController(
    text: (widget.config?['degrade_model'] ?? '').toString(),
  );
  late String _cutoff = (widget.config?['cutoff_behaviour'] ?? 'refuse')
      .toString();
  late bool _chatEnabled = widget.config?['chat_enabled'] == true;
  late bool _useProxy = widget.config?['use_proxy'] == true;
  late String _workspace = (widget.config?['opencode_workspace'] ?? 'sandbox')
      .toString();
  bool _saving = false;
  bool _testing = false;
  String? _error;
  String? _testResult;

  @override
  void dispose() {
    _key.dispose();
    _endpoint.dispose();
    _embeddingModel.dispose();
    _budget.dispose();
    _degradeModel.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _testResult = null;
    });
    try {
      final key = _key.text.trim();
      final endpoint = _endpoint.text.trim();
      final model = _selectedAllowlist.isNotEmpty
          ? _selectedAllowlist.first
          : null;
      final body = <String, dynamic>{
        'provider': widget.provider,
        if (key.isNotEmpty) 'key': key,
        if (endpoint.isNotEmpty) 'endpoint': endpoint,
        'model': ?model,
      };
      final res = await ref
          .read(apiClientProvider)
          .post('/api/v1/instances/${widget.instanceId}/ai-configs/test',
              body: body);
      final map = res as Map<String, dynamic>;
      setState(() {
        _testResult = (map['ok'] == true)
            ? 'OK: ${(map['reply'] ?? map['models'] ?? '').toString()}'
            : 'Failed: ${(map['error'] ?? 'unknown').toString()}';
      });
    } catch (e) {
      setState(() => _testResult = 'Failed: $e');
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final allowlist = _selectedAllowlist.toList();
      final budgetText = _budget.text.trim();
      final budgetCents = budgetText.isEmpty
          ? null
          : (double.parse(budgetText) * 100).round();
      final body = <String, dynamic>{
        'provider': widget.provider,
        if (_key.text.trim().isNotEmpty) 'key': _key.text.trim(),
        'endpoint': _endpoint.text.trim().isEmpty
            ? null
            : _endpoint.text.trim(),
        'model_allowlist': allowlist,
        'embedding_model': _embeddingModel.text.trim().isEmpty
            ? null
            : _embeddingModel.text.trim(),
        'budget_cents': budgetCents,
        'cutoff_behaviour': _cutoff,
        'degrade_model': _degradeModel.text.trim().isEmpty
            ? null
            : _degradeModel.text.trim(),
        'chat_enabled': _chatEnabled,
        'use_proxy': _useProxy,
        if (widget.provider == 'opencode') 'opencode_workspace': _workspace,
      };
      await ref
          .read(adminRepositoryProvider)
          .saveAiConfig(widget.instanceId, body);
      widget.onSaved();
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

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.provider} settings'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              TextField(
                key: const Key('provider_key_field'),
                controller: _key,
                obscureText: true,
                decoration: InputDecoration(
                  labelText: 'API key',
                  helperText: widget.config?['has_key'] == true
                      ? 'Saved key present — leave blank to keep it'
                      : 'Write-only; never shown again',
                ),
              ),
              TextField(
                key: const Key('provider_endpoint_field'),
                controller: _endpoint,
                decoration: const InputDecoration(
                  labelText: 'Endpoint (optional)',
                ),
              ),
              if (_loadingModels)
                const Center(child: CircularProgressIndicator())
              else
                Wrap(
                  spacing: AppSpacing.xs,
                  children: [
                    for (final m in <String>{..._models, ..._selectedAllowlist})
                      FilterChip(
                        key: Key('provider_allowlist_$m'),
                        label: Text(m),
                        selected: _selectedAllowlist.contains(m),
                        onSelected: (v) => setState(() {
                          if (v) {
                            _selectedAllowlist.add(m);
                          } else {
                            _selectedAllowlist.remove(m);
                          }
                        }),
                      ),
                  ],
                ),
              TextField(
                key: const Key('provider_embedding_field'),
                controller: _embeddingModel,
                decoration: const InputDecoration(
                  labelText: 'Embedding model (optional)',
                ),
              ),
              TextField(
                key: const Key('provider_budget_field'),
                controller: _budget,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Monthly budget (dollars, blank = none)',
                ),
              ),
              DropdownButtonFormField<String>(
                key: const Key('provider_cutoff_field'),
                initialValue: _cutoff,
                decoration: const InputDecoration(
                  labelText: 'When the budget runs out',
                ),
                items: [
                  for (final behaviour in _cutoffBehaviours)
                    DropdownMenuItem(value: behaviour, child: Text(behaviour)),
                ],
                onChanged: (v) => setState(() => _cutoff = v ?? 'refuse'),
              ),
              TextField(
                key: const Key('provider_degrade_field'),
                controller: _degradeModel,
                decoration: const InputDecoration(
                  labelText: 'Fallback model when degrading (optional)',
                ),
              ),
              if (_testResult != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_testResult!),
                ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _chatEnabled,
                onChanged: (v) => setState(() => _chatEnabled = v),
                title: const Text('Chat enabled'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _useProxy,
                onChanged: (v) => setState(() => _useProxy = v),
                title: const Text('Use proxy'),
                subtitle: const Text('Requires a provisioned proxy key'),
              ),
              if (widget.provider == 'opencode')
                DropdownButtonFormField<String>(
                  key: const Key('provider_workspace_field'),
                  initialValue: _workspace,
                  decoration: const InputDecoration(
                    labelText: 'OpenCode workspace',
                  ),
                  items: const [
                    DropdownMenuItem(value: 'sandbox', child: Text('sandbox')),
                    DropdownMenuItem(value: 'repo', child: Text('repo')),
                  ],
                  onChanged: widget.isSiteAdmin
                      ? (v) => setState(() => _workspace = v ?? 'sandbox')
                      : null,
                ),
              if (widget.provider == 'opencode' && !widget.isSiteAdmin)
                Text(
                  'Only a Site Admin can change the OpenCode workspace.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: _testing ? null : _test,
          child: Text(_testing ? 'Testing…' : 'Test'),
        ),
        FilledButton(
          key: const Key('provider_save'),
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Per-phase defaults
// ---------------------------------------------------------------------------

class _StagesTab extends StatelessWidget {
  const _StagesTab({
    required this.instanceId,
    required this.stages,
    required this.discovery,
    required this.onSaved,
  });

  final String instanceId;
  final List<Map<String, dynamic>> stages;
  final Map<String, List<Map<String, dynamic>>> discovery;
  final VoidCallback onSaved;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.md,
      ),
      children: [
        const Text(
          'Default provider, model, generation params, skills and guides for '
          'each lifecycle phase. Unset values inherit from the provider '
          'config, then system defaults.',
        ),
        const SizedBox(height: AppSpacing.md),
        for (final stage in _stages)
          _StageCard(
            stage: stage,
            config: stages.where((s) => s['stage'] == stage).firstOrNull,
            instanceId: instanceId,
            discovery: discovery,
            onSaved: onSaved,
          ),
      ],
    );
  }
}

class _StageCard extends StatelessWidget {
  const _StageCard({
    required this.stage,
    required this.config,
    required this.instanceId,
    required this.discovery,
    required this.onSaved,
  });

  final String stage;
  final Map<String, dynamic>? config;
  final String instanceId;
  final Map<String, List<Map<String, dynamic>>> discovery;
  final VoidCallback onSaved;

  bool get _configured =>
      config != null &&
      (config!['provider'] != null ||
          config!['model_name'] != null ||
          config!['temperature'] != null ||
          config!['top_p'] != null ||
          config!['num_predict'] != null ||
          (config!['skills'] as List? ?? []).isNotEmpty ||
          (config!['guidelines'] as List? ?? []).isNotEmpty);

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Semantics(
        button: true,
        label: '$stage ${_configured ? 'configured' : 'inherits'}',
        child: ListTile(
          key: Key('stage_card_$stage'),
          onTap: () => showDialog<void>(
            context: context,
            builder: (context) => _StageDialog(
              stage: stage,
              config: config,
              instanceId: instanceId,
              discovery: discovery,
              onSaved: onSaved,
            ),
          ),
          title: Row(
            children: [
              Text(stage, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: AppSpacing.sm),
              Chip(
                visualDensity: VisualDensity.compact,
                label: Text(_configured ? 'configured' : 'inherits'),
              ),
            ],
          ),
          subtitle: Text(
            _configured
                ? [
                    if (config!['provider'] != null) config!['provider'],
                    if (config!['model_name'] != null) config!['model_name'],
                    if (config!['temperature'] != null)
                      'temp ${config!['temperature']}',
                    if (config!['top_p'] != null) 'top_p ${config!['top_p']}',
                    if (config!['num_predict'] != null)
                      '${config!['num_predict']} tokens',
                    '${(config!['skills'] as List? ?? []).length} skills',
                    '${(config!['guidelines'] as List? ?? []).length} guides',
                  ].join(' · ')
                : 'Uses the provider defaults',
          ),
          trailing: Text(
            _configured ? 'Edit' : 'Configure',
            style: TextStyle(color: Theme.of(context).colorScheme.primary),
          ),
        ),
      ),
    );
  }
}

class _StageDialog extends ConsumerStatefulWidget {
  const _StageDialog({
    required this.stage,
    required this.config,
    required this.instanceId,
    required this.discovery,
    required this.onSaved,
  });

  final String stage;
  final Map<String, dynamic>? config;
  final String instanceId;
  final Map<String, List<Map<String, dynamic>>> discovery;
  final VoidCallback onSaved;

  @override
  ConsumerState<_StageDialog> createState() => _StageDialogState();
}

class _StageDialogState extends ConsumerState<_StageDialog> {
  late String? _provider = widget.config?['provider']?.toString();
  late final _model = TextEditingController(
    text: (widget.config?['model_name'] ?? '').toString(),
  );
  late final _temperature = TextEditingController(
    text: widget.config?['temperature']?.toString() ?? '',
  );
  late final _topP = TextEditingController(
    text: widget.config?['top_p']?.toString() ?? '',
  );
  late final _numPredict = TextEditingController(
    text: widget.config?['num_predict']?.toString() ?? '',
  );
  late final Set<String> _skills = {
    for (final s in (widget.config?['skills'] as List? ?? [])) s.toString(),
  };
  late final Set<String> _guidelines = {
    for (final g in (widget.config?['guidelines'] as List? ?? [])) g.toString(),
  };
  bool _advanced = false;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _model.dispose();
    _temperature.dispose();
    _topP.dispose();
    _numPredict.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final model = _model.text.trim();
    if (_provider == 'opencode' && model.isNotEmpty && !model.contains('/')) {
      setState(
        () => _error =
            "OpenCode models use 'provider/model' (e.g. opencode/beam-free).",
      );
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = <String, dynamic>{
        'stage': widget.stage,
        'provider': _provider,
        'model_name': model.isEmpty ? null : model,
        'temperature': _temperature.text.trim().isEmpty
            ? null
            : double.tryParse(_temperature.text.trim()),
        'top_p': _topP.text.trim().isEmpty
            ? null
            : double.tryParse(_topP.text.trim()),
        'num_predict': _numPredict.text.trim().isEmpty
            ? null
            : int.tryParse(_numPredict.text.trim()),
        'skills': _skills.toList(),
        'guidelines': _guidelines.toList(),
      };
      await ref
          .read(adminRepositoryProvider)
          .saveStageConfig(widget.instanceId, body);
      widget.onSaved();
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

  Future<void> _clear() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref
          .read(adminRepositoryProvider)
          .saveStageConfig(widget.instanceId, {
            'stage': widget.stage,
            'provider': null,
            'model_name': null,
            'temperature': null,
            'top_p': null,
            'num_predict': null,
            'skills': <String>[],
            'guidelines': <String>[],
          });
      widget.onSaved();
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

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.stage} defaults'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              DropdownButtonFormField<String?>(
                key: const Key('stage_provider_field'),
                initialValue: _provider,
                decoration: const InputDecoration(
                  labelText: 'Provider (blank inherits)',
                ),
                items: const [
                  DropdownMenuItem(value: null, child: Text('Inherit')),
                  DropdownMenuItem(value: 'ollama', child: Text('ollama')),
                  DropdownMenuItem(value: 'openai', child: Text('openai')),
                  DropdownMenuItem(
                    value: 'anthropic',
                    child: Text('anthropic'),
                  ),
                  DropdownMenuItem(value: 'gemini', child: Text('gemini')),
                  DropdownMenuItem(value: 'opencode', child: Text('opencode')),
                ],
                onChanged: (v) => setState(() => _provider = v),
              ),
              TextField(
                key: const Key('stage_model_field'),
                controller: _model,
                decoration: const InputDecoration(
                  labelText: 'Model (blank inherits)',
                  helperText: "OpenCode needs 'provider/model'",
                ),
              ),
              TextButton(
                key: const Key('stage_advanced_toggle'),
                onPressed: () => setState(() => _advanced = !_advanced),
                child: Text(
                  _advanced ? 'Hide advanced settings' : 'Advanced settings',
                ),
              ),
              if (_advanced) ...[
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        key: const Key('stage_temperature_field'),
                        controller: _temperature,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Temperature (0–2)',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: TextField(
                        key: const Key('stage_top_p_field'),
                        controller: _topP,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'top_p (0–1)',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: TextField(
                        key: const Key('stage_num_predict_field'),
                        controller: _numPredict,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'num_predict',
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
              const Text(
                'Skills',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              _ChipPicker(
                key: const Key('stage_skills'),
                options: [
                  for (final skill in widget.discovery['skills'] ?? [])
                    (skill['name'] ?? '').toString(),
                ].where((e) => e.isNotEmpty).toList(),
                selected: _skills,
                onToggle: (name) => setState(() {
                  if (!_skills.remove(name)) _skills.add(name);
                }),
              ),
              const SizedBox(height: AppSpacing.sm),
              const Text(
                'Guidelines',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              _ChipPicker(
                key: const Key('stage_guidelines'),
                options: [
                  for (final guide in widget.discovery['guidelines'] ?? [])
                    (guide['name'] ?? guide['file'] ?? '').toString(),
                ].where((e) => e.isNotEmpty).toList(),
                selected: _guidelines,
                onToggle: (name) => setState(() {
                  if (!_guidelines.remove(name)) _guidelines.add(name);
                }),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          key: const Key('stage_clear'),
          onPressed: _saving ? null : _clear,
          child: const Text('Reset to inherit'),
        ),
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const Key('stage_save'),
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}

class _ChipPicker extends StatelessWidget {
  const _ChipPicker({
    super.key,
    required this.options,
    required this.selected,
    required this.onToggle,
  });

  final List<String> options;
  final Set<String> selected;
  final ValueChanged<String> onToggle;

  @override
  Widget build(BuildContext context) {
    if (options.isEmpty) {
      return const Text(
        'Nothing discovered yet.',
        style: TextStyle(fontSize: 12),
      );
    }
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: [
        for (final option in options)
          FilterChip(
            label: Text(option, style: const TextStyle(fontSize: 11)),
            selected: selected.contains(option),
            onSelected: (_) => onToggle(option),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Spend
// ---------------------------------------------------------------------------

class _SpendTab extends StatelessWidget {
  const _SpendTab({required this.spend});

  final Map<String, dynamic> spend;

  @override
  Widget build(BuildContext context) {
    final byProvider = spend['by_provider'] as Map? ?? {};
    final budgets = spend['budgets'] as Map? ?? {};
    final providers = <String>{
      ...byProvider.keys.map((e) => e.toString()),
      ...budgets.keys.map((e) => e.toString()),
    }.toList()..sort();
    if (providers.isEmpty) {
      return const Center(child: Text('No AI spend recorded yet.'));
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.md,
      ),
      children: [
        Text(
          'Rolling ${spend['window_days'] ?? 30} days · costs in dollars',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.md),
        for (final provider in providers)
          Card(
            margin: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: ListTile(
              title: Text(
                provider,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              subtitle: Text(
                '${byProvider[provider]?['prompt_tokens'] ?? 0} prompt + '
                '${byProvider[provider]?['completion_tokens'] ?? 0} completion '
                'tokens',
              ),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    _money(byProvider[provider]?['cost_cents']),
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  if (budgets[provider]?['budget_cents'] != null)
                    Text(
                      'of ${_money(budgets[provider]!['budget_cents'])}'
                      '${budgets[provider]!['exhausted'] == true ? ' · exhausted' : ''}',
                      style: TextStyle(
                        fontSize: 11,
                        color: budgets[provider]!['exhausted'] == true
                            ? Theme.of(context).colorScheme.error
                            : null,
                      ),
                    ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  static String _money(dynamic cents) {
    if (cents is num) return '\$${(cents / 100).toStringAsFixed(2)}';
    return '–';
  }
}

// ---------------------------------------------------------------------------
// Guides upload (paid instances)
// ---------------------------------------------------------------------------

class _GuidesTab extends ConsumerStatefulWidget {
  const _GuidesTab({required this.instanceId});
  final String instanceId;

  @override
  ConsumerState<_GuidesTab> createState() => _GuidesTabState();
}

class _GuidesTabState extends ConsumerState<_GuidesTab> {
  bool _uploading = false;

  Future<void> _upload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['md'],
      withData: true,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.bytes == null) return;
    if (file.size > 10 * 1024 * 1024) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('File too large (max 10 MB)')),
        );
      }
      return;
    }
    setState(() => _uploading = true);
    try {
      await ref.read(apiClientProvider).postMultipart(
            '/api/v1/instances/${widget.instanceId}/guides',
            bytes: file.bytes!,
            filename: file.name,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Guide uploaded')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Upload failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FilledButton.icon(
            onPressed: _uploading ? null : _upload,
            icon: const Icon(Icons.upload_file),
            label: Text(_uploading ? 'Uploading…' : 'Upload guide (.md)'),
          ),
          const SizedBox(height: AppSpacing.md),
          const Text(
            'Guide uploads are only available for paid instances.',
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

final settingsBundleProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, String>((ref, instanceId) async {
      final repo = ref.watch(adminRepositoryProvider);
      final results = await Future.wait<dynamic>([
        repo.aiConfigs(instanceId),
        repo.stageConfigs(instanceId),
        repo.spend(instanceId),
        repo.discovery(),
      ]);
      return {
        'configs': results[0],
        'stages': results[1],
        'spend': results[2],
        'discovery': results[3],
      };
    });
