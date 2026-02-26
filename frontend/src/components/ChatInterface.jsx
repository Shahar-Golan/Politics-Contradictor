import { useState } from 'react';
import { chatAPI } from '../services/api';
import './ChatInterface.css';

function ChatInterface() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState('Ask questions about TED Talks...');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setResponse('Searching TED Talks and generating answer...');

    try {
      const data = await chatAPI.sendQuestion(question);
      setResponse(data.response);
    } catch (error) {
      setResponse('Error: Could not connect to the API.');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>TED Talk Assistant</h1>
      <div className="status">
        System status: <a href="/api/stats" target="_blank" rel="noopener noreferrer">Active</a>
      </div>
      <div className="chat-box">{response}</div>
      <form onSubmit={handleSubmit} className="input-group">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g., What are the best TED talks about AI?"
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
