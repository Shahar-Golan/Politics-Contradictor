import { useState, useRef, useEffect } from 'react';
import { chatAPI } from '../services/api';
import FlowChart from './FlowChart';
import SpeakerProfile from './SpeakerProfile';
import './ChatInterface.css';

function parseResponse(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/## (.*?)(\n|<br)/g, '<h3 class="resp-heading">$1</h3>$2')
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="inline-link">$1</a>')
    .replace(/\n/g, '<br/>');
}

function getTweetSourceUrl(tweet) {
  const meta = tweet?.metadata || {};

  const candidateKeys = [
    'tweet_url',
    'url',
    'link',
    'source_url',
    'permalink',
    'tweet_link',
  ];

  for (const key of candidateKeys) {
    const value = meta[key];
    if (typeof value === 'string' && /^https?:\/\//i.test(value.trim())) {
      return value.trim();
    }
  }

  const text = meta?.text || '';
  const match = text.match(/https?:\/\/[^\s<>")]+/i);
  return match ? match[0] : null;
}

function ChatInterface() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState(null);
  const [agentData, setAgentData] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [mode, setMode] = useState('graph');
  const [streamNode, setStreamNode] = useState(null);
  const [streamText, setStreamText] = useState('');
  const [nodeOutputs, setNodeOutputs] = useState({});
  const [liveEvents, setLiveEvents] = useState([]);
  const [showProfiles, setShowProfiles] = useState(false);
  const liveFeedRef = useRef(null);

  // Auto-scroll live feed
  useEffect(() => {
    if (liveFeedRef.current) {
      liveFeedRef.current.scrollTop = liveFeedRef.current.scrollHeight;
    }
  }, [streamText, liveEvents]);

  if (showProfiles) {
    return <SpeakerProfile onBack={() => setShowProfiles(false)} />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setAgentData(null);
    setGraphData(null);
    setResponse(null);
    setDone(false);
    setStreamNode(null);
    setStreamText('');
    setNodeOutputs({});
    setLiveEvents([]);

    try {
      if (mode === 'graph') {
        await chatAPI.streamGraphQuery(question, (event) => {
          if (event.type === 'node_start') {
            setStreamNode(prev => {
              // Save previous node's output before switching
              if (prev) {
                setStreamText(currentText => {
                  if (currentText) {
                    setNodeOutputs(outputs => ({ ...outputs, [prev]: currentText }));
                  }
                  return '';
                });
              }
              return event.node;
            });
            setLiveEvents(prev => [...prev, { type: 'node', node: event.node, status: 'start' }]);
          } else if (event.type === 'node_end') {
            // Save this node's output on end
            setStreamText(currentText => {
              if (currentText && event.node) {
                setNodeOutputs(outputs => ({ ...outputs, [event.node]: currentText }));
              }
              return currentText;
            });
            setLiveEvents(prev => [...prev, { type: 'node', node: event.node, status: 'end', data: event.data }]);
            if (event.node === 'router' && event.data) {
              setGraphData(prev => ({ ...prev, route: event.data.route, route_reason: event.data.reason }));
            }
          } else if (event.type === 'token') {
            setStreamText(prev => prev + event.content);
          } else if (event.type === 'done') {
            setGraphData(event.data);
            setResponse(event.data.answer);
            setStreamNode(null);
          }
        });
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
      setDone(true);
    }
  };

  const modeDescriptions = {
    graph: 'Routes your query to the best agent: tweets, news, or both',
    agent: 'ReAct agent with multi-step reasoning over tweets',
    simple: 'Direct vector search over tweets with LLM synthesis',
  };

  const nodeLabels = {
    page_lookup: 'Page Lookup',
    router: 'Router',
    tweet_agent: 'Tweet Agent',
    news_agent: 'News Agent',
    both: 'Both Agents',
  };

  return (
    <div className="app-layout">
      {/* ── Left Sidebar ── */}
      <aside className="sidebar sidebar-left">
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

        {/* Graph metadata */}
        {graphData && graphData.route && (
          <div className="sidebar-section">
            <label className="sidebar-label">Routing</label>
            <div className="meta-card">
              <div className="meta-row">
                <span className="meta-key">Route</span>
                <span className={`meta-badge badge-${graphData.route}`}>{graphData.route}</span>
              </div>
              {graphData.agent_used && (
                <div className="meta-row">
                  <span className="meta-key">Agent</span>
                  <span className="meta-value">{graphData.agent_used}</span>
                </div>
              )}
              {graphData.tweets && (
                <div className="meta-row">
                  <span className="meta-key">Tweets</span>
                  <span className="meta-value">{graphData.tweets.length}</span>
                </div>
              )}
              {graphData.articles && (
                <div className="meta-row">
                  <span className="meta-key">Articles</span>
                  <span className="meta-value">{graphData.articles.length}</span>
                </div>
              )}
            </div>
            {graphData.route_reason && (
              <p className="route-reason">{graphData.route_reason}</p>
            )}
          </div>
        )}

        {/* Agent metadata */}
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

        <div className="sidebar-section">
          <button className="profiles-btn" onClick={() => setShowProfiles(true)}>
            Speaker Profiles
          </button>
        </div>

        <div className="sidebar-footer">
          <a href="/api/stats" target="_blank" rel="noopener noreferrer" className="status-link">
            System Status
          </a>
        </div>
      </aside>

      {/* ── Main Content ── */}
      <main className="main-content">
        <div className="chat-area">
          <div className="response-area">
            {/* Empty state */}
            {!loading && !response && !done && (
              <div className="empty-state">
                <h2>Ask anything about political figures</h2>
                <div className="example-queries">
                  {[
                    "What does Hilary Clinton opinion about nuclear weapon?",
                    "What does Donald Trump's policy about immigration in the United States?",
                    "What is Barack Obama's opinion on healthcare reform?",
                    "What does Elon Musk say about space exploration and life on Mars?"
                  ].map((q) => (
                    <button
                      key={q}
                      className="example-btn"
                      onClick={() => setQuestion(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Loading state for non-graph modes */}
            {loading && mode !== 'graph' && (
              <div className="loading-state">
                <div className="loading-spinner" />
                <p>{mode === 'agent' ? 'Agent is reasoning...' : 'Searching and generating...'}</p>
              </div>
            )}

            {/* Final response */}
            {!loading && response && (
              <div className="response-cards">
                <div className="response-card">
                  <div className="card-header">
                    <span className={`card-badge badge-${mode}`}>
                      {mode === 'graph' ? (graphData?.agent_used || 'Graph') : mode === 'agent' ? 'Agent' : 'RAG'}
                    </span>
                    <span className="card-label">Answer</span>
                  </div>
                  <div
                    className="card-body response-text"
                    dangerouslySetInnerHTML={{ __html: parseResponse(response) }}
                  />
                </div>

                {/* Source tweets card */}
                {graphData?.tweets?.length > 0 && (
                  <div className="response-card sources-card">
                    <div className="card-header">
                      <span className="card-badge badge-tweet_agent">Tweets</span>
                      <span className="card-label">{graphData.tweets.length} sources</span>
                    </div>
                    <div className="card-body">
                      {graphData.tweets.map((t, i) => (
                        (() => {
                          const tweetUrl = getTweetSourceUrl(t);
                          return (
                            <div key={i} className="source-item tweet-item">
                              <div className="source-item-header">
                                <strong>{t.metadata?.author_name || 'Unknown'}</strong>
                                <span className="source-date">{t.metadata?.created_at || ''}</span>
                              </div>
                              <p>{t.metadata?.text || ''}</p>
                              {tweetUrl && (
                                <a href={tweetUrl} target="_blank" rel="noopener noreferrer" className="source-link">
                                  Open source link
                                </a>
                              )}
                            </div>
                          );
                        })()
                      ))}
                    </div>
                  </div>
                )}

                {/* Source articles card */}
                {graphData?.articles?.length > 0 && (
                  <div className="response-card sources-card">
                    <div className="card-header">
                      <span className="card-badge badge-news_agent">Articles</span>
                      <span className="card-label">{graphData.articles.length} sources</span>
                    </div>
                    <div className="card-body">
                      {graphData.articles.map((a, i) => (
                        <div key={i} className="source-item article-item">
                          <div className="source-item-header">
                            <strong>{a.metadata?.title || 'Untitled'}</strong>
                            <span className="source-date">{a.metadata?.date || ''}</span>
                          </div>
                          <div className="source-item-meta">
                            {a.metadata?.media_name && <span>{a.metadata.media_name}</span>}
                            {a.metadata?.state && <span>{a.metadata.state}</span>}
                          </div>
                          {a.metadata?.text && (
                            <p>{a.metadata.text.substring(0, 250)}...</p>
                          )}
                          {a.metadata?.link && (
                            <a href={a.metadata.link} target="_blank" rel="noopener noreferrer" className="source-link">
                              View article
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Agent reasoning card */}
                {agentData?.thought_process?.length > 0 && (
                  <div className="response-card">
                    <div className="card-header">
                      <span className="card-badge badge-agent">Reasoning</span>
                      <span className="card-label">{agentData.thought_process.length} steps</span>
                    </div>
                    <div className="card-body">
                      <ol className="reasoning-list">
                        {agentData.thought_process.map((thought, i) => (
                          <li key={i}>{thought}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Input bar */}
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

      {/* ── Right Sidebar ── */}
      <aside className="sidebar sidebar-right">
        <div className="sidebar-section">
          <label className="sidebar-label">Pipeline</label>
          <FlowChart
            mode={mode}
            loading={loading}
            done={done}
            graphData={graphData}
            agentData={agentData}
            streamNode={streamNode}
          />
        </div>

        {/* Live feed */}
        {(loading || liveEvents.length > 0) && mode === 'graph' && (
          <div className="sidebar-section live-feed-section">
            <label className="sidebar-label">Live Feed</label>
            <div className="live-feed" ref={liveFeedRef}>
              {liveEvents.map((ev, i) => (
                <div key={i} className={`live-event ${ev.status}`}>
                  {ev.type === 'node' && ev.status === 'start' && (
                    <span><span className="live-dot starting">&#9679;</span> {nodeLabels[ev.node] || ev.node}</span>
                  )}
                  {ev.type === 'node' && ev.status === 'end' && (
                    <>
                      <span><span className="live-dot ended">&#9679;</span> {nodeLabels[ev.node] || ev.node} done</span>
                      {ev.data?.route && (
                        <span className="live-route">&#8594; {ev.data.route}</span>
                      )}
                    </>
                  )}
                </div>
              ))}
              {streamNode && (
                <div className="live-event active-stream">
                  <span className="live-dot streaming">&#9679;</span>
                  {nodeLabels[streamNode] || streamNode} generating...
                </div>
              )}
              {done && (
                <div className="live-event completed">
                  <span className="live-dot ended">&#9679;</span> Complete
                </div>
              )}
            </div>
          </div>
        )}

        {/* Node outputs — completed + live */}
        {mode === 'graph' && (Object.keys(nodeOutputs).length > 0 || (streamNode && streamText)) && (
          <div className="sidebar-section live-tokens-section">
            <label className="sidebar-label">Model Output</label>
            <div className="live-tokens" ref={liveFeedRef}>
              {/* Previous node outputs */}
              {Object.entries(nodeOutputs).map(([node, text]) => (
                <div key={node} className="node-output-block">
                  <div className="node-output-label">{nodeLabels[node] || node}</div>
                  <div className="node-output-text">{text}</div>
                </div>
              ))}
              {/* Current streaming node */}
              {streamNode && streamText && (
                <div className="node-output-block active">
                  <div className="node-output-label">{nodeLabels[streamNode] || streamNode}</div>
                  <div className="node-output-text">
                    {streamText}
                    <span className="token-cursor">|</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

export default ChatInterface;
