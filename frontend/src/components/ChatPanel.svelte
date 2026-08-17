<script>
  import { api } from '../lib/api.js';
  import { PRESET_QUERIES } from '../lib/presets.js';
  import { marked } from 'marked';
  import { afterUpdate } from 'svelte';

  marked.setOptions({ breaks: true, gfm: true });

  let query = '';
  let loading = false;
  let error = null;
  let messages = []; // { role: 'user'|'assistant', text, citations }

  let historyEl;

  afterUpdate(() => {
    if (historyEl) {
      historyEl.scrollTop = historyEl.scrollHeight;
    }
  });

  async function submit(q) {
    if (!q.trim() || loading) return;
    const userText = q.trim();
    query = '';
    error = null;
    messages = [...messages, { role: 'user', text: userText }];
    loading = true;
    try {
      const res = await api.chat(userText);
      messages = [...messages, { role: 'assistant', text: res.answer, citations: res.citations || [] }];
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

  function renderMd(text) {
    return marked.parse(text || '');
  }
</script>

<div class="chat-panel">
  <div class="presets">
    {#each PRESET_QUERIES as q}
      <button class="preset-btn" on:click={() => submit(q)} disabled={loading}>{q}</button>
    {/each}
  </div>

  <div class="history" bind:this={historyEl}>
    {#if messages.length === 0 && !loading}
      <div class="empty">Ask a question about the indexed corpus.</div>
    {/if}
    {#each messages as msg}
      {#if msg.role === 'user'}
        <div class="msg user-msg">{msg.text}</div>
      {:else}
        <div class="msg assistant-msg">
          <div class="md-body">{@html renderMd(msg.text)}</div>
          {#if msg.citations && msg.citations.length > 0}
            <div class="citations">
              <div class="cit-label">Sources</div>
              {#each msg.citations as c}
                <a class="cit" href={c.url} target="_blank" rel="noopener noreferrer">
                  <span class="cit-title">{c.title || c.domain}</span>
                  <span class="cit-domain">{c.domain}</span>
                </a>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    {/each}
    {#if loading}
      <div class="thinking">Searching corpus…</div>
    {/if}
    {#if error}
      <div class="error-msg">{error}</div>
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
  .chat-panel {
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
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .preset-btn {
    background: var(--surface-2);
    border: 1px solid var(--border-2);
    border-radius: 5px;
    color: var(--text-3);
    font-size: 0.68rem;
    padding: 5px 8px;
    text-align: left;
    cursor: pointer;
    line-height: 1.35;
    transition: background 0.1s, color 0.1s;
  }
  .preset-btn:hover:not(:disabled) { background: var(--surface); color: var(--text-2); }
  .preset-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .history {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .empty {
    font-size: 0.78rem;
    color: var(--text-5);
    text-align: center;
    padding: 2rem 0;
  }
  .thinking {
    font-size: 0.78rem;
    color: var(--accent);
    text-align: center;
    padding: 0.5rem 0;
  }
  .error-msg {
    font-size: 0.78rem;
    color: var(--err);
    padding: 4px 0;
  }

  .msg { max-width: 100%; }

  .user-msg {
    align-self: flex-end;
    background: var(--accent-t);
    border: 1px solid var(--accent);
    border-radius: 8px 8px 2px 8px;
    padding: 8px 12px;
    font-size: 0.82rem;
    color: var(--text-2);
    line-height: 1.5;
    max-width: 85%;
  }

  .assistant-msg {
    align-self: flex-start;
    width: 100%;
  }

  /* Markdown output styles */
  .md-body {
    font-size: 0.82rem;
    color: var(--text-2);
    line-height: 1.65;
  }
  :global(.md-body h1),
  :global(.md-body h2),
  :global(.md-body h3) {
    color: var(--text);
    font-weight: 600;
    margin: 0.75em 0 0.35em;
    line-height: 1.3;
  }
  :global(.md-body h1) { font-size: 1rem; }
  :global(.md-body h2) { font-size: 0.92rem; }
  :global(.md-body h3) { font-size: 0.86rem; }
  :global(.md-body p) { margin: 0 0 0.6em; }
  :global(.md-body p:last-child) { margin-bottom: 0; }
  :global(.md-body ul),
  :global(.md-body ol) {
    margin: 0 0 0.6em 1.2em;
    padding: 0;
  }
  :global(.md-body li) { margin-bottom: 0.25em; }
  :global(.md-body strong) { color: var(--text); font-weight: 600; }
  :global(.md-body em) { color: var(--text-3); font-style: italic; }
  :global(.md-body code) {
    background: var(--surface-2);
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 0.78rem;
    font-family: monospace;
    color: var(--accent);
  }
  :global(.md-body blockquote) {
    border-left: 3px solid var(--border-3);
    margin: 0 0 0.6em;
    padding: 0 0 0 10px;
    color: var(--text-3);
  }
  :global(.md-body a) { color: var(--accent); text-decoration: none; }
  :global(.md-body a:hover) { text-decoration: underline; }
  :global(.md-body hr) { border: none; border-top: 1px solid var(--border); margin: 0.8em 0; }

  .citations {
    margin-top: 10px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .cit-label {
    font-size: 0.62rem;
    color: var(--text-5);
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
    border-bottom: 1px solid var(--border);
  }
  .cit:last-child { border-bottom: none; }
  .cit:hover .cit-title { color: var(--accent); }
  .cit-title {
    font-size: 0.72rem;
    color: var(--text-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    transition: color 0.1s;
  }
  .cit-domain {
    font-size: 0.65rem;
    color: var(--text-5);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .input-row {
    display: flex;
    gap: 6px;
    padding: 8px;
    border-top: 1px solid var(--border);
    flex-shrink: 0;
    align-items: flex-end;
    background: var(--bg);
  }
  textarea {
    flex: 1;
    background: var(--surface-2);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    color: var(--text);
    font-size: 0.8rem;
    padding: 7px 10px;
    resize: none;
    font-family: inherit;
    line-height: 1.4;
    outline: none;
    transition: border-color 0.15s;
  }
  textarea:focus { border-color: var(--accent); }
  textarea::placeholder { color: var(--text-5); }
  textarea:disabled { opacity: 0.5; }
  .send {
    background: var(--accent);
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
  .send:hover:not(:disabled) { background: var(--accent-h); }
  .send:disabled { background: var(--border-3); color: var(--text-5); cursor: not-allowed; }
</style>
