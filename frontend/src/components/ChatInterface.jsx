import { useState } from 'react';
import { chatAPI } from '../services/api';
import './ChatInterface.css';

// Function to parse markdown and convert URLs to clickable links
function parseResponse(text) {
  if (!text) return '';
  
  let html = text
    // Convert **bold** to <strong>bold</strong>
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Convert URLs to clickable links
    .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="tweet-link">$1</a>')
    // Convert line breaks
    .replace(/\n/g, '<br/>');
  
  return html;
}

function ChatInterface() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState('Ask questions about political figures\' tweets...');
  const [agentData, setAgentData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [agentMode, setAgentMode] = useState(true);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setAgentData(null);
    setResponse(agentMode ? 'Agent is thinking and analyzing tweets...' : 'Searching tweets and generating answer...');

    try {
      if (agentMode) {
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

  return (
    <div className="container">
      <h1>Political Tweets Assistant</h1>
      <div className="status">
        System status: <a href="/api/stats" target="_blank" rel="noopener noreferrer">Active</a>
      </div>
      
      <div className="mode-toggle">
        <label>
          <input 
            type="checkbox" 
            checked={agentMode}
            onChange={(e) => setAgentMode(e.target.checked)}
          />
          <span className="toggle-label">
            {agentMode ? '🤖 Agent Mode (Intelligent)' : '📄 Simple RAG Mode'}
          </span>
        </label>
      </div>

      <div className="chat-box">
        <div 
          className="response-text" 
          dangerouslySetInnerHTML={{ __html: parseResponse(response) }}
        />
        
        {agentData && (
          <div className="agent-info">
            <div className="agent-stats">
              <span>Mode: {agentData.mode}</span>
              <span>Iterations: {agentData.iterations}</span>
              <span>Tweets: {agentData.tweets_found}</span>
            </div>
            
            {agentData.thought_process && agentData.thought_process.length > 0 && (
              <details className="reasoning-steps">
                <summary>🧠 Show Agent Reasoning ({agentData.thought_process.length} thoughts)</summary>
                <ol>
                  {agentData.thought_process.map((thought, i) => (
                    <li key={i}>{thought}</li>
                  ))}
                </ol>
              </details>
            )}
            
            {agentData.actions_taken && agentData.actions_taken.length > 0 && (
              <details className="actions-taken">
                <summary>⚙️ Actions Taken ({agentData.actions_taken.length})</summary>
                <ul>
                  {agentData.actions_taken.map((action, i) => (
                    <li key={i}>
                      <strong>{action.tool}</strong>: {action.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            
            {agentData.urls_analyzed && agentData.urls_analyzed.length > 0 && (
              <div className="sources-analyzed">
                <h4>🔗 Sources Analyzed:</h4>
                {agentData.urls_analyzed.map((source, i) => (
                  <div key={i} className="source-item">
                    <a href={source.url} target="_blank" rel="noopener noreferrer" className="source-link">
                      {source.title || source.url}
                    </a>
                    <div className="source-meta">
                      <span>📊 {source.word_count} words</span>
                      {source.statistics?.has_numbers && <span>📈 Contains statistics</span>}
                    </div>
                    {source.content_preview && (
                      <p className="source-preview">{source.content_preview}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      
      <form onSubmit={handleSubmit} className="input-group">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g., What did Obama say about healthcare?"
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Loading...' : 'Ask'}
        </button>
      </form>
    </div>
  );
}

export default ChatInterface;
