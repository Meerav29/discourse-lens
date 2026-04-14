<script>
  import { api } from '../lib/api.js';
  import ClusterMap from '../components/ClusterMap.svelte';
  import OutlierFinder from '../components/OutlierFinder.svelte';
  import TemporalDrift from '../components/TemporalDrift.svelte';
  import ConsensusBars from '../components/ConsensusBars.svelte';
  import ChatPanel from '../components/ChatPanel.svelte';
  import ArticleSidebar from '../components/ArticleSidebar.svelte';

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

  // --- Tab in bottom-right panel ---
  let activeTab = 'consensus'; // 'consensus' | 'chat'

  // --- Export ---
  let exporting = false;
  let exportError = null;

  // --- Computed: filtered outliers ---
  $: filteredOutliers = selectedCluster == null
    ? outliers
    : outliers.filter(o => o.cluster_id === selectedCluster);

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
    } catch (e) {
      // transient network error — keep polling
    }
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
  }

  function handleSelectCluster(id) {
    selectedCluster = id;
    // Refetch outliers filtered by cluster if needed (or just filter client-side)
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
</script>

<!-- ── INPUT PHASE ─────────────────────────────────────────── -->
{#if phase === 'input'}
  <main class="input-page">
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
        <button type="submit" disabled={!topic.trim()}>
          Analyze Discourse
        </button>
      </form>
    </section>
  </main>

<!-- ── LOADING PHASE ───────────────────────────────────────── -->
{:else if phase === 'loading'}
  <main class="loading-page">
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
      <span class="results-meta">{points.length} points · {[...new Set(points.map(p => p.cluster_id))].length} clusters</span>
      {#if exportError}
        <span class="export-error">{exportError}</span>
      {/if}
      <button class="export-btn" on:click={handleExport} disabled={exporting}>
        {exporting ? 'Exporting…' : 'Export'}
      </button>
      <button class="new-btn" on:click={resetToInput}>New analysis</button>
    </header>

    <!-- 4-panel grid -->
    <div class="panels">
      <!-- Top-left: Cluster Map -->
      <section class="panel panel-map">
        <div class="panel-title">Cluster Map</div>
        <div class="panel-body">
          <ClusterMap
            {points}
            {selectedCluster}
            onSelectCluster={handleSelectCluster}
            onSelectArticle={handleSelectArticle}
          />
        </div>
      </section>

      <!-- Top-right: Outlier Finder -->
      <section class="panel panel-outliers">
        <div class="panel-title">
          Outliers
          {#if selectedCluster != null}
            <span class="filter-badge">cluster filter active</span>
          {/if}
        </div>
        <div class="panel-body">
          <OutlierFinder
            outliers={filteredOutliers}
            onSelectArticle={handleSelectArticle}
          />
        </div>
      </section>

      <!-- Bottom-left: Temporal Drift -->
      <section class="panel panel-temporal">
        <div class="panel-title">Temporal Drift</div>
        <div class="panel-body temporal-body">
          <TemporalDrift {points} />
        </div>
      </section>

      <!-- Bottom-right: Tabs (Consensus | Chat) -->
      <section class="panel panel-tabs">
        <div class="panel-title tabs-title">
          <button
            class="tab"
            class:active={activeTab === 'consensus'}
            on:click={() => activeTab = 'consensus'}
          >Consensus</button>
          <button
            class="tab"
            class:active={activeTab === 'chat'}
            on:click={() => activeTab = 'chat'}
          >Ask</button>
        </div>
        <div class="panel-body">
          {#if activeTab === 'consensus'}
            <ConsensusBars
              {points}
              {selectedCluster}
              onSelectCluster={handleSelectCluster}
            />
          {:else}
            <ChatPanel />
          {/if}
        </div>
      </section>
    </div>

    <!-- Article sidebar overlay -->
    <ArticleSidebar
      articleId={selectedArticleId}
      onClose={closeSidebar}
    />
  </div>
{/if}

<style>
  /* ── Global ────────────────────────────── */
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: #0f0f13;
    color: #e8e8f0;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Input page ─────────────────────────── */
  .input-page {
    max-width: 720px;
    margin: 0 auto;
    padding: 4rem 2rem;
    height: 100vh;
    box-sizing: border-box;
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
  }
  header p {
    color: #888;
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
    background: #1a1a24;
    border: 1px solid #2e2e40;
    border-radius: 8px;
    color: #e8e8f0;
    outline: none;
    transition: border-color 0.15s;
  }
  input[type="text"]:focus { border-color: #5a7fff; }
  input[type="text"]::placeholder { color: #555; }
  button[type="submit"] {
    padding: 0.8rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    background: #5a7fff;
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
  }
  button[type="submit"]:hover:not(:disabled) { background: #7090ff; }
  button[type="submit"]:disabled {
    background: #2e2e40;
    color: #555;
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
    color: #c8c8d8;
    margin-bottom: 1.5rem;
    line-height: 1.4;
  }
  .load-status {
    font-size: 0.82rem;
    color: #555;
    margin-bottom: 12px;
  }
  .progress-track {
    height: 3px;
    background: #1c1c28;
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 8px;
  }
  .progress-fill {
    height: 100%;
    background: #5a7fff;
    border-radius: 2px;
    transition: width 0.5s ease;
  }
  .progress-pct {
    font-size: 0.72rem;
    color: #333;
  }
  .load-error {
    font-size: 0.85rem;
    color: #ff6b6b;
    margin-bottom: 16px;
  }
  .retry-btn {
    background: #2a2a40;
    border: 1px solid #3a3a55;
    color: #888;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .retry-btn:hover { background: #32324a; color: #c8c8d8; }

  /* ── Results layout ──────────────────────── */
  .results-root {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  .results-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 16px;
    height: 44px;
    border-bottom: 1px solid #161620;
    flex-shrink: 0;
  }
  .results-topic {
    font-size: 0.85rem;
    font-weight: 600;
    color: #c8c8d8;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }
  .results-meta {
    font-size: 0.72rem;
    color: #444;
    white-space: nowrap;
  }
  .new-btn {
    background: none;
    border: 1px solid #2a2a40;
    border-radius: 5px;
    color: #666;
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
  }
  .new-btn:hover { background: #15151f; color: #c8c8d8; }

  .export-btn {
    background: none;
    border: 1px solid #2a2a40;
    border-radius: 5px;
    color: #666;
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
  }
  .export-btn:hover:not(:disabled) { background: #15151f; color: #c8c8d8; }
  .export-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .export-error {
    font-size: 0.72rem;
    color: #ff6b6b;
    white-space: nowrap;
  }

  /* ── Panels ──────────────────────────────── */
  .panels {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr 320px;
    grid-template-rows: 1fr 1fr;
    gap: 0;
  }
  .panel {
    display: flex;
    flex-direction: column;
    border-right: 1px solid #161620;
    border-bottom: 1px solid #161620;
    min-height: 0;
    overflow: hidden;
  }
  .panel:last-child { border-bottom: none; }
  .panel-map { grid-column: 1; grid-row: 1; }
  .panel-outliers { grid-column: 2; grid-row: 1; border-right: none; }
  .panel-temporal { grid-column: 1; grid-row: 2; border-bottom: none; }
  .panel-tabs { grid-column: 2; grid-row: 2; border-right: none; border-bottom: none; }

  .panel-title {
    font-size: 0.63rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #333;
    padding: 7px 14px;
    border-bottom: 1px solid #161620;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .filter-badge {
    font-size: 0.6rem;
    background: #5a7fff22;
    color: #5a7fff;
    border-radius: 3px;
    padding: 1px 5px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 500;
  }

  .panel-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .temporal-body {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Tabs title ──────────────────────────── */
  .tabs-title {
    padding: 0;
  }
  .tab {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #333;
    font-size: 0.63rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    padding: 7px 14px;
    cursor: pointer;
    transition: color 0.1s, border-color 0.1s;
    height: 100%;
  }
  .tab:hover { color: #888; }
  .tab.active {
    color: #c8c8d8;
    border-bottom-color: #5a7fff;
  }
</style>
