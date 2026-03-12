import { useState } from 'react';
import { chatAPI } from '../services/api';
import './ChatInterface.css';

function parseResponse(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/## (.*?)(\n|<br)/g, '<h3 class="resp-heading">$1</h3>$2')
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="inline-link">$1</a>')
    .replace(/\n/g, '<br/>');
}

function ChatInterface() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState(null);
  const [agentData, setAgentData] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('graph');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setAgentData(null);
    setGraphData(null);
    setResponse(null);

    try {
      if (mode === 'graph') {
        const data = await chatAPI.sendGraphQuery(question);
        setResponse(data.answer);
        setGraphData(data);
      } else if (mode === 'agent') {
        const data = await chatAPI.sendAgentQuery(question);
        setResponse(data.answer);
        setAgentData(data);
      } else {
        const data = await chatAPI.sendQuestion(question);
        setResponse(data.response);
      }
    } catch (error) {
      setResponse('Error: Could not connect to the API.');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const modeDescriptions = {
    graph: 'Routes your query to the best agent: tweets, news, or both',
    agent: 'ReAct agent with multi-step reasoning over tweets',
    simple: 'Direct vector search over tweets with LLM synthesis',
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Politics Contradictor</h1>
          <p className="sidebar-subtitle">Multi-agent political intelligence</p>
        </div>

        <div className="sidebar-section">
          <label className="sidebar-label">Mode</label>
          <div className="mode-buttons">
            <button
              className={`mode-btn ${mode === 'graph' ? 'active' : ''}`}
              onClick={() => setMode('graph')}
            >
              <span className="mode-icon">G</span>
              <span>Graph</span>
            </button>
            <button
              className={`mode-btn ${mode === 'agent' ? 'active' : ''}`}
              onClick={() => setMode('agent')}
            >
              <span className="mode-icon">A</span>
              <span>Agent</span>
            </button>
            <button
              className={`mode-btn ${mode === 'simple' ? 'active' : ''}`}
              onClick={() => setMode('simple')}
            >
              <span className="mode-icon">R</span>
              <span>RAG</span>
            </button>
          </div>
          <p className="mode-description">{modeDescriptions[mode]}</p>
        </div>

        {/* Graph metadata in sidebar */}
        {graphData && (
          <div className="sidebar-section">
            <label className="sidebar-label">Routing</label>
            <div className="meta-card">
              <div className="meta-row">
                <span className="meta-key">Route</span>
                <span className={`meta-badge badge-${graphData.route}`}>{graphData.route}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">Agent</span>
                <span className="meta-value">{graphData.agent_used}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">Tweets</span>
                <span className="meta-value">{graphData.tweets?.length || 0}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">Articles</span>
                <span className="meta-value">{graphData.articles?.length || 0}</span>
              </div>
            </div>
            {graphData.route_reason && (
              <p className="route-reason">{graphData.route_reason}</p>
            )}
          </div>
        )}

        {/* Agent metadata in sidebar */}
        {agentData && (
          <div className="sidebar-section">
            <label className="sidebar-label">Agent Info</label>
            <div className="meta-card">
              <div className="meta-row">
                <span className="meta-key">Mode</span>
                <span className="meta-value">{agentData.mode}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">Iterations</span>
                <span className="meta-value">{agentData.iterations}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">Tweets</span>
                <span className="meta-value">{agentData.tweets_found}</span>
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-footer">
          <a href="/api/stats" target="_blank" rel="noopener noreferrer" className="status-link">
            System Status
          </a>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        <div className="chat-area">
          {/* Response area */}
          <div className="response-area">
            {loading && (
              <div className="loading-state">
                <div className="loading-spinner" />
                <p>
                  {mode === 'graph' && 'Routing through multi-agent graph...'}
                  {mode === 'agent' && 'Agent is reasoning...'}
                  {mode === 'simple' && 'Searching and generating...'}
                </p>
              </div>
            )}

            {!loading && !response && (
              <div className="empty-state">
                <h2>Ask anything about political figures</h2>
                <div className="example-queries">
                  {[
                    'What did Trump say about Biden?',
                    'How did newspapers cover Obama\'s healthcare policy?',
                    'Compare Trump\'s tweets about tariffs with news coverage',
                  ].map((q) => (
                    <button
                      key={q}
                      className="example-btn"
                      onClick={() => { setQuestion(q); }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {!loading && response && (
              <div className="response-content">
                <div
                  className="response-text"
                  dangerouslySetInnerHTML={{ __html: parseResponse(response) }}
                />

                {/* Source tweets */}
                {graphData?.tweets?.length > 0 && (
                  <details className="sources-section">
                    <summary>Source Tweets ({graphData.tweets.length})</summary>
                    <div className="sources-list">
                      {graphData.tweets.map((t, i) => (
                        <div key={i} className="source-card tweet-card">
                          <div className="source-header">
                            <strong>{t.metadata?.author_name || 'Unknown'}</strong>
                            <span className="source-date">{t.metadata?.created_at || ''}</span>
                          </div>
                          <p className="source-text">{t.metadata?.text || ''}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Source articles */}
                {graphData?.articles?.length > 0 && (
                  <details className="sources-section">
                    <summary>Source Articles ({graphData.articles.length})</summary>
                    <div className="sources-list">
                      {graphData.articles.map((a, i) => (
                        <div key={i} className="source-card article-card">
                          <div className="source-header">
                            <strong>{a.metadata?.title || 'Untitled'}</strong>
                            <span className="source-date">{a.metadata?.date || ''}</span>
                          </div>
                          <div className="article-meta">
                            {a.metadata?.media_name && <span>{a.metadata.media_name}</span>}
                            {a.metadata?.state && <span>{a.metadata.state}</span>}
                            {a.metadata?.media_type && <span>{a.metadata.media_type}</span>}
                          </div>
                          {a.metadata?.text && (
                            <p className="source-text">{a.metadata.text.substring(0, 300)}...</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Agent reasoning */}
                {agentData?.thought_process?.length > 0 && (
                  <details className="sources-section">
                    <summary>Agent Reasoning ({agentData.thought_process.length} steps)</summary>
                    <ol className="reasoning-list">
                      {agentData.thought_process.map((thought, i) => (
                        <li key={i}>{thought}</li>
                      ))}
                    </ol>
                  </details>
                )}

                {agentData?.actions_taken?.length > 0 && (
                  <details className="sources-section">
                    <summary>Actions Taken ({agentData.actions_taken.length})</summary>
                    <ul className="actions-list">
                      {agentData.actions_taken.map((action, i) => (
                        <li key={i}>
                          <strong>{action.tool}</strong>: {action.reason}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="input-bar">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about political figures..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !question.trim()}>
              {loading ? 'Thinking...' : 'Send'}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

export default ChatInterface;
