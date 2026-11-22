import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import 'ideas_controller.dart';

/// Create a new idea manually (title + content) or by uploading a
/// markdown/text file.  BUG.034 / BUG.035.
class CreateIdeaPage extends ConsumerStatefulWidget {
  const CreateIdeaPage({super.key});

  @override
  ConsumerState<CreateIdeaPage> createState() => _CreateIdeaPageState();
}

class _CreateIdeaPageState extends ConsumerState<CreateIdeaPage> {
  final _titleCtrl = TextEditingController();
  final _contentCtrl = TextEditingController();
  bool _submitting = false;
  String? _error;

  Future<void> _submit() async {
    final title = _titleCtrl.text.trim();
    final content = _contentCtrl.text.trim();
    if (title.isEmpty || content.isEmpty) {
      setState(() => _error = 'Title and content are required.');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(ideasRepositoryProvider).create(title, content);
      if (!mounted) return;
      ref.read(ideasControllerProvider.notifier).load(fresh: true);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        setState(() => _error = e.toString());
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _uploadFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['md', 'txt'],
      withData: true,
    );
    if (result == null || result.files.isEmpty || result.files.first.bytes == null) {
      return;
    }
    final file = result.files.first;
    if (file.size > 10 * 1024 * 1024) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('File too large (max 10 MB)')),
        );
      }
      return;
    }
    final content = utf8.decode(file.bytes!);
    _contentCtrl.text = content;
    if (_titleCtrl.text.isEmpty) {
      // Derive a title from the filename
      final name = file.name;
      final base = name.contains('.') ? name.substring(0, name.lastIndexOf('.')) : name;
      _titleCtrl.text = base;
    }
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _contentCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      title: 'New Idea',
      child: _submitting
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(AppSpacing.md),
              children: [
                TextField(
                  controller: _titleCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Title',
                    hintText: 'Enter a title for your idea',
                  ),
                  maxLength: 200,
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  controller: _contentCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Content',
                    hintText: 'Describe your idea…',
                  ),
                  maxLines: 10,
                  maxLength: 2000,
                ),
                const SizedBox(height: AppSpacing.md),
                Row(
                  children: [
                    FilledButton.tonal(
                      onPressed: _uploadFile,
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.upload_file, size: 18),
                          SizedBox(width: 6),
                          Text('Upload .md / .txt'),
                        ],
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    const Text(
                      'Or paste content above.',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.md),
                    child: Text(
                      _error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _submit,
                    child: const Text('Create Idea'),
                  ),
                ),
              ],
            ),
    );
  }
}
