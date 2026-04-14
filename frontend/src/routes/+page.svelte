<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import ClusterMap from '../components/ClusterMap.svelte';
  import OutlierFinder from '../components/OutlierFinder.svelte';
  import TemporalDrift from '../components/TemporalDrift.svelte';
  import ConsensusBars from '../components/ConsensusBars.svelte';
  import ChatPanel from '../components/ChatPanel.svelte';
  import ArticleSidebar from '../components/ArticleSidebar.svelte';

  // --- Theme ---
  let theme = 'dark';

  onMount(() => {
    const saved = localStorage.getItem('discourse-theme');
    theme = saved ?? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
  });

  function toggleTheme() {
    theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('discourse-theme', theme);
  }

  // --- Phase state ---
  let phase = 'input'; // 'input' | 'loading' | 'results'

  // --- Input ---
  let topic = '';

  // --- Job polling ---
  let jobId = null;
  let jobStatus = null;
  let jobProgress = 0;
  let jobError = null;
  let pollTimer = null;

  // --- Corpus ---
  let points = [];
  let outliers = [];
  let currentTopic = '';

  // --- Cross-view state ---
  let selectedCluster = null;
  let selectedArticleId = null;

  // --- Active tab in main view ---
  let activeView = 'map'; // 'map' | 'temporal' | 'outliers' | 'consensus'

  // --- Export ---
  let exporting = false;
  let exportError = null;

  // --- Computed ---
  $: filteredOutliers = selectedCluster == null
    ? outliers
    : outliers.filter(o => o.cluster_id === selectedCluster);

  $: clusterCount = [...new Set(points.map(p => p.cluster_id))].length;

  async function handleSubmit() {
    if (!topic.trim()) return;
    currentTopic = topic.trim();
    phase = 'loading';
    jobStatus = 'queued';
    jobProgress = 0;
    jobError = null;
    points = [];
    outliers = [];
    selectedCluster = null;
    selectedArticleId = null;

    try {
      const res = await api.startJob(currentTopic);
      jobId = res.job_id;
      startPolling();
    } catch (e) {
      jobError = e.message;
      jobStatus = 'error';
    }
  }

  function startPolling() {
    clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 2000);
  }

  async function pollJob() {
    if (!jobId) return;
    try {
      const job = await api.getJob(jobId);
      jobStatus = job.status;
      jobProgress = job.progress || 0;
      if (job.status === 'done') {
        clearInterval(pollTimer);
        await loadResults();
      } else if (job.status === 'error') {
        clearInterval(pollTimer);
        jobError = job.error_msg || 'Unknown error';
      }
    } catch (e) { /* transient — keep polling */ }
  }

  async function loadResults() {
    try {
      const [corpusData, outliersData] = await Promise.all([
        api.getCorpus(),
        api.getOutliers(),
      ]);
      points = corpusData;
      outliers = outliersData;
      phase = 'results';
    } catch (e) {
      jobError = e.message;
      jobStatus = 'error';
    }
  }

  function resetToInput() {
    clearInterval(pollTimer);
    phase = 'input';
    topic = '';
    jobId = null;
    jobStatus = null;
    jobProgress = 0;
    jobError = null;
    points = [];
    outliers = [];
    selectedCluster = null;
    selectedArticleId = null;
    activeView = 'map';
  }

  function handleSelectCluster(id) {
    selectedCluster = id;
  }

  function handleSelectArticle(id) {
    selectedArticleId = id;
  }

  function closeSidebar() {
    selectedArticleId = null;
  }

  async function handleExport() {
    exporting = true;
    exportError = null;
    try {
      const blob = await api.exportZip();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'discourse-export.zip';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      exportError = e.message;
    } finally {
      exporting = false;
    }
  }

  const STATUS_LABELS = {
    queued: 'Queued…',
    crawling: 'Crawling articles…',
    processing: 'Extracting content…',
    embedding: 'Embedding chunks…',
    projecting: 'Computing clusters…',
    done: 'Done',
    error: 'Error',
  };

  const TABS = [
    { id: 'map',       label: 'Cluster Map'    },
    { id: 'temporal',  label: 'Temporal Drift' },
    { id: 'outliers',  label: 'Outliers'       },
    { id: 'consensus', label: 'Consensus'      },
  ];
</script>

