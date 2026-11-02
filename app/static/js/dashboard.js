
function ideasApp() {
    return {
        ideas: [],
        filteredIdeas: [],
        prompts: [],
        loading: false,
        voteLoading: null,
        actionLoading: null,
        detailModalOpen: false,
        newActionOpen: false,
        selectedIdea: null,
        commentDraft: '',
        replyTo: null,
        editingCommentId: null,
        editDraft: '',
        commentPosting: false,
        editingIdea: false,
        editTitle: '',
        editBody: '',
        editSaving: false,
        editStructured: false,
        editFields: {},
        editFieldDefs: [
            { key: 'elevator_pitch', label: 'Elevator Pitch', max: 500 },
            { key: 'target_audience', label: 'Target Audience', max: 300 },
            { key: 'core_value_proposition', label: 'Core Value Proposition', max: 500 },
            { key: 'monetization_strategy', label: 'Monetization Strategy', max: 300 },
        ],
        currentPage: 1,
        pageSize: 10,
        total: 0,
        totalPages: 1,
        totalIdeas: 0,
        isAdmin: false,
        currentUserId: null,
        dropdownOpenId: null,
        lastUpdated: '',
        availableActions: [],
        activeTab: 'overview',
        prdAnswers: {},
        docThreads: {},
        docDrafts: {},
        docViewVersion: {},
        managedApp: null,
        appBusy: false,
        appLogText: '',
        // Scale-phase collaboration state.
        scaleParent: null,
        scaleChildren: [],
        scaleReleases: [],
        buildStatus: {},
        // Test tab state (manual + imported test cases).
        ideaTests: [],
        testsLoading: false,
        testSummary: null,
        newTestName: '',
        newTestType: 'unit',
        newTestDescription: '',
        editingTestId: null,
        editTestName: '',
        editTestStatus: 'not_run',
        editTestCoverage: '',
        editTestOutput: '',
        testStatusFilter: 'all',
        buildPollTimer: null,
        relAiDraft: {},
        // Model catalogue per provider (one fetch shared by every release
        // card), plus per-release UI state for the custom-model input and
        // the skills/guidelines panels.
        relAiModels: {},
        relAiCustom: {},
        relAiOpen: {},
        childModalOpen: false,
        childKind: 'enhancement',
        childTitle: '',
        childBody: '',
        childLoading: false,
        childError: '',
        releaseBusy: false,
        releaseMove: {},
        unassignedMove: null,
        exportMsg: '',
        docEditing: null,
        docEditList: [],
        docEditError: '',
        docEditSaving: false,
        filters: { status: 'active', sort: 'created_at', search: '', prompt_id: '', model: '' },
        showMoreFilters: false,
        canCreateIdeas: true,
        createIdeaModalOpen: false,
        createIdeaTitle: '',
        createIdeaContent: '',
        createIdeaStructured: {},
        createIdeaLoading: false,
        createIdeaError: '',
        createIdeaFieldDefs: [
            { key: 'elevator_pitch', label: 'Elevator Pitch', max: 500 },
            { key: 'target_audience', label: 'Target Audience', max: 300 },
            { key: 'core_value_proposition', label: 'Core Value Proposition', max: 500 },
            { key: 'monetization_strategy', label: 'Monetization Strategy', max: 300 },
        ],
        showCreateDetails: false,

        // Confirmation modal state (reusable for Refine/PRD)
        confirmModalOpen: false,
        confirmModalLoading: false,
        confirmModalMessage: '',
        confirmModalDetail: '',
        confirmModalActionLabel: '',
        confirmModalActionType: '',
        confirmModalIdeaId: null,
        confirmModalAnswers: [],
        confirmModalResolve: null,
        confirmModalReject: null,

        // Alert modal state
        alertModalOpen: false,
        alertModalMessage: '',
        alertModalResolve: null,

        // Prompt modal state
        promptModalOpen: false,
        promptModalMessage: '',
        promptModalValue: '',
        promptModalPlaceholder: '',
        promptModalResolve: null,
        promptModalReject: null,

        pendingRunExtra: null,

        // Auto-refresh state: paused on user interaction so content doesn't
        // shift mid-tap / mid-read.
        refreshPaused: false,
        justUpdated: false,
        initialized: false,

        // Run dialog state (provider + model + skills + guidelines per run)
        runDialogOpen: false,
        runDialogIdeaId: null,
        runDialogIdeaRef: '',
        runDialogInstanceId: null,
        runDialogActionType: '',
        runDialogActionLabel: '',
        runDialogProvider: 'ollama',
        runDialogBaseProvider: 'ollama',
        runDialogProviders: ['ollama', 'openai', 'anthropic', 'gemini', 'opencode'],
        runDialogModel: '',
        runDialogCustom: false,
        runAiOpen: {},
        runDialogTarget: '',
        runDialogTargets: [],
        runDialogTargetDefaults: {},
        runDialogIdeaRef: '',
        runDialogNewRepo: false,
        runDialogNewRepoName: '',
        runDialogNewRepoPath: '',
        creatingRepo: false,
        runDialogSkills: [],
        runDialogGuidelines: [],
        runDialogAdvanced: false,
        buildTargetChoices: [],
        buildTargetChoice: '',
        ollamaModels: [],
        discoverySkills: [],
        discoveryGuidelines: [],

        // Bulk actions state
        selectedIdeaIds: [],
        bulkStatus: '',
        bulkUpdating: false,
        showBulkConfirm: false,
        bulkConfirmMessage: '',
        bulkConfirmDetail: '',
        bulkConfirmActionLabel: '',

        // Follow-up AI actions come from the server registry
        // (GET /api/v1/actions), so new actions appear with no UI changes.
        async loadActions() {
            try {
                const response = await authFetch('/api/v1/actions');
                const data = await response.json();
                const payload = data.data || data;
                this.availableActions = payload.actions || [];
            } catch (error) {
                console.error('Failed to load actions:', error);
            }
        },

        async loadUserSettings() {
            try {
                const response = await authFetch('/api/v1/me');
                if (response.ok) {
                    const data = await response.json();
                    const user = (data.data || data).user || {};
                    this.canCreateIdeas = user.can_create_ideas ?? true;
                }
            } catch (error) {
                console.error('Failed to load user settings:', error);
                this.canCreateIdeas = true;
            }
        },

        async init() {
            // Deep links (e.g. from /admin/activity): ?status=&prompt=&model=
            // status=all selects "All statuses" (needed by health links).
            const query = new URLSearchParams(window.location.search);
            const qStatus = query.get('status');
            if (qStatus === 'all') {
                this.filters.status = '';
            } else if (qStatus) {
                this.filters.status = qStatus;
            }
            const qPrompt = query.get('prompt');
            if (qPrompt) this.filters.prompt_id = qPrompt;
            const qModel = query.get('model');
            if (qModel) this.filters.model = qModel;
            await Promise.all([this.loadIdeas(), this.loadTotalIdeas(), this.loadPrompts(), this.checkAdmin(), this.loadActions(), this.loadUserSettings()]);
            // Deep link from admin activity: ?idea=<id> opens the detail modal.
            const qIdea = query.get('idea');
            if (qIdea) await this.openIdeaById(qIdea);
            // Deep link from home: ?new=true opens the create idea modal inline.
            if (query.get('new')) {
                this.openCreateIdeaModal();
            }
            // Live updates: refresh the list every 30s while the page is
            // visible and no modal is open, so new ideas appear by themselves.
            // Pauses on user interaction so content doesn't shift mid-tap.
            let refreshTimer = null;
            const startRefresh = () => {
                if (refreshTimer) return;
                refreshTimer = setInterval(() => {
                    if (!this.refreshPaused && document.visibilityState === 'visible' && !this.loading && !this.detailModalOpen && !this.runDialogOpen && !this.confirmModalOpen && !this.createIdeaModalOpen) {
                        this.loadIdeas();
                    }
                }, 30000);
            };
            const pauseRefresh = () => { this.refreshPaused = true; };
            const resumeRefresh = () => { this.refreshPaused = false; };
            startRefresh();
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && !this.refreshPaused && !this.loading && !this.detailModalOpen && !this.runDialogOpen && !this.confirmModalOpen && !this.createIdeaModalOpen) {
                    this.loadIdeas();
                }
            });
            // Pause auto-refresh on any user interaction so content doesn't
            // shift mid-tap / mid-read.
            ['mousedown','keydown','scroll','touchstart'].forEach((ev) => {
                window.addEventListener(ev, pauseRefresh, { passive: true, once: true });
                window.addEventListener(ev, resumeRefresh, { passive: true });
            });
            // Auto-refresh when filters change (reset to first page: the
            // server paginates, so a stale page could be empty).
            this.$watch('filters.status', () => { this.currentPage = 1; this.loadIdeas(); });
            this.$watch('filters.search', () => { this.currentPage = 1; this.loadIdeas(); });
            this.$watch('filters.prompt_id', () => { this.currentPage = 1; this.loadIdeas(); });
            this.$watch('filters.model', () => { this.currentPage = 1; this.loadIdeas(); });
            this.$watch('filters.sort', () => { this.currentPage = 1; this.loadIdeas(); });
        },
        
        async loadIdeas() {
            this.loading = true;
            try {
                const params = new URLSearchParams({
                    page: this.currentPage,
                    limit: this.pageSize,
                    sort_by: this.filters.sort,
                });
                // 'active' is understood by the API (excludes dropped/archived).
                if (this.filters.status) {
                    params.append('status', this.filters.status);
                }
                if (this.filters.search) params.append('search', this.filters.search);
                if (this.filters.prompt_id) params.append('prompt_config_id', this.filters.prompt_id);
                if (this.filters.model) params.append('model', this.filters.model);
                
                const response = await authFetch(`/api/v1/ideas?${params}`);
                const data = await response.json();
                const payload = data.data || data;
                this.ideas = payload.ideas || [];
                // Server-side filtering/sorting/pagination: the payload is
                // the current page; totals come from the server.
                this.filteredIdeas = [...this.ideas];
                this.total = payload.total ?? this.ideas.length;
                const pages = payload.pages ?? Math.ceil(this.total / this.pageSize);
                this.totalPages = Math.max(pages, 1);
                if (this.currentPage > this.totalPages) {
                    this.currentPage = this.totalPages;
                }
            } catch (error) {
                console.error('Failed to load ideas:', error);
            } finally {
                this.loading = false;
                this.lastUpdated = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                this.justUpdated = !this.initialized ? false : true;
                this.initialized = true;
                setTimeout(() => { this.justUpdated = false; }, 3000);
            }
        },
        
        async loadPrompts() {
            try {
                const response = await authFetch('/api/v1/prompts');
                const data = await response.json();
                const payload = data.data || data;
                this.prompts = payload.prompts || [];
                this.applyFilters();
            } catch (error) {
                console.error('Failed to load prompts:', error);
            }
        },
        
        async checkAdmin() {
            try {
                const response = await authFetch('/api/v1/admin/stats');
                this.isAdmin = response.ok;
            } catch (error) {
                this.isAdmin = false;
            }
            try {
                const me = await authFetch('/api/v1/me');
                if (me.ok) {
                    const data = await me.json();
                    this.currentUserId = (data.data || data).user?.id || null;
                }
            } catch (error) {
                this.currentUserId = null;
            }
        },
        
        applyFilters() {
            // Filtering, sorting and pagination happen server-side
            // (see loadIdeas). This keeps client copies in sync when
            // auxiliary data (e.g. prompts) finishes loading.
            this.filteredIdeas = [...this.ideas];
        },
        
        get paginatedIdeas() {
            // The server already returns the current page.
            return this.filteredIdeas;
        },

        async prevPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
                await this.loadIdeas();
            }
        },

        async nextPage() {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                await this.loadIdeas();
            }
        },

        async loadTotalIdeas() {
            // Grand total (unfiltered) for the header count indicator.
            try {
                const response = await authFetch('/api/v1/ideas?limit=1');
                const data = await response.json();
                const payload = data.data || data;
                this.totalIdeas = payload.total ?? 0;
            } catch (error) {
                console.error('Failed to load total ideas:', error);
            }
        },
        
        async refreshIdeas() {
            await this.loadIdeas();
        },
        
        async loadIdeaDetail(ideaId) {
            try {
                const response = await authFetch(`/api/v1/ideas/${ideaId}`);
                const data = await response.json();
                const payload = data.data || data;
                this.selectedIdea = payload.idea;
                this.selectedIdea.actions = payload.actions || [];
                this.selectedIdea.edit_history = payload.edit_history || [];
                this.editingIdea = false;
                // Admin-only: present only when the API includes it.
                this.selectedIdea.generation_seconds = payload.generation_seconds ?? null;
                this.selectedIdea.rendered_content = this.prettyContent(this.selectedIdea);
                this.selectedIdea.actions = this.selectedIdea.actions.map(a => ({
                    ...a,
                    rendered_output: this.prettyActionOutput(this.displayOutput(a))
                }));
                this.loadScaleFamily();
                this.loadBuildTargetChoices(this.selectedIdea.instance_id);
                // Reload after the detail assignment: openDetailModal fires
                // loadComments concurrently, and the detail response (without
                // comments) would otherwise wipe a faster comments response.
                this.loadComments(ideaId);
            } catch (error) {
                console.error('Failed to load idea detail:', error);
            }
        },
        
        openDetailModal(idea) {
            this.selectedIdea = { ...idea };
            this.activeTab = 'overview';
            this.prdAnswers = {};
            this.docViewVersion = {};
            this.exportMsg = '';
            this.buildTargetChoices = [];
            this.buildTargetChoice = '';
            this.loadIdeaDetail(idea.id);
            this.loadComments(idea.id);
            this.detailModalOpen = true;
        },

        async openIdeaById(ideaId) {
            try {
                const res = await authFetch(`/api/v1/ideas/${ideaId}`);
                if (!res.ok) return;
                const data = await res.json();
                const idea = (data.data || data).idea;
                if (idea) this.openDetailModal(idea);
            } catch (e) {
                console.error('Failed to open linked idea:', e);
            }
        },
        
        closeDetailModal() {
            this.detailModalOpen = false;
            this.newActionOpen = false;
            this.dropdownOpenId = null;
            this.selectedIdea = null;
            this.commentDraft = '';
            this.replyTo = null;
            this.editingCommentId = null;
            this.docThreads = {};
            this.docDrafts = {};
            this.cancelDocEdit();
            this.scaleParent = null;
            this.scaleChildren = [];
            this.scaleReleases = [];
            this.buildStatus = {};
            this.relAiDraft = {};
            this.stopBuildPolling();
            this.childModalOpen = false;
            // Actions may have run inside the modal: refresh the list so
            // chips, counts and statuses stop showing stale data.
            this.loadIdeas();
            this.loadTotalIdeas();
        },

        openCreateIdeaModal() {
            this.createIdeaTitle = '';
            this.createIdeaContent = '';
            this.createIdeaStructured = {};
            this.createIdeaError = '';
            this.showCreateDetails = false;
            this.createIdeaModalOpen = true;
        },

        closeCreateIdeaModal() {
            this.createIdeaModalOpen = false;
            this.createIdeaTitle = '';
            this.createIdeaContent = '';
            this.createIdeaStructured = {};
            this.createIdeaError = '';
            this.showCreateDetails = false;
        },

        async createIdea() {
            this.createIdeaError = '';
            const title = (this.createIdeaTitle || '').trim();
            const content = (this.createIdeaContent || '').trim();
            if (!title) {
                this.createIdeaError = 'Title is required.';
                return;
            }
            if (title.length > 200) {
                this.createIdeaError = 'Title must be 200 characters or fewer.';
                return;
            }
            if (!content) {
                this.createIdeaError = 'Content is required.';
                return;
            }
            // Validate structured fields if any
            const structured = {};
            for (const def of this.createIdeaFieldDefs) {
                const val = (this.createIdeaStructured[def.key] || '').trim();
                if (val) {
                    if (val.length > def.max) {
                        this.createIdeaError = `${def.label} must be ${def.max} characters or fewer.`;
                        return;
                    }
                    structured[def.key] = val;
                }
            }
            this.createIdeaLoading = true;
            try {
                const response = await authFetch('/api/v1/ideas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt_title: title,
                        raw_content: content,
                        structured_content: Object.keys(structured).length ? structured : null,
                    }),
                });
                const data = await response.json();
                if (!response.ok) {
                    const err = data.error || data.message || 'Failed to create idea';
                    this.createIdeaError = err;
                    return;
                }
                this.closeCreateIdeaModal();
                await this.loadIdeas();
                await this.loadTotalIdeas();
                // Open the new idea in the detail modal
                if (data.data?.id) {
                    this.openDetailModal(data.data);
                }
            } catch (error) {
                console.error('Failed to create idea:', error);
                this.createIdeaError = 'Failed to create idea. Please try again.';
            } finally {
                this.createIdeaLoading = false;
            }
        },

        async loadComments(ideaId) {
            try {
                const res = await authFetch(`/api/v1/ideas/${ideaId}/comments`);
                const data = await res.json();
                if (this.selectedIdea && res.ok) {
                    this.selectedIdea.comments = (data.data || data).comments || [];
                }
            } catch (e) {
                console.error('Failed to load comments:', e);
            }
        },

        async loadIdeaTests() {
            if (!this.selectedIdea) return;
            this.testsLoading = true;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests`);
                const data = await res.json();
                if (res.ok) {
                    this.ideaTests = (data.data || data).tests || [];
                }
                const s = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests/summary`);
                const sd = await s.json();
                if (s.ok) this.testSummary = (sd.data || sd);
            } catch (e) {
                console.error('Failed to load tests:', e);
            } finally {
                this.testsLoading = false;
            }
        },

        async addIdeaTest() {
            if (!this.selectedIdea || !this.newTestName.trim()) return;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests`, {
                    method: 'POST',
                    body: JSON.stringify({
                        name: this.newTestName.trim(),
                        test_type: this.newTestType,
                        description: this.newTestDescription.trim() || null,
                    }),
                });
                if (res.ok) {
                    this.newTestName = '';
                    this.newTestDescription = '';
                    await this.loadIdeaTests();
                }
            } catch (e) {
                console.error('Failed to add test:', e);
            }
        },

        async updateIdeaTest(test) {
            if (!this.selectedIdea) return;
            const body = { name: test.name, test_type: test.test_type, description: test.description };
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests/${test.id}`, {
                    method: 'PUT',
                    body: JSON.stringify(body),
                });
                if (res.ok) await this.loadIdeaTests();
            } catch (e) {
                console.error('Failed to update test:', e);
            }
        },

        async setTestStatus(test, status) {
            if (!this.selectedIdea) return;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests/${test.id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ status }),
                });
                if (res.ok) await this.loadIdeaTests();
            } catch (e) {
                console.error('Failed to set test status:', e);
            }
        },

        async deleteIdeaTest(test) {
            if (!this.selectedIdea) return;
            if (!confirm('Delete this test?')) return;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/tests/${test.id}`, {
                    method: 'DELETE',
                });
                if (res.ok) await this.loadIdeaTests();
            } catch (e) {
                console.error('Failed to delete test:', e);
            }
        },

        filteredIdeaTests() {
            if (this.testStatusFilter === 'all') return this.ideaTests;
            return this.ideaTests.filter((t) => t.status === this.testStatusFilter);
        },

        flatComments() {
            const out = [];
            const walk = (nodes, depth) => {
                for (const c of nodes || []) {
                    out.push({ ...c, depth });
                    walk(c.replies, depth + 1);
                }
            };
            walk(this.selectedIdea?.comments, 0);
            return out;
        },

        commentCount() {
            const count = (nodes) => (nodes || []).reduce((n, c) => n + 1 + count(c.replies), 0);
            return count(this.selectedIdea?.comments);
        },

        canModerate(c) {
            if (c.is_deleted) return false;
            return this.isAdmin || (this.currentUserId && c.user_id === this.currentUserId);
        },

        startReply(id) {
            this.replyTo = id;
            this.editingCommentId = null;
        },

        startEdit(c) {
            this.editingCommentId = c.id;
            this.editDraft = c.body === '[deleted]' ? '' : c.body;
            this.replyTo = null;
        },

        async postComment() {
            const body = (this.commentDraft || '').trim();
            if (!body || !this.selectedIdea) return;
            this.commentPosting = true;
            const payload = { body };
            if (this.replyTo) payload.parent_id = this.replyTo;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/comments`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) throw new Error('Failed to post comment');
                this.commentDraft = '';
                this.replyTo = null;
                await this.loadComments(this.selectedIdea.id);
            } catch (e) {
                this.showAlertModal('Failed to post comment: ' + e.message);
            } finally {
                this.commentPosting = false;
            }
        },

        async saveEdit(id) {
            const body = (this.editDraft || '').trim();
            if (!body) return;
            try {
                const res = await authFetch(`/api/v1/comments/${id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ body }),
                });
                if (!res.ok) throw new Error('Failed to save edit');
                this.editingCommentId = null;
                await this.loadComments(this.selectedIdea.id);
            } catch (e) {
                this.showAlertModal('Failed to save edit: ' + e.message);
            }
        },

        startIdeaEdit() {
            if (!this.selectedIdea) return;
            this.editTitle = this.selectedIdea.prompt_title || '';
            // Structured mode when the idea has a field dict; otherwise raw.
            let sc = this.selectedIdea.structured_content;
            if (typeof sc === 'string') {
                try { sc = JSON.parse(sc); } catch (e) { sc = null; }
            }
            const known = ['elevator_pitch', 'target_audience', 'core_value_proposition', 'monetization_strategy'];
            if (sc && typeof sc === 'object' && known.some((k) => typeof sc[k] === 'string')) {
                this.editStructured = true;
                const fields = {};
                for (const k of known) fields[k] = typeof sc[k] === 'string' ? sc[k] : '';
                this.editFields = fields;
            } else {
                this.editStructured = false;
                this.editBody = this.selectedIdea.content || '';
            }
            this.editingIdea = true;
        },

        async saveIdeaEdit() {
            if (!this.selectedIdea) return;
            const title = (this.editTitle || '').trim();
            if (!title) {
                await this.showAlertModal('Title must not be empty.');
                return;
            }
            const payload = { prompt_title: title };
            if (this.editStructured) {
                const sc = {};
                for (const f of this.editFieldDefs) {
                    const val = (this.editFields[f.key] || '').trim();
                    if (!val) {
                        await this.showAlertModal(f.label + ' must not be empty.');
                        return;
                    }
                    if (val.length > f.max) {
                        await this.showAlertModal(f.label + ` must be ${f.max} characters or fewer.`);
                        return;
                    }
                    sc[f.key] = val;
                }
                payload.structured_content = sc;
            } else {
                const body = (this.editBody || '').trim();
                if (!body) {
                    await this.showAlertModal('Body must not be empty.');
                    return;
                }
                payload.raw_content = body;
            }
            this.editSaving = true;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || 'Failed to save');
                }
                this.editingIdea = false;
                await this.loadIdeaDetail(this.selectedIdea.id);
                await this.loadIdeas();
            } catch (e) {
                this.showAlertModal('Failed to save edit: ' + e.message);
            } finally {
                this.editSaving = false;
            }
        },

        async deleteComment(id) {
            if (!(await this.showConfirmModal('Delete this comment? Replies will be kept.', '', 'Delete'))) return;
            try {
                const res = await authFetch(`/api/v1/comments/${id}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Failed to delete comment');
                await this.loadComments(this.selectedIdea.id);
            } catch (e) {
                this.showAlertModal('Failed to delete comment: ' + e.message);
            }
        },

        // Scale-phase collaboration: child ideas + releases + moderation.
        // Plain words throughout: users never see "child_kind" or "bulk".
        async toggleIgnore(c) {
            const next = !c.is_ignored;
            try {
                const res = await authFetch(`/api/v1/comments/${c.id}/flag`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_ignored: next }),
                });
                if (!res.ok) throw new Error('Failed to update comment');
                await this.loadComments(this.selectedIdea.id);
            } catch (e) {
                this.showAlertModal('Failed to update comment: ' + e.message);
            }
        },

        async loadScaleFamily() {
            this.scaleParent = null;
            this.scaleChildren = [];
            this.scaleReleases = [];
            const idea = this.selectedIdea;
            if (!idea) return;
            try {
                if (idea.parent_id) {
                    const res = await authFetch(`/api/v1/ideas/${idea.id}`);
                    const data = await res.json();
                    const payload = data.data || data;
                    this.scaleParent = payload.parent || null;
                    this.selectedIdea.child_kind = payload.idea?.child_kind || this.selectedIdea.child_kind;
                } else if (idea.status === 'SCALE') {
                    this.relAiDraft = {};
                    this.relAiCustom = {};
                    this.relAiOpen = {};
                    const [ch, rel] = await Promise.all([
                        authFetch(`/api/v1/ideas/${idea.id}/children?limit=100`),
                        authFetch(`/api/v1/ideas/${idea.id}/releases`),
                    ]);
                    if (ch.ok) {
                        const d = await ch.json();
                        this.scaleChildren = ((d.data || d).ideas || []);
                    }
                    if (rel.ok) {
                        const d = await rel.json();
                        this.scaleReleases = ((d.data || d).releases || []);
                        // Seed the AI-settings draft from each release's saved
                        // config (blank fields = "stage default"). The pseudo
                        // "No release yet" entry has no id — seed it too so the
                        // hidden editor's x-model bindings resolve.
                        for (const r of this.scaleReleases) {
                            const ai = (r.id && r.ai_config) || {};
                            this.relAiDraft[r.id] = {
                                provider: ai.provider || '',
                                model_name: ai.model_name || '',
                                temperature: ai.temperature ?? '',
                                top_p: ai.top_p ?? '',
                                num_predict: ai.num_predict ?? '',
                                // Arrays end to end: the multiselect control
                                // edits them directly, no comma round-trip.
                                skills: Array.isArray(ai.skills) ? [...ai.skills] : [],
                                guidelines: Array.isArray(ai.guidelines) ? [...ai.guidelines] : [],
                            };
                            this.relAiCustom[r.id] = false;
                        }
                        // Skills/guidelines options and the provider's model
                        // catalogue must exist before the panels open. The
                        // panels are admin-only, so members skip the calls.
                        if (this.isAdmin) {
                            await Promise.all([
                                this.loadDiscovery(),
                                this.loadReleaseAiModels(),
                            ]);
                        }
                    }
                    await this.refreshBuildStatus();
                }
            } catch (e) {
                console.error('Failed to load scale family:', e);
            }
        },

        // Poll build states while anything is queued/running; the tab then
        // stops by itself when every build settles.
        async refreshBuildStatus() {
            const idea = this.selectedIdea;
            if (!idea || !this.showScaleTab()) return;
            try {
                const res = await authFetch(`/api/v1/ideas/${idea.id}/scale-status`);
                if (!res.ok) return;
                const d = await res.json();
                this.buildStatus = (d.data || d).builds || {};
                const busy = Object.values(this.buildStatus).some((b) =>
                    b && (b.status === 'PENDING' || b.status === 'RUNNING'));
                if (busy && !this.buildPollTimer) {
                    this.buildPollTimer = setInterval(() => {
                        if (this.detailModalOpen && this.showScaleTab() && this.activeTab === 'scale') {
                            this.refreshBuildStatus();
                        } else {
                            this.stopBuildPolling();
                        }
                    }, 4000);
                } else if (!busy) {
                    this.stopBuildPolling();
                }
            } catch (e) {
                // Transient: next load retries.
            }
        },

        stopBuildPolling() {
            if (this.buildPollTimer) {
                clearInterval(this.buildPollTimer);
                this.buildPollTimer = null;
            }
        },

        buildPillText(k) {
            const b = this.buildStatus && this.buildStatus[k.id];
            if (!b) return 'No build';
            if (b.status === 'PENDING') return 'Queued';
            if (b.status === 'RUNNING') return 'Building…';
            if (b.status === 'SUCCESS') return '✓ Written';
            if (b.status === 'FAILED') return '✗ Failed';
            return b.status;
        },

        buildPillClass(k) {
            const b = this.buildStatus && this.buildStatus[k.id];
            if (!b) return 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500';
            if (b.status === 'SUCCESS') return 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800';
            if (b.status === 'FAILED') return 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800';
            return 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 animate-pulse';
        },

        buildPillTitle(k) {
            const b = this.buildStatus && this.buildStatus[k.id];
            if (!b) return 'No build started for this idea yet';
            if (b.status === 'FAILED') return (b.error || 'Build failed') + ' — open the idea for details';
            if (b.status === 'SUCCESS') return 'Files written to the app repo — restart the app (Build tab: Stop, then Start) to see them';
            return 'Building — this updates by itself';
        },

        scaleKids(releaseId) {
            return (this.scaleChildren || []).filter((k) =>
                releaseId ? String(k.release_id) === String(releaseId) : !k.release_id);
        },

        // The releases API appends a pseudo "No release yet" entry (id
        // null) for the unassigned bucket. The tab renders that bucket in
        // its own block, so release cards and movers must skip the pseudo
        // entry or every unassigned child appears twice.
        realReleases() {
            return (this.scaleReleases || []).filter((r) => r && r.id);
        },

        // ---- Per-release AI settings -------------------------------------
        // The catalogue is cached per provider and shared by every release
        // card; the shared controls in ai_controls.js decide what a saved
        // model looks like when it is (or is not) in that catalogue.
        async loadAiModels(provider) {
            if (!provider || this.relAiModels[provider]) return;
            const { models } = await AIControls.fetchModels(provider);
            this.relAiModels[provider] = models;
        },

        async loadReleaseAiModels() {
            const providers = new Set(
                (this.scaleReleases || [])
                    .map((r) => (this.relAiDraft[r.id] || {}).provider)
                    .filter(Boolean));
            await Promise.all([...providers].map((p) => this.loadAiModels(p)));
            // A saved model outside the catalogue stays visible through the
            // Custom model… input rather than silently reading as "default".
            for (const r of this.scaleReleases || []) {
                const draft = this.relAiDraft[r.id];
                if (!draft) continue;
                this.relAiCustom[r.id] = AIControls.isCustom(
                    draft.model_name, this.relAiModels[draft.provider] || []);
            }
        },

        onRelAiProvider(relId) {
            const draft = this.relAiDraft[relId];
            if (!draft) return;
            // Model ids differ per provider: drop the old one and load the
            // new catalogue (same rule as Admin → AI Settings).
            draft.model_name = '';
            this.relAiCustom[relId] = false;
            this.loadAiModels(draft.provider);
        },

        onRelAiModelPick(relId, value) {
            const draft = this.relAiDraft[relId];
            if (!draft) return;
            if (value === AIControls.CUSTOM) {
                this.relAiCustom[relId] = true;
                return;
            }
            this.relAiCustom[relId] = false;
            draft.model_name = value;
        },

        openChildModal(kind) {
            this.childKind = kind;
            this.childTitle = '';
            this.childBody = '';
            this.childError = '';
            this.childModalOpen = true;
        },

        async createChild() {
            this.childError = '';
            const title = (this.childTitle || '').trim();
            const body = (this.childBody || '').trim();
            if (!title) { this.childError = 'Give it a short title.'; return; }
            if (!body) { this.childError = 'Describe what should change.'; return; }
            this.childLoading = true;
            try {
                const res = await authFetch('/api/v1/ideas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt_title: title,
                        raw_content: body,
                        parent_id: this.selectedIdea.id,
                        child_kind: this.childKind,
                    }),
                });
                const data = await res.json();
                if (!res.ok) {
                    this.childError = data.message || data.error || 'Could not save. Please try again.';
                    return;
                }
                this.childModalOpen = false;
                await this.loadScaleFamily();
                if (data.data?.id) this.openIdeaById(data.data.id);
            } catch (e) {
                this.childError = 'Could not save. Please try again.';
            } finally {
                this.childLoading = false;
            }
        },

        async createRelease() {
            if (!this.selectedIdea) {
                this.showAlertModal('No idea selected — open an idea first.');
                return;
            }
            const name = await this.showPromptModal('Release name', 'for example: Release 1.1');
            if (!name || !name.trim()) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/releases`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim() }),
                });
                if (!res.ok) throw new Error('Failed to create release');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to create release: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async moveChildToRelease(childId, releaseId) {
            this.releaseBusy = true;
            try {
                const url = releaseId
                    ? `/api/v1/releases/${releaseId}/assign`
                    : null;
                if (!url) return;
                const res = await authFetch(url, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_ids: [childId] }),
                });
                if (!res.ok) throw new Error('Failed to move');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to move: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async removeChildFromRelease(child) {
            if (!child.release_id) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${child.release_id}/unassign`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_ids: [child.id] }),
                });
                if (!res.ok) throw new Error('Failed to move');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to move: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async completeRelease(releaseId) {
            const target = (await this.showConfirmModal('Mark every item in this release as shipped? OK = shipped, Cancel = stop here.', '', 'Ship all')) ? 'SHIP' : null;
            if (!target) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/complete`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: target }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to finish release');
                const d = data.data || data;
                if (!d.total) {
                    await this.showAlertModal('Nothing in this release yet — move ideas into it first.');
                } else if (!d.updated_count && !d.skipped_illegal) {
                    const done = d.status === 'DROP' ? 'dropped' : 'shipped';
                    await this.showAlertModal(`Everything in this release is already ${done}.`);
                } else {
                    await this.showAlertModal(`Finished: ${d.updated_count} shipped${d.skipped_illegal ? `, ${d.skipped_illegal} not ready yet` : ''}.`);
                }
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to finish release: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async deleteRelease(releaseId) {
            if (!(await this.showConfirmModal('Delete this release? Items move back to “No release yet”.', '', 'Delete release'))) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}`, { method: 'DELETE' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to delete');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to delete: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async pushRelease(releaseId) {
            if (!(await this.showConfirmModal('Push this release to GitHub? It can only be pushed once — further updates need a new release.', '', 'Push to GitHub'))) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/github-push`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to start push');
                await this.showAlertModal('Push started — this card shows the commit when it lands. Reload the Scale tab in a minute to check.');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Push failed to start: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Start a secondary action for one release child (dropdown).
        async openChildDoc(k, actionType) {
            if (!actionType) return;
            // Use the repo picked on the Build tab, else this idea's last
            // build repo. Never hard-block: the worker falls back to the
            // instance's only repo and names the options when ambiguous.
            const targetId = this.buildTargetChoice || this.buildTargetId() || null;
            this.actionLoading = actionType;
            try {
                const extra = {};
                if (targetId) extra.target_id = targetId;
                const res = await authFetch(`/api/v1/ideas/${k.id}/actions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action_type: actionType, extra }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error((data && data.message) || 'Failed to start');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to start: ' + e.message);
            } finally {
                this.actionLoading = null;
            }
        },

        releaseKidIds(releaseId) {
            return this.scaleKids(releaseId).map((k) => k.id);
        },

        // "16-Oct-26" — completion date when the release has one, else the
        // planned target, else when it was created.
        releaseDate(rel) {
            const d = rel && (rel.completed_at || rel.target_date || rel.created_at);
            if (!d) return '';
            const dt = new Date(d);
            if (isNaN(dt.getTime())) return '';
            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            const dd = String(dt.getDate()).padStart(2, '0');
            return dd + '-' + months[dt.getMonth()] + '-' + String(dt.getFullYear()).slice(-2);
        },

        // Move every idea in a release to one stage together (related
        // work travels together). Uses the normal bulk-status rules, so
        // illegal jumps are skipped and counted, never forced.
        async moveReleaseAll(releaseId) {
            const status = this.releaseMove[releaseId];
            const ids = this.releaseKidIds(releaseId);
            if (!status || !ids.length) return;
            if (!(await this.showConfirmModal(`Move ${ids.length} idea(s) to ${status}? Skipped ones stay where they are.`, '', 'Move all'))) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch('/api/v1/ideas/bulk-status', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_ids: ids, status }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to move');
                const d = data.data || data;
                await this.showAlertModal(`Moved: ${d.updated_count} of ${ids.length}${d.skipped_illegal ? `, ${d.skipped_illegal} not ready for ${status}` : ''}.`);
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to move: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Start one document/build step for every idea in a release.
        // Same rules as running it per idea; skips explain themselves.
        async bulkReleaseAction(releaseId, actionType, confirmBuild) {
            const ids = this.releaseKidIds(releaseId);
            if (!ids.length) return;
            const what = actionType === 'BUILD_CODE' ? (confirmBuild ? 'write all previews into the app repo' : 'preview builds for all') : `start ${actionType} for all`;
            if (!(await this.showConfirmModal(`This will ${what} (${ids.length} idea(s)). Continue?`, '', 'Continue'))) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/run-action`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action_type: actionType,
                        confirm_build: !!confirmBuild,
                        target_id: this.buildTargetChoice || null,
                    }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || data.error || 'Failed to start');
                const d = data.data || data;
                let msg = d.summary || 'Done.';
                for (const s of (d.skipped || []).slice(0, 5)) msg += `\n• ${s.reference_code}: ${s.reason}`;
                if ((d.skipped || []).length > 5) msg += `\n… and ${(d.skipped || []).length - 5} more.`;
                await this.showAlertModal(msg);
                await this.loadScaleFamily();
                // Builds settle async: watch until every started one finishes.
                if (d.started && d.started.length) await this.refreshBuildStatus();
            } catch (e) {
                this.showAlertModal('Failed to start: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Create a new release and move all unassigned children into it.
        async assignToNewRelease() {
            const ids = this.releaseKidIds(null);
            if (!ids.length) return;
            const name = await this.showPromptModal('New release name', 'for example: Release 1.1');
            if (!name || !name.trim()) return;
            if (!this.selectedIdea) {
                this.showAlertModal('No idea selected — open an idea first.');
                return;
            }
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/ideas/${this.selectedIdea.id}/releases`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim() }),
                });
                if (!res.ok) throw new Error('Failed to create release');
                const d = await res.json();
                const releaseId = ((d.data || d).release || {}).id;
                if (!releaseId) throw new Error('No release id returned');
                const assignRes = await authFetch(`/api/v1/releases/${releaseId}/assign`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_ids: ids }),
                });
                if (!assignRes.ok) throw new Error('Failed to assign ideas to release');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to create release: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Move every unassigned child idea to one stage together.
        async moveUnassignedAll() {
            const status = this.unassignedMove;
            const ids = this.releaseKidIds(null);
            if (!status || !ids.length) return;
            if (!(await this.showConfirmModal(`Move ${ids.length} unassigned idea(s) to ${status}? Skipped ones stay where they are.`, '', 'Move all'))) return;
            this.releaseBusy = true;
            try {
                const res = await authFetch('/api/v1/ideas/bulk-status', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_ids: ids, status }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to move');
                const d = data.data || data;
                await this.showAlertModal(`Moved: ${d.updated_count} of ${ids.length}${d.skipped_illegal ? `, ${d.skipped_illegal} not ready for ${status}` : ''}.`);
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to move: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Start one document/build step for every unassigned child idea.
        async bulkUnassignedAction(actionType, confirmBuild) {
            const ids = this.releaseKidIds(null);
            if (!ids.length) return;
            const what = actionType === 'BUILD_CODE' ? (confirmBuild ? 'write all previews into the app repo' : 'preview builds for all') : `start ${actionType} for all`;
            if (!(await this.showConfirmModal(`This will ${what} (${ids.length} idea(s)). Continue?`, '', 'Continue'))) return;
            this.releaseBusy = true;
            try {
                let started = 0;
                const skipped = [];
                for (const id of ids) {
                    const res = await authFetch(`/api/v1/ideas/${id}/actions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action_type: actionType }),
                    });
                    if (res.ok) started++;
                    else {
                        const d = await res.json().catch(() => ({}));
                        skipped.push({ reference_code: id, reason: d.message || d.error || 'failed' });
                    }
                }
                let msg = `Started ${started} of ${ids.length}.`;
                for (const s of skipped.slice(0, 5)) msg += `\n• ${s.reference_code}: ${s.reason}`;
                if (skipped.length > 5) msg += `\n… and ${skipped.length - 5} more.`;
                await this.showAlertModal(msg);
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to start: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        // Start a PRD/Design/Build for one release child (row "+ Doc").
        // The child isn't in the ideas list, so hand the dialog its ref and
        // instance; the server enforces the same gates as anywhere else.
        openChildDoc(k, actionType) {
            if (!actionType) return;
            this.openRunDialog(k.id, actionType, k.reference_code, k.instance_id);
        },

        async regenReleaseNotes(releaseId) {
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/notes`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to rebuild notes');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to rebuild notes: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async saveReleaseAi(releaseId) {
            const draft = this.relAiDraft[releaseId];
            if (!draft) return;
            const payload = {
                provider: draft.provider || null,
                model_name: draft.model_name || null,
                temperature: draft.temperature === '' ? null : Number(draft.temperature),
                top_p: draft.top_p === '' ? null : Number(draft.top_p),
                num_predict: draft.num_predict === '' ? null : Number(draft.num_predict),
                skills: Array.isArray(draft.skills) ? [...draft.skills] : [],
                guidelines: Array.isArray(draft.guidelines) ? [...draft.guidelines] : [],
            };
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/ai-config`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to save');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to save AI settings: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        async clearReleaseAi(releaseId) {
            this.releaseBusy = true;
            try {
                const res = await authFetch(`/api/v1/releases/${releaseId}/ai-config`, { method: 'DELETE' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Failed to clear');
                await this.loadScaleFamily();
            } catch (e) {
                this.showAlertModal('Failed to clear AI settings: ' + e.message);
            } finally {
                this.releaseBusy = false;
            }
        },

        downloadReleaseNotes(rel) {
            if (!rel || !rel.notes) return;
            const blob = new Blob([rel.notes], { type: 'text/markdown' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = (rel.notes_file || 'release-notes') + '.md';
            a.click();
            URL.revokeObjectURL(a.href);
        },
        
        async vote(ideaId, direction) {
            this.voteLoading = ideaId;
            try {
                const response = await authFetch(`/api/v1/ideas/${ideaId}/vote`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ direction })
                });
                if (!response.ok) throw new Error('Failed to vote');
                const data = await response.json();
                const payload = data.data || data;
                const idea = this.ideas.find(i => i.id === ideaId);
                if (idea) {
                    idea.net_votes = payload.net_votes;
                    idea.user_vote = payload.current_user_vote;
                    if (payload.upvotes_count !== undefined) idea.upvotes_count = payload.upvotes_count;
                    if (payload.downvotes_count !== undefined) idea.downvotes_count = payload.downvotes_count;
                }
                if (this.selectedIdea?.id === ideaId) {
                    this.selectedIdea.net_votes = payload.net_votes;
                    this.selectedIdea.user_vote = payload.current_user_vote;
                    if (payload.upvotes_count !== undefined) this.selectedIdea.upvotes_count = payload.upvotes_count;
                    if (payload.downvotes_count !== undefined) this.selectedIdea.downvotes_count = payload.downvotes_count;
                }
            } catch (error) {
                this.showAlertModal('Failed to vote: ' + error.message);
            } finally {
                this.voteLoading = null;
            }
        },
        
        getVoteClass(idea, direction) {
            const voted = idea?.user_vote === direction;
            return `p-1.5 rounded-lg transition-colors ${voted ? 'bg-primary-100 text-primary-600 dark:bg-primary-900 dark:text-primary-400' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700'}`;
        },
        
        get refinedActions() {
            // 3-dot menu: all available actions from the registry
            return this.availableActions || [];
        },

        docActionVisible(actionKey) {
            // V2 stage gates: PRD unlocks at Scope, Design docs at Map,
            // code builds at Ship. Dropped/archived ideas are read-only.
            // Secondary actions (REFINE, COMPETITORS, FIVE_FORCES, PESTEL,
            // etc.) are always available; only PRD_DOC, DESIGN_DOC,
            // BUILD_CODE are stage-restricted.
            const st = this.selectedIdea?.status;
            if (actionKey === 'PRD_DOC') {
                return st && st !== 'SPARK' && st !== 'DROP' && st !== 'ARCHIVE';
            }
            if (actionKey === 'DESIGN_DOC') {
                return ['MAP', 'SHIP', 'SCALE', 'FREEZE'].includes(st);
            }
            if (actionKey === 'BUILD_CODE') {
                return ['SHIP', 'SCALE'].includes(st);
            }
            return true;
        },

        async confirmDiscard(idea, close) {
            if (!(await this.showConfirmModal('Drop this idea? It will be hidden by the default filter.', '', 'Drop idea'))) return;
            await this.changeStatus('DROP', idea.id, true);
            if (close) close();
        },

        // Mirrors ALLOWED_TRANSITIONS in app/models/lifecycle.py.
        canArchive(idea) {
            return !!idea && ['SPARK', 'SCOPE', 'MAP', 'SHIP', 'SCALE', 'DROP', 'FREEZE'].includes(idea.status);
        },

        canRestore(idea) {
            return !!idea && idea.status === 'ARCHIVE';
        },

        // Restore returns the idea to the stage it left (server-side history).
        restoreTarget(idea) {
            return (idea && idea.archived_from) || 'SPARK';
        },

        async confirmArchive(idea, close) {
            if (!idea || !this.canArchive(idea)) {
                if (close) close();
                return;
            }
            const message = 'Archive this idea? It is stored away and hidden from the default list. You can restore it later.';
            if (!(await this.showConfirmModal(message, '', 'Archive idea'))) {
                if (close) close();
                return;
            }
            await this.changeStatus('ARCHIVE', idea.id, true);
            if (close) close();
        },

        async confirmRestore(idea, close) {
            if (!idea || !this.canRestore(idea)) {
                if (close) close();
                return;
            }
            const target = this.restoreTarget(idea);
            const message = 'Restore this idea to ' + this.stageLabel(target) + '?';
            if (!(await this.showConfirmModal(message, '', 'Restore idea'))) {
                if (close) close();
                return;
            }
            await this.changeStatus(target, idea.id, true);
            if (close) close();
        },

        async changeStatus(status, ideaId, confirmed) {
            if (!status) return;
            // Contract: the UI always prompts the admin on a status change.
            if (!confirmed && !(await this.showConfirmModal(`Change status to ${status}?`, '', 'Change status'))) {
                await this.loadIdeas();
                return;
            }
            try {
                const response = await authFetch(`/api/v1/ideas/${ideaId}/status`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error((payload && payload.message) || 'Failed to update status');
                await this.loadIdeas();
                await this.loadTotalIdeas();
                if (this.selectedIdea?.id === ideaId) {
                    this.selectedIdea.status = status;
                    if (!this.showScaleTab() && this.activeTab === 'scale') this.activeTab = 'overview';
                }
            } catch (error) {
                this.showAlertModal('Failed to update status: ' + error.message);
                await this.loadIdeas();
            }
        },
        
        async runAction(ideaId, actionType, extra) {
            // V2 stage gates mirror the server (admin enforced server-side too).
            const target = (this.selectedIdea?.id === ideaId)
                ? this.selectedIdea
                : (this.ideas || []).find(i => i.id === ideaId);
            const st = target ? target.status : null;
            if (st === 'DROP' || st === 'ARCHIVE') {
                await this.showAlertModal('No actions can run on dropped or archived ideas.');
                return false;
            }
            if (actionType === 'PRD_DOC' && (!st || st === 'SPARK')) {
                await this.showAlertModal('PRD creation requires the idea to reach Scope stage.');
                return false;
            }
            if (actionType === 'DESIGN_DOC' && !['MAP', 'SHIP', 'SCALE', 'FREEZE'].includes(st)) {
                await this.showAlertModal('Design documents require the idea to reach Map stage.');
                return false;
            }
            if (actionType === 'BUILD_CODE' && !['SHIP', 'SCALE'].includes(st)) {
                await this.showAlertModal('Building code requires the idea to reach Ship stage.');
                return false;
            }
            // Check if this action requires confirmation (Refine or PRD)
            if ((actionType === 'REFINE' || actionType === 'PRD_DOC') && this.selectedIdea) {
                const idea = this.selectedIdea;
                const commentCount = idea.comments ? idea.comments.length : 0;
                const actionsDone = idea.actions_run || [];
                if (commentCount === 0 && actionsDone.length < 3) {
                    await this.requestConfirmation(ideaId, actionType, extra);
                    return true;
                }
            }
            return await this.executeAction(ideaId, actionType, extra);
        },

        async requestConfirmation(ideaId, actionType, extra) {
            const action = (this.availableActions || []).find(a => a.key === actionType);
            const label = action ? action.label : actionType;
            this.confirmModalMessage = 'Are you sure you want to continue? This idea doesn\'t have much more additional information yet.';
            this.confirmModalDetail = `Running ${label} on an idea with no comments and fewer than 3 secondary actions may produce less useful results.`;
            this.confirmModalActionLabel = `Run ${label}`;
            this.confirmModalActionType = actionType;
            this.confirmModalIdeaId = ideaId;
            this.confirmModalAnswers = extra?.answers || [];
            this.pendingRunExtra = {
                ...(extra?.model_override ? { model_override: extra.model_override } : {}),
                ...(extra?.provider_override ? { provider_override: extra.provider_override } : {}),
                ...(extra?.skills?.length ? { skills: extra.skills } : {}),
                ...(extra?.guidelines?.length ? { guidelines: extra.guidelines } : {}),
            };
            this.confirmModalOpen = true;
        },

        closeConfirmModal() {
            this.confirmModalOpen = false;
            this.confirmModalMessage = '';
            this.confirmModalDetail = '';
            this.confirmModalActionLabel = '';
            this.confirmModalActionType = '';
            this.confirmModalIdeaId = null;
            this.confirmModalAnswers = [];
            this.pendingRunExtra = null;
        },

        // Alert modal (replaces alert())
        async showAlertModal(message) {
            this.alertModalMessage = message;
            this.alertModalOpen = true;
            return new Promise(resolve => {
                this.alertModalResolve = resolve;
            });
        },
        closeAlertModal() {
            this.alertModalOpen = false;
            this.alertModalMessage = '';
            if (this.alertModalResolve) {
                this.alertModalResolve();
                this.alertModalResolve = null;
            }
        },

        // Confirm modal with promise (replaces confirm())
        async showConfirmModal(message, detail, actionLabel) {
            this.confirmModalMessage = message;
            this.confirmModalDetail = detail || '';
            this.confirmModalActionLabel = actionLabel || 'OK';
            this.confirmModalOpen = true;
            return new Promise((resolve, reject) => {
                this.confirmModalResolve = resolve;
                this.confirmModalReject = reject;
            });
        },
        resolveConfirmModal() {
            if (this.confirmModalResolve) {
                this.confirmModalResolve(true);
                this.confirmModalResolve = null;
            }
            this.closeConfirmModal();
        },
        rejectConfirmModal() {
            if (this.confirmModalReject) {
                this.confirmModalReject(false);
                this.confirmModalReject = null;
            }
            this.closeConfirmModal();
        },

        // Prompt modal (replaces prompt())
        async showPromptModal(message, placeholder) {
            this.promptModalMessage = message;
            this.promptModalPlaceholder = placeholder || '';
            this.promptModalValue = '';
            this.promptModalOpen = true;
            return new Promise((resolve, reject) => {
                this.promptModalResolve = resolve;
                this.promptModalReject = reject;
            });
        },
        submitPromptModal() {
            if (!this.promptModalValue.trim()) return;
            if (this.promptModalResolve) {
                this.promptModalResolve(this.promptModalValue.trim());
                this.promptModalResolve = null;
            }
            this.closePromptModal();
        },
        closePromptModal() {
            this.promptModalOpen = false;
            this.promptModalMessage = '';
            this.promptModalPlaceholder = '';
            this.promptModalValue = '';
            if (this.promptModalReject) {
                this.promptModalReject(null);
                this.promptModalReject = null;
            }
        },

        async openRunDialog(ideaId, actionType, ref, instanceId) {
            const action = (this.availableActions || []).find(a => a.key === actionType);
            this.runDialogIdeaId = ideaId;
            this.runDialogActionType = actionType;
            this.runDialogActionLabel = action ? action.label : actionType;
            // For ideas outside the list (release children), the caller passes
            // the ref + instance so the dialog can label itself and create
            // build repos; otherwise fall back to the known idea.
            const knownIdea = (this.selectedIdea && this.selectedIdea.id === ideaId)
                ? this.selectedIdea
                : (this.ideas || []).find((i) => i.id === ideaId);
            this.runDialogIdeaRef = ref || (knownIdea && knownIdea.reference_code) || '';
            this.runDialogInstanceId = instanceId || (knownIdea && knownIdea.instance_id) || null;
            // Recreate defaults: pre-fill from the latest run of this action
            // (provider, model, skills, guidelines actually used), falling
            // back to the idea's prompt engine and blanks.
            const idea = (this.selectedIdea && this.selectedIdea.id === ideaId)
                ? this.selectedIdea
                : (this.ideas || []).find((i) => i.id === ideaId);
            const rows = ((idea && idea.actions) || []).filter((a) => a.action_type === actionType);
            const last = rows.find((a) => a.is_current) || rows[rows.length - 1] || null;
            let ideaProvider = 'ollama';
            if (idea && idea.prompt_config_id) {
                try {
                    const pr = await authFetch(`/api/v1/prompts/${idea.prompt_config_id}`);
                    const pdata = await pr.json();
                    const prompt = (pdata.data || pdata).prompt || pdata.data || pdata;
                    if (prompt && prompt.provider) ideaProvider = prompt.provider;
                } catch (e) { /* keep ollama default */ }
            }
            this.runDialogBaseProvider = (last && last.provider_used) || ideaProvider;
            this.runDialogProvider = this.runDialogBaseProvider;
            this.runDialogModel = '';
            this.runDialogCustom = false;
            this.runAiOpen = {};
            this.runDialogSkills = [];
            this.runDialogGuidelines = [];
            this.runDialogTarget = '';
            this.runDialogTargets = [];
            this.runDialogTargetDefaults = {};
            this.runDialogIdeaRef = (idea && idea.reference_code) || '';
            this.runDialogNewRepo = false;
            this.runDialogNewRepoName = '';
            this.runDialogNewRepoPath = '';
            this.creatingRepo = false;
            this.runDialogAdvanced = false;
            this.runDialogOpen = true;
            const dialogLoads = [this.loadRunDialogModels(false), this.loadDiscovery()];
            if (actionType === 'BUILD_CODE' && idea && idea.instance_id) {
                dialogLoads.push(this.loadBuildTargets(idea.instance_id));
            }
            await Promise.all(dialogLoads);
            // Prefill a new repo from the idea + defaults (editable; blanks
            // stay rejected server-side).
            if (actionType === 'BUILD_CODE' && idea) {
                const root = this.runDialogTargetDefaults.configured_root
                    || this.runDialogTargetDefaults.projects_root || '';
                if (idea.reference_code) {
                    this.runDialogNewRepoName = idea.reference_code;
                    if (root) this.runDialogNewRepoPath = root.replace(/\/+$/, '') + '/' + idea.reference_code;
                }
            }
            // Preselect the repo: the one this idea last built into, else the
            // Build tab's choice, else the first registered. A blank select
            // silently failed the run with "Unknown build target".
            if (actionType === 'BUILD_CODE') {
                const ref = (this.runDialogIdeaRef || '').trim().toLowerCase();
                // A repo named after this idea wins: reusing the instance's
                // only repo (often another idea's folder) mixed files.
                const byRef = ref
                    ? this.runDialogTargets.find((t) => String(t.name || '').trim().toLowerCase() === ref)
                    : null;
                const prior = (last && last.target_id) || this.buildTargetChoice;
                const match = this.runDialogTargets.find((t) => String(t.id) === String(prior));
                this.runDialogTarget = byRef
                    ? byRef.id
                    : (match ? match.id : ((this.runDialogTargets[0] || {}).id || ''));
                // No repo for this idea yet: open the (prefilled) new-repo
                // form instead of silently building into someone else's.
                if (!byRef && this.runDialogTargets.length) this.runDialogNewRepo = true;
            }
            // Assign Recreate defaults AFTER the option lists render: an
            // x-model value set before its <option>s exist stays blank.
            this.runDialogModel = (last && last.model_used) || '';
            this.runDialogSkills = last && last.skills_used ? [...last.skills_used] : [];
            this.runDialogGuidelines = last && last.guidelines_used ? [...last.guidelines_used] : [];
            const skillNames = this.discoverySkills.map((s) => s.name);
            const guideNames = this.discoveryGuidelines.map((g) => g.name);
            this.runDialogSkills = this.runDialogSkills.filter((n) => skillNames.includes(n));
            this.runDialogGuidelines = this.runDialogGuidelines.filter((n) => guideNames.includes(n));
        },

        closeRunDialog() {
            this.runDialogOpen = false;
            this.runDialogIdeaId = null;
            this.runDialogActionType = '';
            this.runDialogActionLabel = '';
            this.runDialogProvider = 'ollama';
            this.runDialogBaseProvider = 'ollama';
            this.runDialogModel = '';
            this.runDialogCustom = false;
            this.runAiOpen = {};
            this.runDialogTarget = '';
            this.runDialogTargets = [];
            this.runDialogTargetDefaults = {};
            this.runDialogIdeaRef = '';
            this.runDialogNewRepo = false;
            this.runDialogNewRepoName = '';
            this.runDialogNewRepoPath = '';
            this.creatingRepo = false;
            this.runDialogSkills = [];
            this.runDialogGuidelines = [];
            this.runDialogAdvanced = false;
        },

        // Same catalogue + normaliser as every other AI settings surface
        // (static/js/ai_controls.js); the template renders the shared
        // model field, including the Custom model... escape hatch.
        async loadRunDialogModels(resetModel) {
            const provider = this.runDialogProvider || 'ollama';
            const { models } = await AIControls.fetchModels(provider);
            this.ollamaModels = models;
            if (resetModel) this.runDialogModel = '';
            // No catalogue for this engine (no allowlist, server unreachable)
            // must still be usable: open the custom id input.
            if (!models.length && provider !== 'ollama' && !this.runDialogModel) {
                this.runDialogCustom = true;
            }
            if (this.runDialogModel) {
                this.runDialogCustom = AIControls.isCustom(this.runDialogModel, models);
            }
            // Never clear on initial load: a pre-filled Recreate default
            // survives even if the model list fails to load or changed.
        },

        onRunDialogModelPick(value) {
            if (value === AIControls.CUSTOM) {
                this.runDialogCustom = true;
                return;
            }
            this.runDialogCustom = false;
            this.runDialogModel = value;
        },

        runDialogSelectedTarget() {
            return (this.runDialogTargets || []).find(
                (t) => String(t.id) === String(this.runDialogTarget)
            ) || null;
        },

        // Name of the selected repo when it is not this idea's own repo
        // (empty string when it matches or nothing is selected).
        runDialogTargetMismatch() {
            const target = this.runDialogSelectedTarget();
            const ref = (this.runDialogIdeaRef || '').trim();
            if (!target || !ref) return '';
            const name = String(target.name || '').trim();
            return name.toLowerCase() === ref.toLowerCase() ? '' : name;
        },

        async loadBuildTargets(instanceId) {
            this.runDialogTargets = [];
            try {
                const res = await authFetch(`/api/v1/instances/${instanceId}/build-targets`);
                const data = await res.json();
                if (!res.ok) return;
                this.runDialogTargets = ((data.data || data).targets) || [];
                this.runDialogTargetDefaults = ((data.data || data).defaults) || {};
            } catch (e) {
                console.error('Failed to load build targets:', e);
            }
        },

        async loadBuildTargetChoices(instanceId) {
            this.buildTargetChoices = [];
            if (!instanceId) return;
            try {
                const res = await authFetch(`/api/v1/instances/${instanceId}/build-targets`);
                if (!res.ok) return;
                const data = await res.json();
                this.buildTargetChoices = ((data.data || data).targets) || [];
            } catch (e) {
                console.error('Failed to load build repos:', e);
                return;
            }
            // Keep a valid selection: previous build's repo, else the first.
            const known = this.buildTargetChoices.some(
                (t) => String(t.id) === String(this.buildTargetChoice)
            );
            if (!known) {
                const prior = this.buildTargetId();
                const match = this.buildTargetChoices.find(
                    (t) => String(t.id) === String(prior)
                );
                this.buildTargetChoice = match
                    ? match.id
                    : ((this.buildTargetChoices[0] || {}).id || '');
            }
        },

        async createBuildRepo() {
            const idea = (this.selectedIdea && this.selectedIdea.id === this.runDialogIdeaId)
                ? this.selectedIdea
                : (this.ideas || []).find((i) => i.id === this.runDialogIdeaId);
            const instanceId = (idea && idea.instance_id) || this.runDialogInstanceId;
            const name = (this.runDialogNewRepoName || '').trim();
            const path = (this.runDialogNewRepoPath || '').trim();
            if (!instanceId) { await this.showAlertModal('Cannot determine the idea’s instance.'); return; }
            if (!name || !path) { await this.showAlertModal('Repo name and folder are both required.'); return; }
            this.creatingRepo = true;
            try {
                const res = await authFetch(`/api/v1/instances/${instanceId}/build-targets`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, path }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error((data && (data.message || data.msg)) || 'Register failed');
                await this.loadBuildTargets(instanceId);
                const created = ((data.data || data).target) || {};
                if (created.id) this.runDialogTarget = created.id;
                this.runDialogNewRepo = false;
            } catch (e) {
                this.showAlertModal('Failed to register repo: ' + (e.message || e));
            } finally {
                this.creatingRepo = false;
            }
        },

        async loadDiscovery() {
            try {
                const res = await authFetch('/api/v1/discovery');
                if (!res.ok) return;
                const data = await res.json();
                const payload = data.data || data;
                this.discoverySkills = payload.skills || [];
                this.discoveryGuidelines = payload.guidelines || [];
            } catch (e) {
                console.error('Failed to load skills/guidelines:', e);
            }
        },

        async confirmRunDialog() {
            const extra = {};
            // Simple mode ("Run with recommended settings") must not override
            // the model or provider. The backend resolves stage/release config
            // and the idea's prompt defaults. Only advanced mode sends explicit
            // overrides chosen by the user.
            if (this.runDialogAdvanced) {
                const model = (this.runDialogModel || '').trim();
                if (model) extra.model_override = model;
                if (this.runDialogProvider && this.runDialogProvider !== this.runDialogBaseProvider) {
                    extra.provider_override = this.runDialogProvider;
                }
            }
            if (this.runDialogSkills.length) extra.skills = [...this.runDialogSkills];
            if (this.runDialogGuidelines.length) extra.guidelines = [...this.runDialogGuidelines];
            const ideaId = this.runDialogIdeaId;
            const actionType = this.runDialogActionType;
            if (actionType === 'BUILD_CODE') {
                if (!this.runDialogTarget) {
                    await this.showAlertModal('Select a build target first (manage repos in Admin → AI Settings).');
                    return;
                }
                extra.target_id = this.runDialogTarget;
            }
            this.closeRunDialog();
            await this.runAction(ideaId, actionType, extra);
        },

        // Bulk actions functions
        toggleSelectAll() {
            if (this.selectedIdeaIds.length === this.paginatedIdeas.length) {
                this.selectedIdeaIds = [];
            } else {
                this.selectedIdeaIds = this.paginatedIdeas.map(i => i.id);
            }
        },

        toggleIdeaSelection(ideaId) {
            const idx = this.selectedIdeaIds.indexOf(ideaId);
            if (idx === -1) {
                this.selectedIdeaIds.push(ideaId);
            } else {
                this.selectedIdeaIds.splice(idx, 1);
            }
        },

        clearSelection() {
            this.selectedIdeaIds = [];
            this.bulkStatus = '';
        },

        confirmBulkAction() {
            if (!this.bulkStatus || this.selectedIdeaIds.length === 0) return;
            const count = this.selectedIdeaIds.length;
            const statusLabel = this.bulkStatus.charAt(0) + this.bulkStatus.slice(1).toLowerCase();
            this.bulkConfirmMessage = `Are you sure you want to change the status of <strong>${count}</strong> idea${count !== 1 ? 's' : ''} to <strong>${statusLabel}</strong>?`;
            this.bulkConfirmDetail = 'This action will create a status history record for each idea.';
            this.bulkConfirmActionLabel = `Confirm & Apply`;
            this.showBulkConfirm = true;
        },

        confirmBulkArchive() {
            // Bulk archive is its own button (not a status in the select)
            // so non-technical users see a plain-language confirmation.
            if (this.selectedIdeaIds.length === 0) return;
            this.bulkStatus = 'ARCHIVE';
            const count = this.selectedIdeaIds.length;
            this.bulkConfirmMessage = `Archive <strong>${count}</strong> idea${count !== 1 ? 's' : ''}?`;
            this.bulkConfirmDetail = 'Archived ideas are stored away and hidden from the default list. You can restore them later.';
            this.bulkConfirmActionLabel = 'Archive selected';
            this.showBulkConfirm = true;
        },

        closeBulkConfirm() {
            this.showBulkConfirm = false;
            this.bulkConfirmMessage = '';
            this.bulkConfirmDetail = '';
            this.bulkConfirmActionLabel = '';
        },

        async executeBulkAction() {
            if (!this.bulkStatus || this.selectedIdeaIds.length === 0) return;
            this.bulkUpdating = true;
            try {
                const response = await authFetch('/api/v1/ideas/bulk-status', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        idea_ids: this.selectedIdeaIds,
                        status: this.bulkStatus
                    })
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.message || 'Failed to bulk update status');
                }
                this.closeBulkConfirm();
                this.clearSelection();
                await this.loadIdeas();
                await this.loadTotalIdeas();
            } catch (error) {
                this.showAlertModal('Failed to update status: ' + error.message);
            } finally {
                this.bulkUpdating = false;
            }
        },

        async executeConfirmedAction() {
            if (!this.confirmModalIdeaId || !this.confirmModalActionType) return;
            const ideaId = this.confirmModalIdeaId;
            const actionType = this.confirmModalActionType;
            const extra = { ...(this.pendingRunExtra || {}), ...(this.confirmModalAnswers ? { answers: this.confirmModalAnswers } : {}) };
            this.pendingRunExtra = null;
            this.resolveConfirmModal();
            await this.executeAction(ideaId, actionType, extra);
        },

        async executeAction(ideaId, actionType, extra) {
            this.actionLoading = actionType;
            try {
                // Snapshot existing result ids so the poll below waits for the
                // NEW run instead of instantly matching a stale result from a
                // previous run (which also crashed when the detail modal was
                // closed mid-poll: selectedIdea is null there).
                let knownIds = [];
                try {
                    const pre = await authFetch(`/api/v1/ideas/${ideaId}/actions`);
                    const preData = await pre.json();
                    const prePayload = preData.data || preData;
                    knownIds = (prePayload.results || [])
                        .filter(r => r.action_type === actionType)
                        .map(r => r.id);
                } catch (e) { knownIds = []; }
                const body = { action_type: actionType, confirm: true, ...(extra || {}) };
                const response = await authFetch(`/api/v1/ideas/${ideaId}/actions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.message || 'Failed to run action');
                }
                const postData = await response.json();
                const runId = postData.data?.run_id;

                // Poll the PromptRun status so the user sees "Running…" instead
                // of an immediate "Done". The worker marks the run RUNNING when
                // it starts and SUCCESS/FAILED when it finishes.
                let runStatus = null;
                for (let i = 0; i < 60; i++) {
                    await new Promise(r => setTimeout(r, 2000));
                    try {
                        const statusRes = await authFetch(`/api/v1/ideas/${ideaId}/actions/${runId}/status`);
                        const statusData = await statusRes.json();
                        const payload = statusData.data || statusData;
                        runStatus = payload.status;
                        if (runStatus === 'SUCCESS' || runStatus === 'FAILED') break;
                    } catch (e) {
                        // Status endpoint may 404 briefly while the row is being
                        // committed — keep polling.
                    }
                }

                // If the run succeeded, poll for the SecondaryActionResult to
                // display the actual output. If it failed, surface the error.
                if (runStatus === 'FAILED') {
                    throw new Error('Action run failed.');
                }

                // Poll for the completed result (same logic as before).
                const poll = async () => {
                    const response = await authFetch(`/api/v1/ideas/${ideaId}/actions`);
                    const data = await response.json();
                    const payload = data.data || data;
                    const action = (payload.results || []).find(r => r.action_type === actionType && !knownIds.includes(r.id));
                    if (action) {
                        if (this.docViewVersion) delete this.docViewVersion[actionType];
                        const target = (this.selectedIdea && this.selectedIdea.id === ideaId)
                            ? this.selectedIdea
                            : (this.ideas || []).find(i => i.id === ideaId);
                        // Release children live in scaleChildren, not the list.
                        const scaleTarget = (!target && this.showScaleTab())
                            ? (this.scaleChildren || []).find(i => i.id === ideaId)
                            : null;
                        const row2 = scaleTarget || target;
                        if (row2) {
                            row2.actions = payload.results;
                            row2.actions = row2.actions.map(a => ({
                                ...a,
                                rendered_output: this.prettyActionOutput(this.displayOutput(a))
                            }));
                            if (scaleTarget) {
                                // Refresh the readiness pills from the fresh actions.
                                await this.loadScaleFamily();
                                return true;
                            }
                        }
                        return !!row2;
                    }
                    return false;
                };
                
                for (let i = 0; i < 30; i++) {
                    await new Promise(r => setTimeout(r, 2000));
                    if (await poll()) break;
                }
                return true;
            } catch (error) {
                this.showAlertModal('Failed to run action: ' + error.message);
                return false;
            } finally {
                this.actionLoading = null;
            }
        },
        
        // Scale tab: live apps only (top-level SCALE ideas). Children never
        // get it — their breadcrumb already links back to the parent.
        showScaleTab() {
            const s = this.selectedIdea;
            return !!s && s.status === 'SCALE' && !s.parent_id;
        },

        // Refine sits beside the Idea tab (pinned there in the bar), so it is
        // filtered out of the action-tab loop to avoid rendering twice.
        hasRefineTab() {
            return (this.selectedIdea?.actions || []).some((a) => a.action_type === 'REFINE');
        },

        actionTabs() {
            const seen = [];
            const actions = (this.selectedIdea?.actions || []).slice().reverse();
            for (const a of actions) {
                if (a.action_type === 'REFINE') continue;                // Existing result tabs always display (history survives
                // every transition); creation is gated by docActionVisible.
                if (!seen.find((t) => t.key === a.action_type)) {
                    const reg = (this.availableActions || []).find((r) => r.key === a.action_type);
                    const label = reg ? reg.label : a.action_type.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                    seen.push({ key: a.action_type, label });
                }
            }
            // Tests tab: only once the idea has been built.
            const hasBuild = (this.selectedIdea?.actions || []).some((a) => a.action_type === 'BUILD_CODE');
            if (hasBuild && !seen.find((t) => t.key === 'TESTS')) {
                seen.push({ key: 'TESTS', label: 'Tests' });
            }
            return seen;
        },

        actionTabResult(key) {
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            return rows.find((a) => a.is_current) || rows[rows.length - 1];
        },

        docVersionLabel(key) {
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            const cur = rows.find((a) => a.is_current) || rows[rows.length - 1];
            if (!cur) return '';
            let label = 'v' + (cur.version || 1);
            if (cur.edited_by_id) label += ' · edited';
            if (rows.length > 1) label += ` · ${rows.length - 1} prior`;
            return label;
        },

        docVersions(key) {
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            return rows.slice().sort((a, b) => (b.version || 1) - (a.version || 1));
        },

        // Row actually on screen: a pinned prior version, else current.
        docViewResult(key) {
            const rows = this.docVersions(key);
            if (!rows.length) return null;
            const v = this.docViewVersion[key];
            if (v != null && v !== '') {
                const hit = rows.find((r) => String(r.version) === String(v));
                if (hit) return hit;
            }
            return rows.find((a) => a.is_current) || rows[0];
        },

        isDocVersionSelected(key, row) {
            const v = this.docViewVersion[key];
            if (v == null || v === '') return !!row.is_current;
            return String(v) === String(row.version);
        },

        // Latest unwritten BUILD_CODE preview for this idea+tab, if any.
        buildPreview(key) {
            if (key !== 'BUILD_CODE') return null;
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            const cur = rows.find((a) => a.is_current) || rows[rows.length - 1];
            if (!cur) return null;
            const data = cur.output || {};
            const obj = typeof data === 'string' ? null : data;
            if (!obj || !Array.isArray(obj.files) || obj.written) return null;
            return cur;
        },

        async writeBuildFiles(key) {
            const row = this.buildPreview(key);
            if (!row || !this.selectedIdea) return;
            const extra = { target_id: row.target_id, confirm_build: true };
            if (row.model_used) extra.model_override = row.model_used;
            if (row.provider_used) extra.provider_override = row.provider_used;
            await this.runAction(this.selectedIdea.id, key, extra);
            await this.loadManagedApp();
        },

        buildTargetId() {
            const row = this.docViewResult('BUILD_CODE');
            return (row && row.target_id) || null;
        },

        async loadManagedApp() {
            this.managedApp = null;
            const idea = this.selectedIdea;
            if (!idea || !idea.instance_id) return;
            try {
                const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps`);
                if (!res.ok) return;
                const data = await res.json();
                const apps = ((data.data || data).apps) || [];
                const targetId = this.buildTargetId();
                this.managedApp = apps.find((a) => a.idea_id === idea.id && (!targetId || a.target_id === targetId)) || null;
                if (this.managedApp) await this.loadAppLogs();
            } catch (e) {
                console.error('Failed to load supervised app:', e);
            }
        },

        async configureManagedApp() {
            const idea = this.selectedIdea;
            const targetId = this.buildTargetId();
            if (!idea || !idea.instance_id || !targetId) return;
            this.appBusy = true;
            try {
                const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idea_id: idea.id, target_id: targetId }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error((data && (data.message || data.msg)) || 'Enable failed');
                this.managedApp = (data.data || data).app || null;
                await this.loadAppLogs();
            } catch (e) {
                this.showAlertModal('Could not enable one-click run: ' + (e.message || e));
            } finally {
                this.appBusy = false;
            }
        },

        async startManagedApp() {
            const idea = this.selectedIdea;
            if (!idea || !idea.instance_id || !this.managedApp) return;
            this.appBusy = true;
            try {
                const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps/${this.managedApp.id}/start`, { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error((data && (data.message || data.msg)) || 'Start failed');
                this.managedApp = (data.data || data).app || this.managedApp;
                this.pollManagedApp(36);
            } catch (e) {
                this.showAlertModal('Could not start the app: ' + (e.message || e));
            } finally {
                this.appBusy = false;
            }
        },

        async stopManagedApp() {
            const idea = this.selectedIdea;
            if (!idea || !idea.instance_id || !this.managedApp) return;
            this.appBusy = true;
            try {
                const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps/${this.managedApp.id}/stop`, { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error((data && (data.message || data.msg)) || 'Stop failed');
                this.managedApp = (data.data || data).app || this.managedApp;
                this.pollManagedApp(12);
            } catch (e) {
                this.showAlertModal('Could not stop the app: ' + (e.message || e));
            } finally {
                this.appBusy = false;
            }
        },

        async pollManagedApp(rounds) {
            for (let i = 0; i < (rounds || 12); i++) {
                await new Promise((r) => setTimeout(r, 5000));
                if (!this.selectedIdea || !this.managedApp) return;
                const idea = this.selectedIdea;
                try {
                    const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps`);
                    if (!res.ok) return;
                    const data = await res.json();
                    const apps = ((data.data || data).apps) || [];
                    const found = apps.find((a) => a.id === this.managedApp.id);
                    if (found) {
                        this.managedApp = found;
                        await this.loadAppLogs();
                    }
                    const live = (found && found.live) || {};
                    if (live.state === 'running' && live.healthy !== null) return;
                    if (live.state === 'stopped' || live.state === 'failed') return;
                } catch (e) { return; }
            }
        },

        async loadAppLogs() {
            const idea = this.selectedIdea;
            if (!idea || !idea.instance_id || !this.managedApp) { this.appLogText = ''; return; }
            try {
                const res = await authFetch(`/api/v1/instances/${idea.instance_id}/managed-apps/${this.managedApp.id}/logs?lines=100`);
                if (!res.ok) return;
                const data = await res.json();
                const lines = ((data.data || data).lines) || [];
                this.appLogText = lines.join('\n');
            } catch (e) {
                console.error('Failed to load app logs:', e);
            }
        },

        managedAppLive() {
            const live = (this.managedApp && this.managedApp.live) || {};
            return live.state === 'running' || this.managedApp?.state === 'starting';
        },

        managedAppHealthy() {
            const live = (this.managedApp && this.managedApp.live) || {};
            return live.state === 'running' && live.healthy === true && !!(this.managedApp.open_url || this.managedApp.health_url);
        },

        managedAppOpenUrl() {
            if (!this.managedApp) return '#';
            return this.managedApp.open_url || this.managedApp.health_url || '#';
        },

        managedAppUiUrl() {
            if (!this.managedApp || !this.selectedIdea) return '#';
            const target = String(this.managedApp.target_id || '');
            const rows = (this.selectedIdea.actions || []).filter((a) => a.action_type === 'BUILD_CODE');
            const row = rows.find((a) => String(a.target_id || '') === target && ((a.output || {}).written))
                || rows.find((a) => (a.output || {}).written);
            const data = row ? (row.output || {}) : {};
            return data.frontend_url || '#';
        },

        managedAppStatusText() {
            const app = this.managedApp;
            if (!app) return 'Not set up yet.';
            const live = app.live || {};
            if (app.state === 'failed') return 'Failed to start.';
            if (app.state === 'starting' || live.state === 'starting') return 'Starting…';
            if (app.state === 'stopping') return 'Stopping…';
            if (live.state === 'running') {
                if (live.healthy === true) return 'Running.';
                if (live.healthy === false) return 'Running, not answering yet.';
                return 'Running.';
            }
            return 'Stopped.';
        },

        managedAppDotClass() {
            const app = this.managedApp;
            if (!app) return 'bg-slate-300 dark:bg-slate-600';
            if (app.state === 'failed') return 'bg-red-500';
            const live = app.live || {};
            if (app.state === 'starting' || app.state === 'stopping') return 'bg-amber-400';
            if (live.state === 'running') return live.healthy === false ? 'bg-amber-400' : 'bg-green-500';
            return 'bg-slate-300 dark:bg-slate-600';
        },

        // Small-model command cleanup: models emit stringified lists
        // ('["python", "app.py"]') — show (and copy) the runnable form.
        // Host shells provide python3, not python: rewrite the bare
        // interpreter (command start or after && / ; / |). python3,
        // pythonw and paths are untouched; venvs provide python3 too.
        prettyBuildCmd(v) {
            let s;
            if (Array.isArray(v)) {
                s = v.join(' ');
            } else if (typeof v === 'string' && v.trim().startsWith('[')) {
                try {
                    const parsed = JSON.parse(v);
                    s = Array.isArray(parsed) ? parsed.join(' ') : v;
                } catch (e) { s = v; }
            } else {
                s = v;
            }
            return String(s ?? '').replace(/(^|&&\s*|;\s*|\|\s*|\)\s*)python(?=\s|$)/g, '$1python3');
        },

        // Copy/pasteable run instructions for one BUILD_CODE output object.
        // Every command carries its directory, duplicate Notes lines are
        // stripped, and the result feeds the How-to-run panel, the on-screen
        // document and the .md export alike.
        buildRunLines(obj) {
            const data = (obj && typeof obj === 'object' && !Array.isArray(obj)) ? obj : {};
            const lines = [];
            // Every command must be paste-and-run as-is: prefix the target
            // directory so users never have to find it themselves. The host
            // path is what works in the user's own terminal (container
            // paths like /app/... do not exist there).
            const workdir = String(data.target_host_path || data.target_path || '').replace(/"/g, '');
            const cd = workdir ? `cd "${workdir}" && ` : '';
            // Step order for non-technical readers: set up, start
            // something, open it afterwards. Docker Compose is a separate
            // alternative to Run, not an additional step.
            // Server-verified runbook (resolved working directory, venv
            // setup) wins over the raw model fields whenever present.
            const rb = (data.runbook && typeof data.runbook === 'object') ? data.runbook : null;
            if (rb && (rb.setup || rb.run)) {
                if (rb.setup) lines.push({ label: 'Setup', value: String(rb.setup), copy: true });
                if (rb.setup_fallback) lines.push({ label: 'If setup fails', value: String(rb.setup_fallback), copy: true });
                if (rb.run) lines.push({ label: 'Run', value: String(rb.run), copy: true });
            } else {
            if (workdir) {
                const paths = (Array.isArray(data.files) ? data.files : []).map((f) => f && f.path);
                const req = paths.find((p) => /(^|\/)requirements[^/]*\.txt$/.test(p || ''));
                const pkg = !req && paths.find((p) => /(^|\/)package\.json$/.test(p || ''));
                if (req) {
                    lines.push({ label: 'Setup', value: cd + 'pip3 install -r ' + req, copy: true });
                } else if (pkg) {
                    const dir = pkg.includes('/') ? pkg.slice(0, pkg.lastIndexOf('/')) : '';
                    const into = dir ? `cd "${workdir}/${dir}" && ` : cd;
                    lines.push({ label: 'Setup', value: into + 'npm install', copy: true });
                }
            }
            if (data.start_command) lines.push({ label: 'Run', value: cd + this.prettyBuildCmd(data.start_command), copy: true });
            }
            if (data.docker_compose_file) lines.push({ label: 'Docker Compose (alternative)', value: cd + '(docker compose version >/dev/null 2>&1 || sudo apt-get install -y docker-compose-v2) && (test -d /var/log/opencode || sudo mkdir -p /var/log/opencode) && (test -f .env || cp .env.example .env) && docker compose up --build', copy: true });
            // The human UI may live on a different port than the API
            // Human UI first: the supervised dashboard URL when one is
            // configured, else the frontend URL recorded at confirm time,
            // else the API URL. Readers must land on the app, not raw
            // JSON — so the Open row never names the API when a UI URL
            // exists (IDEA-9603: dashboard :3000, API :8001).
            const dashUrl = (this.managedApp && this.managedApp.open_url) || '';
            const frontUrl = data.frontend_url || '';
            const apiUrl = data.app_url || '';
            // Prefer the frontend address in prose, but show both addresses
            // as separate links so users can tell which one is live.
            const openUrl = frontUrl || apiUrl;
            const linkUrls = [];
            if (apiUrl) linkUrls.push({ label: 'Open backend (API)', value: apiUrl });
            if (frontUrl && frontUrl !== apiUrl) linkUrls.push({ label: 'Open UI (after Docker Compose)', value: frontUrl });
            linkUrls.forEach((entry) => lines.push({ label: entry.label, value: entry.value, link: true }));
            // Port adds nothing next to a clickable URL that already carries it.
            if (data.port && !data.app_url) lines.push({ label: 'Port', value: String(data.port) });
            if (data.credentials && typeof data.credentials === 'object') {
                Object.keys(data.credentials).forEach((k) => {
                    lines.push({ label: k, value: String(data.credentials[k]) });
                });
            }
            if (data.run_notes) {
                // Small models restate the rows above inside run_notes
                // ("Start command: ..." / bare URL). Strip lines that merely
                // repeat a value already shown so Notes stays signal-only.
                const seen = lines.flatMap((l) => {
                    const v = String(l.value).trim();
                    return [v, v.replace(/^cd\s+".*?"\s*&&\s*/, '')];
                }).filter(Boolean);
                const notes = String(data.run_notes).split('\n').map((ln) => {
                    // Same UI-URL preference inside notes prose: any
                    // mention of the API address points at Open instead.
                    let text = ln.trim();
                    if (apiUrl && openUrl && apiUrl !== openUrl) text = text.split(apiUrl).join(openUrl);
                    return text;
                }).filter((ln) => {
                    if (!ln) return false;
                    const bare = ln.replace(/^(start command|run|open|compose)\s*:\s*/i, '').trim();
                    // Compare prettified too: models emit stringified lists
                    // ('["python", "app.py"]') that Run shows prettified.
                    return ![ln, bare, this.prettyBuildCmd(ln), this.prettyBuildCmd(bare)].some((v) => seen.includes(v));
                }).join('\n').trim();
                if (notes) lines.push({ label: 'Notes', value: notes, pre: true });
            }
            return lines;
        },

        // Latest written BUILD_CODE version for the How-to-run panel,
        // scoped to the viewed version's target: instructions for a
        // different target's build must never pose as this one's. Falls
        // back past a same-target preview so the last working instructions
        // stay visible while a rebuild is in flight.
        buildRunInfo(key) {
            if (key !== 'BUILD_CODE') return null;
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            const viewed = this.docViewResult(key);
            const target = viewed ? String(viewed.target_id || '') : '';
            const written = rows.filter((a) => {
                const data = a.output || {};
                const obj = typeof data === 'string' ? null : data;
                return obj && obj.written && String(a.target_id || '') === target;
            });
            if (!written.length) return null;
            const row = written.find((a) => a.is_current) || written[written.length - 1];
            const data = row.output || {};
            const obj = typeof data === 'string' ? {} : data;
            const lines = this.buildRunLines(obj);
            if (!lines.length) return null;
            return { target: obj.target_name || row.target_name || '', lines };
        },

        // Raw output object of the viewed BUILD_CODE version, for the
        // Build tab's own sections (summary / write report / files).
        buildDocObj() {
            const row = this.docViewResult('BUILD_CODE');
            let obj = row && (row.output || row.result_data);
            if (typeof obj === 'string') {
                try { obj = JSON.parse(obj); } catch (e) { return {}; }
            }
            return (obj && typeof obj === 'object' && !Array.isArray(obj)) ? obj : {};
        },

        buildSummary() {
            return this.buildDocObj().summary || '';
        },

        buildWriteReport() {
            const w = this.buildDocObj().write_report;
            return Array.isArray(w) ? w : [];
        },

        buildFiles() {
            const f = this.buildDocObj().files;
            return Array.isArray(f) ? f : [];
        },

        buildFileSize(f) {
            const n = ((f && f.content) || '').length;
            return n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' chars';
        },

        async copyText(text, doneMsg) {
            try {
                await navigator.clipboard.writeText(text);
            } catch (e) {
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                try { document.execCommand('copy'); } catch (err) { /* clipboard unavailable */ }
                ta.remove();
            }
            this.exportMsg = doneMsg || 'Copied';
            setTimeout(() => { this.exportMsg = ''; }, 2000);
        },

        // Rendered display copy: BUILD_CODE file contents are truncated
        // (full text stays in result_data for export and the write phase).
        displayOutput(a) {
            const data = a.output || a.result_data;
            if (a.action_type !== 'BUILD_CODE' || !data || typeof data !== 'object' || Array.isArray(data)) {
                return data;
            }
            // Curated document, not a field dump: run instructions first
            // (shared helper, same cleanup as the How-to-run panel), then
            // the write report and a file listing. Full file contents stay
            // in the .md export; the on-screen doc stays scannable.
            const doc = {};
            if (data.summary) doc.summary = data.summary;
            const lines = this.buildRunLines(data);
            if (lines.length) {
                const how = {};
                if (!data.written) {
                    how.Status = 'Preview — confirm it (Write files) first; the commands below work once the files are written.';
                }
                lines.forEach((l) => { how[l.label] = l.value; });
                doc.how_to_run = how;
            } else if (!data.written) {
                doc.how_to_run = 'Preview only — nothing is written yet. Confirm the preview (Write files) and the run instructions will appear here.';
            }
            if (Array.isArray(data.write_report) && data.write_report.length) {
                doc.write_report = data.write_report;
            }
            const targetBits = [data.target_name].filter(Boolean);
            if (data.target_path) targetBits.push(data.target_path);
            if (targetBits.length) doc.target = targetBits.join(' · ');
            if (data.docker_image) doc.docker_image = data.docker_image;
            const files = Array.isArray(data.files) ? data.files : [];
            doc.files = files.map((f) => ({
                path: f.path,
                size: ((f.content || '').length) + ' chars',
            }));
            return doc;
        },

        setDocVersion(key, version) {
            if (version == null || version === '') {
                delete this.docViewVersion[key];
            } else {
                this.docViewVersion[key] = String(version);
            }
            const row = this.docViewResult(key);
            if (row) this.loadDocComments(row.id, true);
        },

        docActionLabel(key) {
            const found = (this.availableActions || []).find((a) => a.key === key);
            return (found && found.label) || String(key).replace(/_/g, ' ');
        },

        docToMarkdown(key) {
            const row = this.docViewResult(key);
            if (!row) return '';
            let obj = row.result_data || row.output;
            if (typeof obj === 'string') {
                try { obj = JSON.parse(obj); } catch (e) { /* plain text below */ }
            }
            const label = (k) => String(k).replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());
            const lines = [];
            const ideaRef = this.selectedIdea?.reference_code || 'idea';
            lines.push('# ' + this.docActionLabel(key) + ' — ' + ideaRef + ' (v' + (row.version || 1) + ')');
            const meta = [];
            if (row.model_used) meta.push('Model: ' + row.model_used);
            if (row.executed_at) meta.push('Generated: ' + this.formatDate(row.executed_at));
            if (meta.length) lines.push('_' + meta.join(' · ') + '_');
            const pushValue = (v, depth) => {
                const pad = '  '.repeat(depth);
                if (Array.isArray(v)) {
                    v.forEach((item) => {
                        if (item && typeof item === 'object') {
                            const parts = Object.keys(item).map((k) => '**' + label(k) + ':** ' + String(item[k] ?? ''));
                            lines.push(pad + '- ' + parts.join(' · '));
                        } else {
                            lines.push(pad + '- ' + String(item ?? ''));
                        }
                    });
                } else if (v && typeof v === 'object') {
                    Object.keys(v).forEach((k) => {
                        const sv = v[k];
                        if (sv && typeof sv === 'object' && 'score' in sv) {
                            lines.push(pad + '- **' + label(k) + ' ' + sv.score + '/10:** ' + String(sv.reasoning ?? ''));
                        } else if (sv && typeof sv === 'object') {
                            lines.push(pad + '- **' + label(k) + ':**');
                            pushValue(sv, depth + 1);
                        } else {
                            lines.push(pad + '- **' + label(k) + ':** ' + String(sv ?? ''));
                        }
                    });
                } else {
                    lines.push(pad + String(v ?? ''));
                }
            };
            if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
                lines.push(String(row.result_data ?? row.output ?? ''));
            } else if (key === 'BUILD_CODE') {
                // Same curated shape as the on-screen document: instructions
                // first (shared helper), then the untouched remainder.
                const runLines = this.buildRunLines(obj);
                const covered = ['start_command', 'app_url', 'port', 'run_notes', 'docker_compose_file', 'credentials', 'target_path', 'port_requested', 'port_changed'];
                if (runLines.length) {
                    lines.push('');
                    lines.push('## How to run');
                    runLines.forEach((l) => {
                        if (l.pre) {
                            String(l.value).split('\n').forEach((part) => lines.push(part));
                        } else if (l.link) {
                            lines.push('- **' + l.label + ':** ' + l.value);
                        } else {
                            lines.push('- **' + l.label + ':** `' + l.value + '`');
                        }
                    });
                } else if (!obj.written) {
                    lines.push('');
                    lines.push('## How to run');
                    lines.push('Preview only — nothing is written yet.');
                }
                Object.keys(obj).forEach((k) => {
                    if (covered.includes(k)) return;
                    lines.push('');
                    lines.push('## ' + label(k));
                    pushValue(obj[k], 0);
                });
            } else {
                Object.keys(obj).forEach((k) => {
                    lines.push('');
                    lines.push('## ' + label(k));
                    pushValue(obj[k], 0);
                });
            }
            const answers = row.answers || [];
            if (answers.length) {
                lines.push('');
                lines.push('## Answers');
                answers.forEach((a) => {
                    const parts = String(a).split('\n');
                    parts.forEach((part, i) => {
                        lines.push((i === 0 ? '- ' : '  ') + part);
                    });
                });
            }
            return lines.join('\n');
        },

        async copyDocMarkdown(key) {
            const md = this.docToMarkdown(key);
            if (!md) return;
            await this.copyText(md, 'Copied');
        },

        downloadDocMarkdown(key) {
            const row = this.docViewResult(key);
            const md = this.docToMarkdown(key);
            if (!row || !md) return;
            const ref = (this.selectedIdea?.reference_code || 'idea').replace(/[^A-Za-z0-9-]+/g, '-');
            const blob = new Blob([md], { type: 'text/markdown' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = ref + '-' + key + '-v' + (row.version || 1) + '.md';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); this.exportMsg = 'Saved'; }, 500);
            setTimeout(() => { this.exportMsg = ''; }, 2500);
        },

        async loadDocComments(resultId, force) {
            if (!resultId) return;
            if (!force && this.docThreads[resultId]) return;
            try {
                const res = await authFetch(`/api/v1/actions/${resultId}/comments`);
                const data = await res.json();
                const payload = data.data || data;
                this.docThreads[resultId] = payload.comments || [];
            } catch (e) {
                console.error('Failed to load document comments:', e);
            }
        },

        async postDocComment(resultId) {
            const body = (this.docDrafts[resultId] || '').trim();
            if (!body) return;
            try {
                const res = await authFetch(`/api/v1/actions/${resultId}/comments`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ body }),
                });
                if (!res.ok) throw new Error('Failed to post comment');
                this.docDrafts[resultId] = '';
                await this.loadDocComments(resultId, true);
            } catch (e) {
                this.showAlertModal('Failed to post comment: ' + e.message);
            }
        },

        async startDocEdit(key) {
            try {
                const cur = this.docCurrentResult(key) || this.actionTabResult(key);
                if (!cur || !cur.id) {
                    await this.showAlertModal('Could not load this document for editing. Try closing and reopening the details.');
                    return;
                }
                const data = cur.output || cur.result_data || {};
                this.docEditing = cur.id;
                this.docEditList = [];
                for (const k of Object.keys(data)) {
                    const v = data[k];
                    let kind = 'text';
                    let value = v ?? '';
                    if (Array.isArray(v)) {
                        kind = 'list';
                        value = v.map((x) => typeof x === 'string' ? x : JSON.stringify(x)).join('\n');
                    } else if (v && typeof v === 'object') {
                        kind = 'json';
                        value = JSON.stringify(v, null, 2);
                    } else {
                        value = String(value ?? '');
                    }
                    const label = k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                    this.docEditList.push({ key: k, label, kind, value,
                        isList: Array.isArray(v),
                        isObj: !!(v && typeof v === 'object' && !Array.isArray(v)) });
                }
                this.docEditError = '';
            } catch (e) {
                this.showAlertModal('Could not open the editor: ' + (e && e.message ? e.message : e));
            }
        },

        cancelDocEdit() {
            this.docEditing = null;
            this.docEditList = [];
            this.docEditError = '';
        },

        async saveDocEdit() {
            const parsed = {};
            for (const f of (this.docEditList || [])) {
                const raw = f.value ?? '';
                if (f.isList) {
                    parsed[f.key] = String(raw).split('\n').map((s) => s.trim()).filter(Boolean);
                } else if (f.isObj) {
                    try {
                        parsed[f.key] = JSON.parse(String(raw) || '{}');
                    } catch (e) {
                        this.docEditError = '\u201c' + f.key + '\u201d is not valid JSON: ' + e.message;
                        return;
                    }
                } else {
                    parsed[f.key] = String(raw);
                }
            }
            if (!Object.keys(parsed).length) {
                this.docEditError = 'Nothing to save.';
                return;
            }
            this.docEditSaving = true;
            try {
                const res = await authFetch(`/api/v1/actions/${this.docEditing}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ result_data: parsed }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error((data.data || data).message || data.message || 'Save failed');
                const id = this.docEditing;
                this.cancelDocEdit();
                await this.loadIdeas();
                const idea = (this.ideas || []).find(i => i.id === this.selectedIdea?.id);
                if (idea) await this.openDetailModal(idea);
                await this.loadDocComments(id, true);
            } catch (e) {
                this.docEditError = e.message;
            } finally {
                this.docEditSaving = false;
            }
        },

        docCurrentResult(key) {
            const rows = (this.selectedIdea?.actions || []).filter((a) => a.action_type === key);
            return rows.find((a) => a.is_current) || rows[rows.length - 1];
        },

        docEditorResult() {
            if (!this.docEditing) return null;
            return (this.selectedIdea?.actions || []).find((a) => a.id === this.docEditing) || null;
        },

        docEditorLabel() {
            const r = this.docEditorResult();
            if (!r) return '';
            const reg = (this.availableActions || []).find((x) => x.key === r.action_type);
            return reg ? reg.label : r.action_type;
        },

        docEditorVersion() {
            const r = this.docEditorResult();
            if (!r) return '';
            let label = 'v' + (r.version || 1);
            if (r.edited_by_id) label += ' · edited';
            return label;
        },

        prdQuestions() {
            const row = this.docViewResult('PRD_DOC');
            const data = row?.result_data || row?.output;
            const list = data && typeof data === 'object' ? data.open_questions : null;
            return Array.isArray(list) ? list : [];
        },

        prdHasAnswers() {
            return Object.values(this.prdAnswers || {}).some((v) => String(v || '').trim() !== '');
        },

        async submitPrdAnswers() {
            if (!this.selectedIdea || !this.prdHasAnswers()) return;
            const questions = this.prdQuestions();
            const answers = questions
                .map((q, i) => ({ q, a: String(this.prdAnswers[i] || '').trim() }))
                .filter((x) => x.a !== '')
                .map((x) => `Q: ${x.q}\nA: ${x.a}`);
            if (!answers.length) return;
            // Open the run dialog so the user can pick model/provider/skills
            // (as on the first run) instead of silently re-running with the
            // previous parameters.
            this.pendingRunExtra = { answers };
            await this.openRunDialog(
                this.selectedIdea.id,
                'PRD_DOC',
                this.selectedIdea.reference_code,
                this.selectedIdea.instance_id,
            );
            this.prdAnswers = {};
        },

        stageLabels: {
            SPARK: 'Spark',
            SCOPE: 'Scope',
            MAP: 'Map',
            SHIP: 'Ship',
            SCALE: 'Scale',
            DROP: 'Dropped',
            FREEZE: 'Frozen',
            ARCHIVE: 'Archived',
        },
        stageDescriptions: {
            SPARK: 'A new idea waiting to be explored.',
            SCOPE: 'The idea is being shaped and defined.',
            MAP: 'A plan is being created for the idea.',
            SHIP: 'The idea is ready to be built.',
            SCALE: 'The idea is live as a working app.',
            DROP: 'The idea was not taken forward.',
            FREEZE: 'The idea is paused for now.',
            ARCHIVE: 'The idea is stored away and closed.',
        },
        stageLabel(status) {
            return this.stageLabels[status] || status;
        },
        releaseStageLabels: {
            'planned': 'Planned',
            'in_progress': 'In progress',
            'done': 'Done',
        },
        releaseStageLabel(status) {
            return this.releaseStageLabels[status] || status.replace('_', ' ');
        },

        getStatusClass(status) {
            const classes = {
                'SPARK': 'bg-slate-100 text-slate-700',
                'SCOPE': 'bg-blue-100 text-blue-700',
                'MAP': 'bg-violet-100 text-violet-700',
                'SHIP': 'bg-indigo-100 text-indigo-700',
                'SCALE': 'bg-emerald-100 text-emerald-700',
                'DROP': 'bg-slate-100 text-slate-800',
                'FREEZE': 'bg-amber-100 text-amber-700',
                'ARCHIVE': 'bg-slate-200 text-slate-500',
            };
            return `inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${classes[status] || classes.SPARK}`;
        },
        
        formatDate(dateStr) {
            if (!dateStr) return 'Never';
            const date = new Date(dateStr);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        },
        
        // Readable one-liner for table cells: prefers a structured pitch or
        // summary over raw JSON blobs like {"elevator_pitch": "..."}.
        pickSummary(obj) {
            if (!obj || typeof obj !== 'object') return '';
            const keys = ['elevator_pitch', 'summary', 'pitch', 'description', 'overview', 'tagline', 'idea'];
            for (const k of keys) {
                if (typeof obj[k] === 'string' && obj[k].trim()) return obj[k].trim();
            }
            return '';
        },

        firstString(value) {
            if (!value) return '';
            if (typeof value === 'string') return value;
            if (Array.isArray(value)) {
                for (const v of value) {
                    const s = this.firstString(v);
                    if (s && s.trim()) return s;
                }
                return '';
            }
            if (typeof value === 'object') {
                for (const k of Object.keys(value)) {
                    const s = this.firstString(value[k]);
                    if (s && s.trim()) return s;
                }
            }
            return '';
        },

        summaryFullText(idea) {
            // Unsliced candidate text behind prettySummary (for "has more" checks).
            if (!idea) return '';
            const tryParse = (t) => {
                if (typeof t !== 'string') return null;
                const s = t.trim();
                if (!s.startsWith('{') && !s.startsWith('[')) return null;
                try { return JSON.parse(s); } catch (e) { return null; }
            };
            const fromObj = (o) => this.pickSummary(o) || this.firstString(o);
            if (idea.structured_content) {
                if (typeof idea.structured_content === 'object') {
                    return fromObj(idea.structured_content) || '';
                }
                const o = tryParse(idea.structured_content);
                if (o) return fromObj(o) || '';
                return String(idea.structured_content);
            }
            const raw = idea.summary || idea.raw_content || '';
            const o = tryParse(raw);
            if (o) return fromObj(o) || '';
            return String(raw);
        },

        hasMoreSummary(idea) {
            return this.summaryFullText(idea).length > 220;
        },

        actionChips(idea) {
            // Richness signals: which follow-up analyses already live inside.
            // Registry-driven (like the detail tabs) so new actions appear
            // with no UI changes; deduped (versions share one chip).
            const done = idea && Array.isArray(idea.actions_run) ? [...new Set(idea.actions_run)] : [];
            return done.map((k) => {
                const reg = (this.availableActions || []).find((r) => r.key === k);
                const label = reg
                    ? (reg.done_label || reg.label)
                    : k.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                return { key: k, label };
            });
        },

        prettySummary(idea) {
            if (!idea) return '';
            const tryParse = (t) => {
                if (typeof t !== 'string') return null;
                const s = t.trim();
                if (!s.startsWith('{') && !s.startsWith('[')) return null;
                try { return JSON.parse(s); } catch (e) { return null; }
            };
            const fromObj = (o) => this.pickSummary(o) || this.firstString(o);
            // Structured content wins when present.
            if (idea.structured_content) {
                if (typeof idea.structured_content === 'object') {
                    const s = fromObj(idea.structured_content);
                    if (s) return s.slice(0, 220);
                } else {
                    const o = tryParse(idea.structured_content);
                    if (o) {
                        const s = fromObj(o);
                        if (s) return s.slice(0, 220);
                    } else {
                        return String(idea.structured_content).slice(0, 220);
                    }
                }
            }
            const raw = idea.summary || idea.raw_content || '';
            const o = tryParse(raw);
            if (o) {
                const s = fromObj(o);
                if (s) return s.slice(0, 220);
            }
            return String(raw).slice(0, 220);
        },

        // Secondary-action rendering: structured results become labelled
        // sections (Elevator Pitch, Target Audience, ...) instead of raw JSON.
        prettyActionOutput(data) {
            let obj = data;
            if (typeof obj === 'string') {
                const t = obj.trim();
                if (!t.startsWith('{')) return this.renderMarkdown(obj);
                try { obj = JSON.parse(t); } catch (e) { return this.renderMarkdown(obj); }
            }
            if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
                return this.renderMarkdown(String(data ?? ''));
            }
            const esc = (s) => String(s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            const label = (k) => k.replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());
            const renderValue = (v) => {
                if (Array.isArray(v)) {
                    const items = v.map((item) => (item && typeof item === 'object')
                        ? Object.keys(item).map((k) => '<strong>' + esc(label(k)) + ':</strong> ' + esc(typeof item[k] === 'object' ? JSON.stringify(item[k]) : String(item[k] ?? ''))).join('<br>')
                        : esc(String(item ?? '')));
                    return '<ul class="list-disc pl-5 space-y-1"><li>' + items.join('</li><li>') + '</li></ul>';
                }
                if (v && typeof v === 'object') {
                    return '<ul class="list-disc pl-5 space-y-1">' + Object.keys(v).map((k) => {
                        const sv = v[k];
                        const inner = (sv && typeof sv === 'object')
                            ? esc(JSON.stringify(sv))
                            : (/^(https?:\/\/)/.test(String(sv ?? '')) ? esc(String(sv)) : this.renderMarkdown(String(sv ?? '')));
                        if (sv && typeof sv === 'object' && 'score' in sv) {
                            return '<li><strong>' + esc(label(k)) + ' ' + esc(String(sv.score)) + '/10:</strong> ' + esc(String(sv.reasoning ?? '')) + '</li>';
                        }
                        return '<li><strong>' + esc(label(k)) + ':</strong> ' + inner + '</li>';
                    }).join('') + '</ul>';
                }
                return this.renderMarkdown(String(v ?? ''));
            };
            return Object.keys(obj).map((k) => {
                return '<div class="mb-3"><div class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">'
                    + esc(label(k)) + '</div><div class="text-sm text-slate-700 dark:text-slate-300">'
                    + renderValue(obj[k]) + '</div></div>';
            }).join('');
        },

        // Full-idea rendering for the detail modal: JSON blobs become
        // labelled sections instead of a raw dump.
        prettyContent(idea) {            if (!idea) return '';
            const text = idea.content || idea.raw_content || '';
            const t = String(text).trim();
            if (!t.startsWith('{')) return this.renderMarkdown(t);
            let obj;
            try { obj = JSON.parse(t); } catch (e) { return this.renderMarkdown(t); }
            if (!obj || typeof obj !== 'object') return this.renderMarkdown(t);
            const esc = (s) => String(s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            const label = (k) => k.replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());
            return Object.keys(obj).map((k) => {
                const v = obj[k];
                const body = (v && typeof v === 'object')
                    ? '<code>' + esc(JSON.stringify(v, null, 2)) + '</code>'
                    : this.renderMarkdown(String(v ?? ''));
                return '<div class="mb-3"><div class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">'
                    + esc(label(k)) + '</div><div class="text-sm text-slate-700 dark:text-slate-300">'
                    + body + '</div></div>';
            }).join('');
        },

        timeAgo(dateStr) {
            if (!dateStr) return 'Never';
            const s = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
            if (isNaN(s) || s < 0) return this.formatDate(dateStr);
            if (s < 60) return 'just now';
            if (s < 3600) {
                const m = Math.floor(s / 60);
                return m + (m === 1 ? ' min ago' : ' mins ago');
            }
            if (s < 86400) {
                const h = Math.floor(s / 3600);
                return h + (h === 1 ? ' hour ago' : ' hours ago');
            }
            const d = Math.floor(s / 86400);
            if (d === 1) return 'yesterday';
            if (d < 7) return d + ' days ago';
            return this.formatDate(dateStr);
        },

        formatDuration(seconds) {
            if (seconds === null || seconds === undefined) return '—';
            const s = Math.round(seconds);
            if (s < 60) return s + 's';
            const m = Math.floor(s / 60);
            const rest = s % 60;
            return rest ? m + 'm ' + rest + 's' : m + 'm';
        },

        renderMarkdown(text) {
            if (!text) return '';
            // The result is injected with x-html, so escape first and only
            // then apply the inline markdown transforms. Escaping at every
            // call site was the bug: most of them passed raw idea content.
            const escaped = String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
            return escaped
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.+?)\*/g, '<em>$1</em>')
                .replace(/`(.+?)`/g, '<code>$1</code>')
                .replace(/\n/g, '<br>');
        },
    };
}
