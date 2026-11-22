import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import 'package:brainstormer/core/widgets/site_header.dart';

/// Instance member roster. Server enforces the guards (never self,
/// never the last admin); the UI surfaces the messages.
class UsersPage extends ConsumerStatefulWidget {
  const UsersPage({super.key});

  @override
  ConsumerState<UsersPage> createState() => _UsersPageState();
}

class _UsersPageState extends ConsumerState<UsersPage> {
  @override
  Widget build(BuildContext context) {
    final iid = ref.watch(currentInstanceProvider);
    if (iid == null) {
      return Scaffold(
        appBar: SiteHeader(title: 'Brainstormer'),
        body: const Center(child: Text('Pick an instance first.')),
      );
    }
    final members = ref.watch(_membersProvider(iid));
    return Scaffold(
      appBar: SiteHeader(title: 'Brainstormer'),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Text('Users',
                style: TextStyle(
                    fontSize: 20, fontWeight: FontWeight.bold)),
          ),
          Expanded(
            child: members.when(
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) =>
                  Center(child: Text('Failed to load: $e')),
              data: (items) => ListView.builder(
                padding: const EdgeInsets.all(AppSpacing.md),
                itemCount: items.length,
                itemBuilder: (context, i) {
                  final m = items[i];
                  final avatar = (m['avatar_url'] ?? '').toString();
                  return Card(
                    child: ListTile(
                      leading: CircleAvatar(
                        backgroundImage: avatar.isNotEmpty
                            ? NetworkImage(avatar)
                            : null,
                        child: avatar.isEmpty
                            ? Text(((m['email'] ?? '?')
                                    .toString())
                                .substring(0, 1)
                                .toUpperCase())
                            : null,
                      ),
                      title: Text(
                          ((m['email'] ?? m['user_id']) ?? '').toString()),
                      subtitle: Text((m['role'] ?? '').toString()),
                      trailing: PopupMenuButton<String>(
                        onSelected: (v) => _act(
                            context, iid, (m['user_id'] ?? '').toString(), v, m),
                        itemBuilder: (context) => const [
                          PopupMenuItem(
                              value: 'INSTANCE_ADMIN',
                              child: Text('Make admin')),
                          PopupMenuItem(
                              value: 'PRODUCT_MANAGER', child: Text('Make product manager')),
                          PopupMenuItem(
                              value: 'USER', child: Text('Make user')),
                          PopupMenuItem(
                              value: 'edit', child: Text('Edit name/email')),
                          PopupMenuItem(
                              value: 'reset_password', child: Text('Reset password')),
                          PopupMenuItem(
                              value: 'remove', child: Text('Remove'))
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _act(BuildContext context, String iid, String memberId,
      String action, Map<String, dynamic> m) async {
    final api = ref.read(apiClientProvider);
    try {
      if (action == 'edit') {
        final nameCtrl = TextEditingController(
            text: (m['name'] ?? '').toString());
        final emailCtrl = TextEditingController(
            text: (m['email'] ?? '').toString());
        final avatarCtrl = TextEditingController(
            text: (m['avatar_url'] ?? '').toString());
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Edit member'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                    controller: nameCtrl,
                    decoration:
                        const InputDecoration(labelText: 'Name')),
                TextField(
                    controller: emailCtrl,
                    decoration:
                        const InputDecoration(labelText: 'Email')),
                TextField(
                    controller: avatarCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Avatar URL')),
                const SizedBox(height: 8),
                FilledButton.tonal(
                  onPressed: () async {
                    final picker = ImagePicker();
                    final picked = await picker.pickImage(
                        source: ImageSource.gallery);
                    if (picked == null) return;
                    final bytes = await picked.readAsBytes();
                    final req = await ref
                        .read(apiClientProvider)
                        .postMultipart(
                      '/api/v1/me/avatar',
                      bytes: bytes,
                      filename: picked.name,
                    );
                    // ignore: use_build_context_synchronously
                    if (context.mounted) {
                      final map = req as Map<String, dynamic>;
                      avatarCtrl.text =
                          (map['avatar_url'] ?? '').toString();
                    }
                  },
                  child: const Text('Upload avatar'),
                ),
              ],
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Cancel')),
              FilledButton(
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Save')),
            ],
          ),
        );
        if (ok == true) {
          await api.patch('/api/v1/instances/$iid/members/$memberId',
              body: {
                'name': nameCtrl.text.trim(),
                'email': emailCtrl.text.trim(),
                'avatar_url': avatarCtrl.text.trim(),
              });
        }
        nameCtrl.dispose();
        emailCtrl.dispose();
        avatarCtrl.dispose();
      } else if (action == 'remove') {
        await api.delete('/api/v1/instances/$iid/members/$memberId');
      } else if (action == 'reset_password') {
        final res = await api.post(
            '/api/v1/instances/$iid/members/$memberId/reset-password');
        final map = res as Map<String, dynamic>;
        final temp = (map['temp_password'] ?? '').toString();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Temp password: $temp')),
          );
        }
      } else {
        await api.patch('/api/v1/instances/$iid/members/$memberId',
            body: {'role': action});
      }
      ref.invalidate(_membersProvider(iid));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    }
  }
}

final _membersProvider = FutureProvider.family
    .autoDispose<List<Map<String, dynamic>>, String>((ref, iid) async {
  final data =
      await ref.watch(apiClientProvider).get('/api/v1/instances/$iid/members');
  final list = ((data as Map<String, dynamic>)['members'] as List? ?? []);
  return [
    for (final e in list)
      (e as Map).map((k, v) => MapEntry(k.toString(), v))
  ];
});