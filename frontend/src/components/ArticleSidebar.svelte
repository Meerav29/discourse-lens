<script>
  import { api } from '../lib/api.js';

  export let articleId = null;
  export let onClose = () => {};

  let article = null;
  let loading = false;
  let error = null;

  $: if (articleId) {
    loadArticle(articleId);
  } else {
    article = null;
    error = null;
  }

  async function loadArticle(id) {
    loading = true;
    error = null;
    article = null;
    try {
      article = await api.getArticle(id);
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  $: excerpt = article?.raw_text
    ? article.raw_text.slice(0, 800).replace(/\s+/g, ' ').trim()
    : null;
</script>

<div class="backdrop" class:visible={articleId != null} on:click={onClose} role="presentation"></div>

<aside class="drawer" class:open={articleId != null}>
  <button class="close" on:click={onClose} aria-label="Close">✕</button>

  {#if loading}
    <div class="state">Loading…</div>
  {:else if error}
    <div class="state error">Failed to load article: {error}</div>
  {:else if article}
    <div class="content">
      <div class="meta">
        <span class="domain">{article.domain || 'unknown'}</span>
        {#if article.publish_date}
          <span class="dot">·</span>
          <span class="date">{article.publish_date}</span>
        {/if}
        {#if article.word_count}
          <span class="dot">·</span>
          <span class="wc">{article.word_count.toLocaleString()} words</span>
        {/if}
      </div>
      <h2 class="title">{article.title || 'Untitled'}</h2>
      {#if excerpt}
        <p class="excerpt">{excerpt}{article.raw_text?.length > 800 ? '…' : ''}</p>
      {/if}
      {#if article.url}
        <a class="link" href={article.url} target="_blank" rel="noopener noreferrer">
          Read full article →
        </a>
      {/if}
    </div>
  {:else}
    <div class="state">No article selected.</div>
  {/if}
</aside>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 200;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;
  }
  .backdrop.visible {
    opacity: 1;
    pointer-events: auto;
  }
  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    width: 420px;
    max-width: 92vw;
    height: 100vh;
    background: var(--surface-3);
    border-left: 1px solid var(--border-2);
    z-index: 210;
    transform: translateX(100%);
    transition: transform 0.22s cubic-bezier(0.4,0,0.2,1);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .drawer.open {
    transform: translateX(0);
  }
  .close {
    position: sticky;
    top: 0;
    align-self: flex-end;
    background: none;
    border: none;
    color: var(--text-4);
    font-size: 1rem;
    cursor: pointer;
    padding: 14px 16px;
    line-height: 1;
    z-index: 1;
  }
  .close:hover { color: var(--text); }
  .content {
    padding: 0 24px 32px;
    flex: 1;
  }
  .state {
    padding: 3rem 24px;
    color: var(--text-5);
    font-size: 0.85rem;
  }
  .state.error { color: var(--err); }
  .meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .domain {
    font-size: 0.72rem;
    color: var(--accent);
    font-weight: 600;
  }
  .dot { color: var(--text-6); font-size: 0.72rem; }
  .date, .wc {
    font-size: 0.72rem;
    color: var(--text-4);
  }
  .title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text);
    line-height: 1.4;
    margin: 0 0 14px;
  }
  .excerpt {
    font-size: 0.83rem;
    color: var(--text-3);
    line-height: 1.65;
    margin: 0 0 20px;
  }
  .link {
    display: inline-block;
    font-size: 0.82rem;
    color: var(--accent);
    text-decoration: none;
    border: 1px solid var(--border-2);
    border-radius: 6px;
    padding: 7px 14px;
    transition: background 0.15s, border-color 0.15s;
  }
  .link:hover {
    background: var(--surface-2);
    border-color: var(--accent);
  }
</style>
