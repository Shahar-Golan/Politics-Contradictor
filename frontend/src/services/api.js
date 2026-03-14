import axios from 'axios';

const API_BASE_URL = '/api';

export const chatAPI = {
  async sendQuestion(question) {
    const response = await axios.post(`${API_BASE_URL}/prompt`, { question });
    return response.data;
  },

  async sendAgentQuery(query) {
    const response = await axios.post(`${API_BASE_URL}/agent/query`, { query });
    return response.data;
  },

  async sendGraphQuery(query) {
    const response = await axios.post(`${API_BASE_URL}/v2/query`, { query });
    return response.data;
  },

  streamGraphQuery(query, onEvent) {
    return new Promise((resolve, reject) => {
      fetch(`${API_BASE_URL}/v2/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })
        .then((response) => {
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          function read() {
            reader.read().then(({ done, value }) => {
              if (done) {
                resolve();
                return;
              }
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop();
              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  try {
                    const event = JSON.parse(line.slice(6));
                    onEvent(event);
                    if (event.type === 'done') {
                      resolve(event.data);
                      return;
                    }
                  } catch (e) {
                    // skip malformed JSON
                  }
                }
              }
              read();
            }).catch(reject);
          }
          read();
        })
        .catch(reject);
    });
  },

  async getStats() {
    const response = await axios.get(`${API_BASE_URL}/stats`);
    return response.data;
  },

  async getSpeakers() {
    const response = await axios.get(`${API_BASE_URL}/speakers`);
    return response.data;
  },

  async getSpeakerProfile(speakerId) {
    const response = await axios.get(`${API_BASE_URL}/speakers/${speakerId}`);
    return response.data;
  }
};
