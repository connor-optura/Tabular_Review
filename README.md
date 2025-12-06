
# Tabular Review for Bulk Document Analysis

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![React](https://img.shields.io/badge/framework-React-61DAFB.svg)
![AI](https://img.shields.io/badge/AI-Anthropic%20Claude-191919.svg)

An AI-powered document review workspace that transforms unstructured legal contracts into structured, queryable datasets. Designed for legal professionals, auditors, and procurement teams to accelerate due diligence and contract analysis.

## 🚀 Features

- **AI-Powered Extraction**: Automatically extract key clauses, dates, amounts, and entities using Anthropic Claude models (Sonnet 4, 3.5 Sonnet, 3.5 Haiku).
- **RAG-Powered Retrieval**: Hybrid search combining semantic embeddings (BGE) + BM25 keyword matching with cross-encoder reranking for precise context retrieval.
- **High-Fidelity Conversion**: Uses **Docling** (running locally) to convert PDFs and DOCX files to clean Markdown text, preserving formatting and structure without hallucination.
- **Structured Outputs**: LiteLLM with Pydantic models ensures reliable JSON responses with confidence scores and source citations.
- **Dynamic Schema**: Define columns with natural language prompts (e.g., "What is the governing law?").
- **Verification & Citations**: Click any extracted cell to view the exact source quote highlighted in the original document.
- **Spreadsheet Interface**: A high-density, Excel-like grid for managing bulk document reviews.
- **Integrated Chat Analyst**: Ask questions across your entire dataset (e.g., "Which contract has the most favorable MFN clause?").

## 🎬 Demo

https://github.com/user-attachments/assets/b63026d8-3df6-48a8-bb4b-eb8f24d3a1ca

## 🛠 Tech Stack

- **Frontend**: React 19, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python 3.11+
- **LLM Integration**: [LiteLLM](https://github.com/BerriAI/litellm) (supports Anthropic, OpenAI, Gemini, and 100+ providers)
- **Document Processing**: [Docling](https://github.com/DS4SD/docling) for PDF/DOCX to Markdown conversion
- **RAG Stack**:
  - Embeddings: `BAAI/bge-small-en-v1.5` (sentence-transformers)
  - Keyword Search: BM25 (rank-bm25)
  - Reranking: `BAAI/bge-reranker-base` (cross-encoder)
- **Default Models**: Claude Sonnet 4, Claude 3.5 Sonnet, Claude 3.5 Haiku

## 📦 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/tabular-review.git
cd tabular-review
```

### 2. Setup Frontend
Install Node dependencies:
```bash
pnpm install
```

### 3. Setup Backend
The backend handles document conversion, RAG indexing, and LLM calls.

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure API Keys
Create a `.env` file in the project root:
```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

> **Note**: LiteLLM supports many providers. You can also use OpenAI, Google, or others by setting the appropriate environment variable and changing the model IDs. See [LiteLLM docs](https://docs.litellm.ai/docs/providers).

### 5. Run
Start the backend (in one terminal):
```bash
cd server
source venv/bin/activate
python main.py
```

Start the frontend (in another terminal):
```bash
pnpm dev
```

The app will be available at `http://localhost:3000`.

## 📄 Sample Documents

The repository includes 8 sample side letter agreements for testing. To export them as files:

```bash
node scripts/export_samples.cjs
```

This creates markdown files in `sample_documents/`.

## 🔧 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │DataGrid │  │Sidebar  │  │  Chat   │  │ Model Selector  │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘ │
└───────┼────────────┼────────────┼────────────────┼──────────┘
        │            │            │                │
        ▼            ▼            ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  Document Processing                  │   │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────────────────┐  │   │
│  │  │ Docling │→ │Chunking │→ │ Embeddings + BM25    │  │   │
│  │  │(PDF→MD) │  │         │  │ Index                │  │   │
│  │  └─────────┘  └─────────┘  └──────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  Extraction Pipeline                  │   │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────────────────┐  │   │
│  │  │ Hybrid  │→ │Reranker │→ │ LiteLLM + Structured │  │   │
│  │  │ Search  │  │         │  │ Outputs (Pydantic)   │  │   │
│  │  └─────────┘  └─────────┘  └──────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 🐳 Docker Deployment

You can also run the application using Docker:

1. **Setup environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your Anthropic API key
   ```

2. **Build and run with Docker**:
   ```bash
   docker-compose up --build
   ```

3. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000/docs

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/convert` | POST | Upload and convert a document (PDF/DOCX) to Markdown, indexes for RAG |
| `/extract` | POST | Extract data for a column using RAG retrieval + LLM |
| `/generate-prompt` | POST | AI-assisted prompt generation for columns |
| `/chat` | POST | Chat with extracted data across documents |
| `/models` | GET | List available LLM models |

## 🛡 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Disclaimer**: This tool is an AI assistant and should not be used as a substitute for professional legal advice. Always verify AI-generated results against the original documents.
