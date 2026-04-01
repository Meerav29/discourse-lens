<script>
  let topic = '';

  function handleSubmit() {
    if (!topic.trim()) return;
    console.log('Starting ingestion for topic:', topic);
    // Logic wired up in Stage 1
  }
</script>

<main>
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
      />
      <button type="submit" disabled={!topic.trim()}>
        Analyze Discourse
      </button>
    </form>
  </section>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: #0f0f13;
    color: #e8e8f0;
  }

  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 4rem 2rem;
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

  input {
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

  input:focus {
    border-color: #5a7fff;
  }

  input::placeholder {
    color: #555;
  }

  button {
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

  button:hover:not(:disabled) {
    background: #7090ff;
  }

  button:disabled {
    background: #2e2e40;
    color: #555;
    cursor: not-allowed;
  }
</style>
