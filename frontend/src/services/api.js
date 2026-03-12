import axios from 'axios';

const API_BASE_URL = import.meta.env.MODE === 'production' 
  ? '/api' 
  : 'http://localhost:5000/api';

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

  async getStats() {
    const response = await axios.get(`${API_BASE_URL}/stats`);
    return response.data;
  }
};
