# TED System - RAG-Based TED Talk Assistant

A Retrieval-Augmented Generation (RAG) system that allows users to ask questions and get recommendations about TED Talks.  The system uses Pinecone for vector storage, OpenAI for embeddings and language generation, and Flask for serving a web API with an integrated chat interface. 

🔗 **Live Demo**: [https://ted-system.vercel.app](https://ted-system.vercel.app)

## 🌟 Features

- **Intelligent Search**: Semantic search through thousands of TED Talk transcripts using vector embeddings
- **RAG Architecture**: Retrieves relevant TED Talk context and generates accurate, contextual answers
- **Deduplication**: Ensures diverse results by returning distinct TED Talks
- **Interactive UI**: Clean web interface for asking questions and getting instant responses
- **API Endpoints**: RESTful API for programmatic access
- **Balanced Chunking**: Smart text chunking algorithm that creates optimal-sized segments with overlap

## 🏗️ Architecture

The system follows a classic RAG pipeline:

1. **Data Preparation** (`src/prep_data.py`)
   - Loads TED Talk data from CSV
   - Splits transcripts into balanced chunks (1024 tokens with 20% overlap)
   - Generates embeddings using OpenAI's text-embedding-3-small model
   - Stores vectors in Pinecone with metadata

2. **Query Processing** (`api/index.py`)
   - Embeds user questions using the same embedding model
   - Retrieves top-K similar chunks from Pinecone
   - Deduplicates results to ensure unique TED Talks
   - Augments prompt with retrieved context
   - Generates response using GPT model

3. **Response Generation**
   - Uses retrieved transcripts as context
   - Generates answers strictly based on provided TED Talk data
   - Returns structured JSON with response, context, and augmented prompt

## 📁 Project Structure

```
TED_system/
├── api/
│   ├── index.py              # Flask API with RAG endpoint and chat UI
│   └── test_request.py       # API testing utility
├── src/
│   └── prep_data.py          # Data processing and vector upload
├── data/
│   └── ted_talks_en.csv      # TED Talk dataset (not included)
├── analyze_csv.py            # Dataset analysis utility
├── check_transcript_length.py # Transcript length checker
├── delete_all_vectors.py     # Pinecone cleanup utility
├── requirements.txt          # Python dependencies
├── vercel.json              # Vercel deployment configuration
└── . env                     # Environment variables (not included)
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Pinecone account and API key
- OpenAI API key
- TED Talks dataset (CSV format)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Shahar-Golan/TED_system.git
   cd TED_system
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   PINECONE_API_KEY=your_pinecone_api_key
   OPENAI_API_KEY=your_openai_api_key
   PINECONE_INDEX_NAME=ted-rag
   ```

4. **Prepare the data**
   
   Place your `ted_talks_en.csv` file in the `data/` directory, then run:
   ```bash
   python src/prep_data.py
   ```

5. **Run the application**
   ```bash
   python api/index.py
   ```
   
   The app will be available at `http://localhost:3000`

## 🔧 Configuration

Key parameters in `api/index.py`:

- `EMBEDDING_MODEL`: OpenAI embedding model (text-embedding-3-small)
- `GPT_MODEL`: Language model for response generation (gpt-5-mini)
- `TOP_K`: Number of chunks to retrieve (10)
- `CHUNK_SIZE`: Token size for text chunks (1024)
- `OVERLAP`: Overlap ratio between chunks (0.2 / 20%)

## 📡 API Endpoints

### `GET /`
Renders the interactive chat UI

### `GET /api/stats`
Returns system configuration parameters
```json
{
  "chunk_size": 1024,
  "overlap_ratio": 0.2,
  "top_k": 10
}
```

### `POST /api/prompt`
Main RAG endpoint for question answering

**Request:**
```json
{
  "question": "Recommend a talk on climate change"
}
```

**Response:**
```json
{
  "response": "Based on the TED data, I recommend.. .",
  "context": [
    {
      "talk_id": "123",
      "title": "Talk Title",
      "speakers": "Speaker Name",
      "chunk":  "Relevant transcript excerpt...",
      "score": 0.85
    }
  ],
  "Augmented_prompt": {
    "System": "System prompt.. .",
    "User": "Context and question..."
  }
}
```

## 🛠️ Utilities

### Analyze Dataset
```bash
python analyze_csv.py
```
Provides comprehensive statistics about the TED Talks dataset including word counts, views, and transcript analysis.

### Check Transcript Length
```bash
python check_transcript_length.py
```
Analyzes transcript lengths to optimize chunking parameters.

### Delete All Vectors
```bash
python delete_all_vectors.py
```
Clears all vectors from the Pinecone index (use with caution! ).

## 🧪 Testing

Test the API endpoint: 
```bash
python api/test_request.py
```

## 🌐 Deployment

The application is configured for deployment on Vercel.  The `vercel.json` file contains the necessary configuration. 

To deploy:
1. Install Vercel CLI:  `npm i -g vercel`
2. Run:  `vercel`
3. Set environment variables in Vercel dashboard

## 🔒 System Constraints

The assistant operates under strict constraints:
- Answers are **strictly based on the TED Talk dataset**
- No external knowledge or internet data is used
- If information is not in the provided context, responds:  "I don't know based on the provided TED data."
- Always cites or references the relevant TED Talk transcripts

## 📊 Dataset Requirements

The system expects a CSV file with the following columns:
- `talk_id`: Unique identifier
- `title`: Talk title
- `speaker_1`: Primary speaker
- `all_speakers`: All speakers (dictionary format)
- `transcript`: Full transcript text
- Additional metadata columns (views, etc.)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is open source and available for educational and research purposes.

## 👤 Author

**Shahar Golan** - [GitHub Profile](https://github.com/Shahar-Golan)

## 🙏 Acknowledgments

- TED Talks for the dataset
- OpenAI for embedding and language models
- Pinecone for vector storage infrastructure
- Flask for the web framework

---

**Note**: Make sure to add your TED Talks dataset to the `data/` directory and configure your API keys in the `.env` file before running the application. 