<!-- ── INPUT PHASE ─────────────────────────────────────────── -->
{#if phase === 'input'}
  <main class="input-page">
    <button class="theme-toggle-float" on:click={toggleTheme} aria-label="Toggle theme">
      {#if theme === 'dark'}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      {:else}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      {/if}
    </button>
    <header>
      <h1>Discourse Lens</h1>
      <p>Map the shape of any conversation in under 10 minutes.</p>
    </header>
    <section class="input-section">
      <form on:submit|preventDefault={handleSubmit}>
        <input
          type="text"
          bind:value={topic}
          placeholder="Enter a topic (e.g. mechanistic interpretability in large language models)"
          aria-label="Research topic"
          autofocus
        />
        <button type="submit" disabled={!topic.trim()}>Analyze Discourse</button>
      </form>
    </section>
  </main>

<!-- ── LOADING PHASE ───────────────────────────────────────── -->
{:else if phase === 'loading'}
  <main class="loading-page">
    <button class="theme-toggle-float" on:click={toggleTheme} aria-label="Toggle theme">
      {#if theme === 'dark'}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      {:else}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      {/if}
    </button>
    <div class="loading-card">
      <div class="loading-topic">{currentTopic}</div>
      {#if jobStatus === 'error'}
        <div class="load-error">{jobError || 'Pipeline failed.'}</div>
        <button class="retry-btn" on:click={resetToInput}>Try again</button>
      {:else}
        <div class="load-status">{STATUS_LABELS[jobStatus] || jobStatus}</div>
        <div class="progress-track">
          <div class="progress-fill" style="width:{jobProgress}%"></div>
        </div>
        <div class="progress-pct">{jobProgress}%</div>
      {/if}
    </div>
  </main>

<!-- ── RESULTS PHASE ───────────────────────────────────────── -->
{:else if phase === 'results'}
  <div class="results-root">

    <!-- Top bar -->
    <header class="results-bar">
      <span class="results-topic">{currentTopic}</span>
      <span class="results-meta">{points.length} points · {clusterCount} clusters</span>
      <div class="bar-actions">
        {#if exportError}<span class="export-error">{exportError}</span>{/if}
        <button class="icon-btn export-btn" on:click={handleExport} disabled={exporting}>
          {exporting ? 'Exporting…' : 'Export'}
        </button>
        <button class="icon-btn" on:click={resetToInput}>New analysis</button>
        <button class="theme-btn" on:click={toggleTheme} aria-label="Toggle theme">
          {#if theme === 'dark'}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          {:else}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          {/if}
        </button>
      </div>
    </header>

    <!-- Tab bar -->
    <nav class="tab-bar">
      {#each TABS as tab}
        <button
          class="tab-btn"
          class:active={activeView === tab.id}
          on:click={() => activeView = tab.id}
        >
          {tab.label}
          {#if tab.id === 'outliers' && selectedCluster != null}
            <span class="tab-dot"></span>
          {/if}
        </button>
      {/each}
    </nav>

    <!-- Content area -->
    <div class="content-area">

      <!-- Main tabbed view -->
      <div class="view-area">
        <div class="view-panel" class:active={activeView === 'map'}>
          <ClusterMap
            {points}
            {selectedCluster}
            onSelectCluster={handleSelectCluster}
            onSelectArticle={handleSelectArticle}
          />
        </div>

        <div class="view-panel" class:active={activeView === 'temporal'}>
          <div class="temporal-wrap">
            <TemporalDrift {points} />
          </div>
        </div>

        <div class="view-panel" class:active={activeView === 'outliers'}>
          <OutlierFinder
            outliers={filteredOutliers}
            onSelectArticle={handleSelectArticle}
          />
        </div>

        <div class="view-panel" class:active={activeView === 'consensus'}>
          <ConsensusBars
            {points}
            {selectedCluster}
            onSelectCluster={handleSelectCluster}
          />
        </div>
      </div>

      <!-- Persistent right sidebar -->
      <aside class="right-sidebar">
        <div class="sidebar-section sidebar-outliers">
          <div class="sidebar-header">
            Outliers
            {#if selectedCluster != null}
              <span class="filter-badge">filtered</span>
            {/if}
          </div>
          <div class="sidebar-scroll">
            <OutlierFinder
              outliers={filteredOutliers}
              onSelectArticle={handleSelectArticle}
            />
          </div>
        </div>
        <div class="sidebar-section sidebar-chat">
          <div class="sidebar-header">Ask</div>
          <ChatPanel />
        </div>
      </aside>
    </div>

    <!-- Article overlay -->
    <ArticleSidebar
      articleId={selectedArticleId}
      onClose={closeSidebar}
    />
  </div>
{/if}

<style>
  /* ── CSS Variables ──────────────────────────────────────── */
  :global(:root) {
    --bg: #0f0f13;
    --surface: #1a1a24;
    --surface-2: #15151f;
    --surface-3: #13131e;
    --border: #161620;
    --border-2: #232336;
    --border-3: #2e2e40;
    --track: #1c1c28;
    --text: #e8e8f0;
    --text-2: #c8c8d8;
    --text-3: #888888;
    --text-4: #555555;
    --text-5: #444444;
    --text-6: #333333;
    --accent: #5a7fff;
    --accent-h: #7090ff;
    --accent-t: rgba(90,127,255,0.13);
    --err: #ff6b6b;
  }
  :global([data-theme="light"]) {
    --bg: #f3f3f8;
    --surface: #ffffff;
    --surface-2: #ededf4;
    --surface-3: #ffffff;
    --border: #e4e4f0;
    --border-2: #d4d4e4;
    --border-3: #c4c4d8;
    --track: #e8e8f4;
    --text: #14141f;
    --text-2: #30304e;
    --text-3: #60607e;
    --text-4: #80809a;
    --text-5: #9090a8;
    --text-6: #a8a8bc;
    --accent: #3d5ce8;
    --accent-h: #2d4cd8;
    --accent-t: rgba(61,92,232,0.12);
    --err: #c83030;
  }

  :global(*, *::before, *::after) { box-sizing: border-box; }

  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    overflow: hidden;
    transition: background 0.2s, color 0.2s;
  }

  /* ── Theme toggle (floating, input/loading pages) ────────── */
  .theme-toggle-float {
    position: fixed;
    top: 16px;
    right: 16px;
    background: var(--surface);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    color: var(--text-3);
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    z-index: 50;
    transition: background 0.1s, color 0.1s;
  }
  .theme-toggle-float:hover { color: var(--text); background: var(--surface-2); }

  /* ── Input page ─────────────────────────── */
  .input-page {
    max-width: 720px;
    margin: 0 auto;
    padding: 4rem 2rem;
    height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  header {
    margin-bottom: 3rem;
    text-align: center;
  }
  h1 {
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    letter-spacing: -0.03em;
    color: var(--text);
  }
  header p {
    color: var(--text-3);
    font-size: 1.1rem;
    margin: 0;
  }
  .input-section form {
    display: flex;
    gap: 0.75rem;
  }
  input[type="text"] {
    flex: 1;
    padding: 0.8rem 1rem;
    font-size: 1rem;
    background: var(--surface);
    border: 1px solid var(--border-3);
    border-radius: 8px;
    color: var(--text);
    outline: none;
    transition: border-color 0.15s;
  }
  input[type="text"]:focus { border-color: var(--accent); }
  input[type="text"]::placeholder { color: var(--text-5); }
  button[type="submit"] {
    padding: 0.8rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
  }
  button[type="submit"]:hover:not(:disabled) { background: var(--accent-h); }
  button[type="submit"]:disabled {
    background: var(--border-3);
    color: var(--text-5);
    cursor: not-allowed;
  }

  /* ── Loading page ────────────────────────── */
  .loading-page {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
  }
  .loading-card {
    text-align: center;
    width: 400px;
    padding: 2rem;
  }
  .loading-topic {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-2);
    margin-bottom: 1.5rem;
    line-height: 1.4;
  }
  .load-status {
    font-size: 0.82rem;
    color: var(--text-5);
    margin-bottom: 12px;
  }
  .progress-track {
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 8px;
  }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.5s ease;
  }
  .progress-pct {
    font-size: 0.72rem;
    color: var(--text-6);
  }
  .load-error {
    font-size: 0.85rem;
    color: var(--err);
    margin-bottom: 16px;
  }
  .retry-btn {
    background: var(--surface);
    border: 1px solid var(--border-3);
    color: var(--text-3);
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .retry-btn:hover { background: var(--surface-2); color: var(--text-2); }

  /* ── Results layout ──────────────────────── */
  .results-root {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* Top bar */
  .results-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    height: 42px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .results-topic {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }
  .results-meta {
    font-size: 0.7rem;
    color: var(--text-5);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .bar-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .export-error {
    font-size: 0.7rem;
    color: var(--err);
    white-space: nowrap;
  }
  .icon-btn {
    background: none;
    border: 1px solid var(--border-2);
    border-radius: 5px;
    color: var(--text-4);
    font-size: 0.72rem;
    padding: 4px 10px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
  }
  .icon-btn:hover:not(:disabled) { background: var(--surface-2); color: var(--text-2); }
  .icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .theme-btn {
    background: none;
    border: 1px solid var(--border-2);
    border-radius: 5px;
    color: var(--text-3);
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
    flex-shrink: 0;
  }
  .theme-btn:hover { background: var(--surface-2); color: var(--text); }

  /* Tab bar */
  .tab-bar {
    display: flex;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    background: var(--bg);
  }
  .tab-btn {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-5);
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0 16px;
    height: 34px;
    cursor: pointer;
    transition: color 0.12s, border-color 0.12s;
    position: relative;
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }
  .tab-btn:hover { color: var(--text-3); }
  .tab-btn.active {
    color: var(--text-2);
    border-bottom-color: var(--accent);
  }
  .tab-dot {
    width: 5px;
    height: 5px;
    background: var(--accent);
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* Content area (main view + sidebar) */
  .content-area {
    flex: 1;
    min-height: 0;
    display: flex;
    overflow: hidden;
  }

  /* Tabbed main view */
  .view-area {
    flex: 1;
    min-width: 0;
    position: relative;
    overflow: hidden;
    border-right: 1px solid var(--border);
  }
  .view-panel {
    position: absolute;
    inset: 0;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.18s ease;
    overflow: hidden;
  }
  .view-panel.active {
    opacity: 1;
    pointer-events: auto;
  }
  /* Temporal needs flex column for chart + controls */
  .temporal-wrap {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Right sidebar */
  .right-sidebar {
    width: 300px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .sidebar-section {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .sidebar-outliers {
    flex: 4;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-chat {
    flex: 6;
  }
  .sidebar-header {
    font-size: 0.62rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--text-6);
    padding: 6px 14px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .filter-badge {
    font-size: 0.58rem;
    background: var(--accent-t);
    color: var(--accent);
    border-radius: 3px;
    padding: 1px 5px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 500;
  }
  .sidebar-scroll {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
</style>
