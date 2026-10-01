SETTINGS_TEMPLATE = """
{% extends "base.html" %}

{% block title %}System Settings - Admin{% endblock %}

{% block content %}
<div class="space-y-6">
    <div class="flex items-center justify-between">
        <div>
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">System Settings</h1>
            <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">Configure platform, location, and AI connection settings</p>
        </div>
        <a href="/admin" class="px-4 py-2 min-h-[44px] text-sm font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            Back to Dashboard
        </a>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Platform</h2>
            <div class="space-y-4" x-data="settingsForm('platform')">
                <div>
                    <label for="platform_title" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Title <span class="text-red-500">*</span></label>
                    <input type="text" id="platform_title" name="title" x-model="form.title" maxlength="250"
                        class="block w-full px-3 py-2 min-h-[44px] text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        placeholder="e.g., Web Based">
                    <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Max 250 characters</p>
                </div>
                <div>
                    <label for="platform_description" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Description</label>
                    <textarea id="platform_description" name="description" x-model="form.description" maxlength="1000" rows="4"
                        class="block w-full px-3 py-2 min-h-[44px] text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        placeholder="Full technology description"></textarea>
                    <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Max 1000 characters</p>
                </div>
                <div>
                    <h3 class="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Platform Types</h3>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3" x-data="{ checkboxes: ['web', 'android', 'ios', 'plugin', 'standalone', 'test_env', 'github'] }">
                        <template x-for="key in checkboxes" :key="key">
                            <label class="inline-flex items-center space-x-2 cursor-pointer">
                                <input type="checkbox" :id="key" :name="key" :value="true"
                                    :checked="form.types[key]"
                                    @change="form.types[key] = $event.target.checked"
                                    class="w-4 h-4 text-primary-600 border-slate-300 rounded focus:ring-primary-500">
                                <span class="text-sm text-slate-700 dark:text-slate-300 capitalize" x-text="key.replace(/_/g, ' ')"></span>
                            </label>
                        </template>
                    </div>
                </div>
                <div class="flex justify-end pt-4 border-t border-slate-200 dark:border-slate-700">
                    <button @click="save('platform')" :disabled="saving" class="px-4 py-2 min-h-[44px] text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                        <span x-show="!saving">Save Platform Settings</span>
                        <span x-show="saving" class="flex items-center"><svg class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg> Saving...</span>
                    </button>
                </div>
            </div>
        </div>

        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Location</h2>
            <div class="space-y-4" x-data="settingsForm('location')">
                <div>
                    <label for="location_country" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Country <span class="text-red-500">*</span></label>
                    <select id="location_country" name="country" x-model="form.country"
                        class="block w-full px-3 py-2 min-h-[44px] text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500">
                        <option value="">Select country</option>
                        <option value="NZ">New Zealand</option>
                        <option value="AU">Australia</option>
                        <option value="US">United States</option>
                        <option value="GB">United Kingdom</option>
                        <option value="CA">Canada</option>
                        <option value="DE">Germany</option>
                        <option value="FR">France</option>
                        <option value="JP">Japan</option>
                        <option value="SG">Singapore</option>
                        <option value="OTHER">Other</option>
                    </select>
                </div>
                <div class="flex justify-end pt-4 border-t border-slate-200 dark:border-slate-700">
                    <button @click="save('location')" :disabled="saving" class="px-4 py-2 min-h-[44px] text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                        <span x-show="!saving">Save Location</span>
                        <span x-show="saving" class="flex items-center"><svg class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg> Saving...</span>
                    </button>
                </div>
            </div>
        </div>

        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">AI Connections</h2>
            <div class="space-y-4" x-data="settingsForm('ai_connections')">
                <p class="text-sm text-slate-500 dark:text-slate-400">Placeholder for future AI service connections (OpenAI, Anthropic, etc.)</p>
                <div class="p-4 rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700">
                    <p class="text-sm text-slate-600 dark:text-slate-400">No AI connections configured yet.</p>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">This section will support external LLM provider integrations in future releases.</p>
                </div>
                <div class="flex justify-end pt-4 border-t border-slate-200 dark:border-slate-700">
                    <button @click="save('ai_connections')" :disabled="saving" class="px-4 py-2 min-h-[44px] text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                        <span x-show="!saving">Save (Placeholder)</span>
                        <span x-show="saving" class="flex items-center"><svg class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg> Saving...</span>
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    function settingsForm(section) {
        return {
            form: {
                title: '',
                description: '',
                types: { web: true, android: false, ios: false, plugin: false, standalone: false, test_env: false, github: true },
                country: '',
            },
            saving: false,
            async init() { await this.load(); },
            async load() {
                try {
                    const res = await fetch('/api/v1/admin/settings', { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
                    const data = await res.json();
                    if (data.data) {
                        const s = data.data;
                        if (s.platform) { this.form.title = s.platform.title || ''; this.form.description = s.platform.description || ''; this.form.types = { ...this.form.types, ...(s.platform.types || {}) }; }
                        if (s.location) { this.form.country = s.location.country || ''; }
                    }
                } catch (e) { console.error('Failed to load settings:', e); }
            },
            async save(section) {
                this.saving = true;
                try {
                    let endpoint, payload;
                    if (section === 'platform') { endpoint = '/api/v1/admin/settings/platform'; payload = { title: this.form.title, description: this.form.description, types: this.form.types }; }
                    else if (section === 'location') { endpoint = '/api/v1/admin/settings/location'; payload = { country: this.form.country }; }
                    else { endpoint = '/api/v1/admin/settings/ai_connections'; payload = {}; }
                    const res = await fetch(endpoint, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token') }, body: JSON.stringify(payload) });
                    const data = await res.json();
                    if (res.ok) { this.showToast('Saved successfully'); } else { this.showToast(data.message || 'Save failed', 'error'); }
                } catch (e) { this.showToast('Save failed: ' + e.message, 'error'); } finally { this.saving = false; }
            },
            showToast(message, type = 'success') {
                const toast = document.createElement('div');
                toast.className = `fixed bottom-4 right-4 px-4 py-3 rounded-lg shadow-lg text-white text-sm ${type === 'success' ? 'bg-emerald-600' : 'bg-red-600'} z-50`;
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }
        }
    }
</script>
{% endblock %}

"""