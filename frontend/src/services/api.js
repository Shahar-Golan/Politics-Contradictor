import axios from 'axios';

const API_BASE_URL = import.meta.env.MODE === 'production' 
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
