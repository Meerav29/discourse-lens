<script>
  import { api } from '../lib/api.js';
  import { PRESET_QUERIES } from '../lib/presets.js';

  let query = '';
  let lastQuery = '';
  let loading = false;
  let answer = null;
  let citations = [];
  let error = null;

  async function submit(q) {
    if (!q.trim() || loading) return;
    query = q;
    lastQuery = q;
    loading = true;
    answer = null;
    citations = [];
    error = null;
    try {
      const res = await api.chat(q);
      answer = res.answer;
      citations = res.citations || [];
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit(query);
    }
  }
</script>

<div class="panel">
  <div class="presets">
    {#each PRESET_QUERIES as q}
      <button
        class="preset-btn"
        on:click={() => submit(q)}
        disabled={loading}
      >{q}</button>
    {/each}
  </div>

  <div class="output">
    {#if loading}
      <div class="thinking">Searching corpus…</div>
    {:else if error}
      <div class="error">{error}</div>
      <button class="retry-btn" on:click={() => submit(lastQuery)}>Try again</button>
    {:else if answer}
      <div class="answer">{answer}</div>
      {#if citations.length > 0}
        <div class="citations">
          <div class="cit-label">Sources</div>
          {#each citations as c}
            <a class="cit" href={c.url} target="_blank" rel="noopener noreferrer">
              <span class="cit-title">{c.title || c.domain}</span>
              <span class="cit-domain">{c.domain}</span>
            </a>
          {/each}
        </div>
      {/if}
    {:else}
      <div class="empty">Ask a question about the indexed corpus.</div>
    {/if}
  </div>

  <div class="input-row">
    <textarea
      bind:value={query}
      on:keydown={handleKey}
      placeholder="Ask about themes, gaps, disagreements…"
      rows="2"
      disabled={loading}
    ></textarea>
    <button class="send" on:click={() => submit(query)} disabled={!query.trim() || loading}>
      {loading ? '…' : '→'}
    </button>
  </div>
</div>

<style>
  .panel {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .presets {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-bottom: 1px solid #161620;
    flex-shrink: 0;
  }
  .preset-btn {
    background: #15151f;
    border: 1px solid #232336;
    border-radius: 5px;
    color: #888;
    font-size: 0.68rem;
    padding: 5px 8px;
    text-align: left;
    cursor: pointer;
    line-height: 1.35;
    transition: background 0.1s, color 0.1s;
  }
  .preset-btn:hover:not(:disabled) {
    background: #1e1e2e;
    color: #c8c8d8;
  }
  .preset-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .output {
    flex: 1;
    overflow-y: auto;
    padding: 12px 12px 8px;
    min-height: 0;
  }
  .thinking, .empty {
    font-size: 0.78rem;
    color: #444;
    text-align: center;
    padding: 1.5rem 0;
  }
  .thinking { color: #5a7fff; }
  .error {
    font-size: 0.78rem;
    color: #ff6b6b;
  }
  .retry-btn {
    margin-top: 8px;
    background: #1e1e2e;
    border: 1px solid #2e2e44;
    border-radius: 5px;
    color: #888;
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .retry-btn:hover { background: #28283e; color: #c8c8d8; }
  .answer {
    font-size: 0.82rem;
    color: #c8c8d8;
    line-height: 1.65;
    white-space: pre-wrap;
  }
  .citations {
    margin-top: 12px;
    border-top: 1px solid #161620;
    padding-top: 10px;
  }
  .cit-label {
    font-size: 0.65rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }
  .cit {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 6px;
    padding: 4px 0;
    text-decoration: none;
    border-bottom: 1px solid #0d0d14;
  }
  .cit:hover .cit-title { color: #5a7fff; }
  .cit-title {
    font-size: 0.72rem;
    color: #888;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    transition: color 0.1s;
  }
  .cit-domain {
    font-size: 0.65rem;
    color: #444;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .input-row {
    display: flex;
    gap: 6px;
    padding: 8px;
    border-top: 1px solid #161620;
    flex-shrink: 0;
    align-items: flex-end;
  }
  textarea {
    flex: 1;
    background: #15151f;
    border: 1px solid #232336;
    border-radius: 6px;
    color: #e0e0f0;
    font-size: 0.8rem;
    padding: 7px 10px;
    resize: none;
    font-family: inherit;
    line-height: 1.4;
    outline: none;
    transition: border-color 0.15s;
  }
  textarea:focus { border-color: #5a7fff; }
  textarea::placeholder { color: #444; }
  textarea:disabled { opacity: 0.5; }
  .send {
    background: #5a7fff;
    border: none;
    border-radius: 6px;
    color: white;
    font-size: 1rem;
    width: 32px;
    height: 32px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.1s;
  }
  .send:hover:not(:disabled) { background: #7090ff; }
  .send:disabled { background: #2a2a40; color: #444; cursor: not-allowed; }
</style>
