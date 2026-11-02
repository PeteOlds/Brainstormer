/* Shared AI model + parameter controls.
 *
 * Every surface that picks a model (Admin -> AI Settings stage defaults, the
 * run dialog, the per-release override, the prompt editor) must show the same
 * catalogue and the same "Custom model..." escape hatch, so the rules live
 * here once:
 *
 *   - one endpoint (/api/v1/ollama/models?provider=...) and one normaliser
 *     ({value, label}) instead of three ad-hoc parsers;
 *   - `selectValue` decides what a <select> shows for a saved model:
 *     "" (inherit) / catalogue value / "__custom__";
 *   - `pick` turns a <select> choice back into draft state.
 *
 * Markup lives in templates/partials/ai_controls.html so the fields cannot
 * drift apart either.
 */
(function (global) {
    'use strict';

    var CUSTOM = '__custom__';

    function badge(size) {
        if (size == null) return '';
        if (size < 3000000000) return ' \uD83D\uDE80';
        if (size < 7000000000) return ' \uD83D\uDC07';
        return ' \uD83D\uDC22';
    }

    function normaliseOne(m) {
        if (typeof m === 'string') {
            return { value: m, label: m };
        }
        if (!m || typeof m !== 'object') return { value: '', label: '' };
        // Cater for every shape the endpoints have returned: {model}, {id},
        // {modelID}, {name}.
        var value = m.model || m.id || m.modelID || m.name || '';
        if (!value) return { value: '', label: '' };
        var label = m.name && m.name !== value ? m.name + ' \u00B7 ' + value : value;
        return { value: value, label: label + badge(m.size) };
    }

    function normalise(list) {
        return (Array.isArray(list) ? list : [])
            .map(normaliseOne)
            .filter(function (m) { return !!m.value; });
    }

    // One fetch for every surface. Never throws: a dead provider (or an
    // offline OpenCode server) yields an empty catalogue and the caller
    // falls back to the custom input.
    async function fetchModels(provider) {
        var name = provider || 'ollama';
        var url = name === 'ollama'
            ? '/api/v1/ollama/models'
            : '/api/v1/ollama/models?provider=' + encodeURIComponent(name);
        try {
            var res = await authFetch(url);
            var data = await res.json();
            var payload = data.data || data;
            return {
                models: normalise(payload.models),
                unrestricted: name !== 'ollama' && !!payload.unrestricted,
            };
        } catch (e) {
            console.error('Failed to load models:', e);
            return { models: [], unrestricted: false };
        }
    }

    // <select> value for a saved model: blank means "inherit".
    function selectValue(current, models) {
        if (!current) return '';
        return (models || []).some(function (m) { return m.value === current; })
            ? current
            : CUSTOM;
    }

    // A saved model outside the catalogue must stay visible: the select
    // shows "Custom model..." with the text input already open.
    function isCustom(current, models) {
        if (!current) return false;
        return !(models || []).some(function (m) { return m.value === current; });
    }

    // Toggle one name in a draft array (skills/guidelines). Arrays are kept
    // as arrays end to end: no comma-splitting, no trimming bugs.
    function toggle(list, name) {
        if (!Array.isArray(list)) return;
        var i = list.indexOf(name);
        if (i === -1) list.push(name);
        else list.splice(i, 1);
    }

    function summary(list, emptyLabel) {
        var n = (list || []).length;
        if (!n) return emptyLabel || 'None';
        return n + ' selected';
    }

    function hints(list) {
        return (list || []).join(', ');
    }

    global.AIControls = {
        CUSTOM: CUSTOM,
        normalise: normalise,
        fetchModels: fetchModels,
        selectValue: selectValue,
        isCustom: isCustom,
        toggle: toggle,
        summary: summary,
        hints: hints,
    };
})(window);
