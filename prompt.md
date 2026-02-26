# React Migration Plan for TED System

## Overview
This document outlines the steps to migrate the TED System from a Flask-only application (with embedded HTML) to a modern React + Flask architecture, while keeping deployment on Vercel.

---

## Phase 1: Backend Preparation

### Step 1: Install Flask-CORS  - add it to requiments.txt and run it using .venv
```bash
pip install flask-cors
pip freeze > requirements.txt
```

### Step 2: Update Flask Backend (api/index.py)
- Import CORS: `from flask_cors import CORS`
- Add CORS configuration after app initialization:
  ```python
  app = Flask(__name__)
  CORS(app)
  ```
- Remove the `CHAT_UI_TEMPLATE` constant (entire HTML string)
- Remove or comment out the `@app.route('/')` home route
- Keep only API routes: `/api/stats` and `/api/prompt`

### Step 3: Test Backend API
- Run Flask locally: `python api/index.py`
- Test endpoints with curl or Postman:
  ```bash
  curl http://localhost:3000/api/stats
  curl -X POST http://localhost:3000/api/prompt -H "Content-Type: application/json" -d "{\"question\":\"test\"}"
  ```

---

## Phase 2: React Frontend Setup

### Step 4: Create React Application
Choose one option: - I chose Vite

**Option A: Vite (Recommended - Faster)**
```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
```c:/Users/golan/VisualStudioProjects/TED_system/.venv/Scripts/python.exe api/index.py

### Step 5: Install Dependencies
```bash
npm install axios
```

### Step 6: Create API Service (frontend/src/services/api.js)
```javascript
import axios from 'axios';

const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? '/api' 
  : 'http://localhost:3000/api';

export const chatAPI = {
  async sendQuestion(question) {
    const response = await axios.post(`${API_BASE_URL}/prompt`, { question });
    return response.data;
  },
  
  async getStats() {
    const response = await axios.get(`${API_BASE_URL}/stats`);
    return response.data;
  }
};
```

### Step 7: Create Chat Component (frontend/src/components/ChatInterface.jsx)
```javascript
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
```

### Step 8: Create Styles (frontend/src/components/ChatInterface.css)
```css
body {
  font-family: sans-serif;
  background-color: #f4f4f4;
  margin: 0;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.container {
  background: white;
  width: 100%;
  max-width: 700px;
  padding: 30px;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
}

h1 {
  color: #1da1f2;
  margin-top: 0;
}

.chat-box {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 15px;
  min-height: 200px;
  margin: 20px 0;
  background: #fafafa;
  white-space: pre-wrap;
  line-height: 1.5;
  color: #333;
}

.input-group {
  display: flex;
  gap: 10px;
}

.input-group input {
  flex: 1;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 16px;
}

.input-group button {
  background: #1da1f2;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
}

.input-group button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.status {
  font-size: 0.9em;
  color: #666;
  margin-bottom: 5px;
}

.status a {
  color: #1da1f2;
  text-decoration: none;
}

.status a:hover {
  text-decoration: underline;
}
```

### Step 9: Update App Component (frontend/src/App.jsx)
```javascript
import ChatInterface from './components/ChatInterface';
import './App.css';

function App() {
  return (
    <div className="App">
      <ChatInterface />
    </div>
  );
}

export default App;
```

### Step 10: Update App.css (frontend/src/App.css)
```css
.App {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
}
```

### Step 11: Test React App Locally
```bash
cd frontend
npm run dev  # if using Vite
# or
npm start    # if using Create React App
```

---

## Phase 3: Vercel Configuration

### Step 12: Update vercel.json
```json
{
  "builds": [
    {
      "src": "frontend/package.json",
      "use": "@vercel/static-build",
      "config": { "distDir": "dist" }
    }
  ],
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" },
    { "source": "/(.*)", "destination": "/frontend/index.html" }
  ]
}
```

### Step 13: Add Build Script to frontend/package.json
Add to the "scripts" section:
```json
"scripts": {
  "build": "vite build",
  "vercel-build": "npm run build"
}
```

### Step 14: Create .vercelignore (Optional)
```
.venv
__pycache__
*.pyc
.env
node_modules
.DS_Store
```

---

## Phase 4: Deployment

### Step 15: Update .gitignore
```
.env
.venv/
__pycache__/
*.pyc
node_modules/
frontend/dist/
frontend/build/
.vercel
```

### Step 16: Commit Changes
```bash
git add .
git commit -m "Migrate to React + Flask architecture"
git push
```

### Step 17: Deploy to Vercel
Vercel will automatically detect changes and deploy:
- Frontend: Static React files served from CDN
- Backend: Python API as serverless functions

### Step 18: Verify Deployment
- Test the live URL
- Check that API calls work
- Verify CORS is functioning
- Test on mobile devices

---

## Phase 5: Post-Migration (Optional Enhancements)

### Step 19: Add Environment Variables
**Frontend (.env.local):**
```
VITE_API_URL=http://localhost:3000/api
```

**Vercel Dashboard:**
- Add environment variables for production
- Update API keys if needed

### Step 20: Improve UI/UX
- Add loading spinner
- Add error boundary
- Add typing indicators
- Add conversation history
- Add dark mode toggle
- Add mobile responsiveness

### Step 21: Add Tests
```bash
npm install --save-dev @testing-library/react @testing-library/jest-dom
```

### Step 22: Add CI/CD (Optional)
- Set up GitHub Actions for automated testing
- Add PR preview deployments
- Add code quality checks (ESLint, Prettier)

---

## Rollback Plan

If issues occur, you can quickly rollback:

1. Restore the original `api/index.py` with embedded HTML template
2. Restore the original `vercel.json`
3. Remove the `frontend/` directory
4. Redeploy

---

## Testing Checklist

- [ ] Backend API responds to `/api/stats`
- [ ] Backend API responds to `/api/prompt` with valid JSON
- [ ] React app runs locally without errors
- [ ] React app can call backend API locally
- [ ] CORS headers are present in API responses
- [ ] Production build succeeds
- [ ] Vercel deployment succeeds
- [ ] Live site loads correctly
- [ ] Live site can query the API
- [ ] Mobile view works correctly
- [ ] Error handling works as expected

---

## Additional Resources

- [Vercel React Deployment](https://vercel.com/docs/frameworks/react)
- [Vercel Python Functions](https://vercel.com/docs/functions/serverless-functions/runtimes/python)
- [Flask-CORS Documentation](https://flask-cors.readthedocs.io/)
- [React + Vite Guide](https://vitejs.dev/guide/)

---

## Estimated Time
- Phase 1: 30 minutes
- Phase 2: 2-3 hours
- Phase 3: 30 minutes
- Phase 4: 30 minutes
- **Total: 4-5 hours**

---

## Notes
- Keep the original `api/index.py` backed up before making changes
- Test locally before deploying to production
- Consider creating a separate branch for this migration
- Document any API changes for future reference
