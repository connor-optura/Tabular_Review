from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any
from dotenv import load_dotenv
import tempfile
import os
import shutil
import litellm
import hashlib
import uuid
import numpy as np

# Import chunking module for RAG
from chunking import (
    chunk_document,
    generate_embeddings,
    retrieve_relevant_chunks,
    build_bm25_index,
    preload_models,
)

# Load environment variables from .env file (check both server/ and project root)
load_dotenv()  # Current directory
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))  # Project root

# Enable JSON schema validation for models that don't natively support it
litellm.enable_json_schema_validation = True

app = FastAPI()

# Configure CORS
# In production, replace with specific origins
origins = [
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize converter (this might take a moment to load models on startup)
converter = DocumentConverter()


# ============== Document Index (In-Memory RAG Store) ==============
# In production, use Redis or a vector database like Pinecone/Weaviate

document_index: Dict[str, Dict[str, Any]] = {}
extraction_cache: Dict[str, Dict[str, Any]] = {}


# Preload RAG models at startup for faster first request
@app.on_event("startup")
async def startup_event():
    """Preload embedding and reranking models."""
    print("Preloading RAG models...")
    preload_models()


def generate_doc_id(filename: str) -> str:
    """Generate a unique document ID."""
    return f"{uuid.uuid4().hex[:8]}_{filename.replace(' ', '_')[:20]}"


def get_cache_key(doc_id: str, column_prompt: str, model: str) -> str:
    """Generate cache key for extraction results."""
    return hashlib.md5(f"{doc_id}:{column_prompt}:{model}".encode()).hexdigest()


# ============== Pydantic Models ==============


# Response model for structured extraction output
class ExtractionResponse(BaseModel):
    """Structured response for data extraction from documents."""

    value: str = Field(description="The extracted answer, concise and direct")
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Confidence level of the extraction"
    )
    quote: str = Field(
        description="Verbatim text from the document supporting the answer"
    )
    page: int = Field(
        description="Page number where the information was found", default=1
    )
    reasoning: str = Field(
        description="Brief explanation of why this value was selected"
    )


class ExtractionRequest(BaseModel):
    document_text: Optional[str] = (
        None  # Full text fallback (for backwards compatibility)
    )
    doc_id: Optional[str] = None  # Document ID for RAG lookup
    column_name: str
    column_type: str
    prompt: str
    model: str = "anthropic/claude-sonnet-4-20250514"  # Default model


class PromptHelperRequest(BaseModel):
    name: str
    type: str
    current_prompt: Optional[str] = None
    model: str = "anthropic/claude-sonnet-4-20250514"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    data_context: str
    history: List[ChatMessage] = []
    model: str = "anthropic/claude-sonnet-4-20250514"


# ============== Document Conversion ==============


@app.post("/convert")
async def convert_document(file: UploadFile = File(...)):
    try:
        # Create a temporary file to save the uploaded content
        # Docling needs a file path
        suffix = os.path.splitext(file.filename)[1]
        if not suffix:
            suffix = ""

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        try:
            # Convert the document
            result = converter.convert(tmp_path)
            # Export to markdown
            markdown_content = result.document.export_to_markdown()

            # === RAG INDEXING ===
            # Generate unique document ID
            doc_id = generate_doc_id(file.filename or "document")

            # Chunk the document
            chunks = chunk_document(markdown_content)

            # Generate embeddings for all chunks
            embeddings = generate_embeddings(chunks)

            # Build BM25 index for keyword search
            bm25_index = build_bm25_index(chunks)

            # Store in document index
            document_index[doc_id] = {
                "chunks": chunks,
                "embeddings": embeddings,
                "bm25_index": bm25_index,
                "markdown": markdown_content,
                "filename": file.filename,
            }

            print(
                f"Indexed document '{file.filename}' as '{doc_id}' with {len(chunks)} chunks (hybrid search enabled)"
            )

            return {
                "markdown": markdown_content,
                "doc_id": doc_id,
                "chunk_count": len(chunks),
            }
        finally:
            # Clean up the temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        print(f"Error converting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== LLM Endpoints ==============


async def perform_extraction(
    document_text: str,
    page_context: str,
    column_name: str,
    column_type: str,
    extraction_prompt: str,
    model: str,
) -> dict:
    """Core extraction logic - separated for reuse in retry."""
    import json

    # Format instruction based on column type
    format_instructions = {
        "date": "Format the date as YYYY-MM-DD.",
        "boolean": "Return 'true' or 'false' as the value string.",
        "number": "Return a clean number string, removing currency symbols if needed.",
        "list": "Return the items as a comma-separated string.",
    }
    format_instruction = format_instructions.get(column_type, "Keep the text concise.")

    prompt = f"""Extract specific information from the provided document excerpts.

RELEVANT DOCUMENT SECTIONS:
{document_text}
{page_context}

Column Name: "{column_name}"
Extraction Instruction: {extraction_prompt}

Format Requirements:
- {format_instruction}
- Provide a confidence score (High/Medium/Low).
- Include the exact quote from the text where the answer is found.
- Provide a brief reasoning for your extraction.
- If the information is not found in the provided sections, state that clearly and set confidence to Low."""

    response = await litellm.acompletion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a precise data extraction agent. Extract data exactly as requested from the document sections provided.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format=ExtractionResponse,
    )

    result = response.choices[0].message.content

    if isinstance(result, str):
        parsed = json.loads(result)
        return {
            "value": str(parsed.get("value", "")),
            "confidence": parsed.get("confidence", "Low"),
            "quote": parsed.get("quote", ""),
            "page": parsed.get("page", 1),
            "reasoning": parsed.get("reasoning", ""),
        }
    else:
        return {
            "value": str(
                result.get("value", "")
                if isinstance(result, dict)
                else getattr(result, "value", "")
            ),
            "confidence": (
                result.get("confidence", "Low")
                if isinstance(result, dict)
                else getattr(result, "confidence", "Low")
            ),
            "quote": (
                result.get("quote", "")
                if isinstance(result, dict)
                else getattr(result, "quote", "")
            ),
            "page": (
                result.get("page", 1)
                if isinstance(result, dict)
                else getattr(result, "page", 1)
            ),
            "reasoning": (
                result.get("reasoning", "")
                if isinstance(result, dict)
                else getattr(result, "reasoning", "")
            ),
        }


@app.post("/extract")
async def extract_column_data(request: ExtractionRequest):
    """Extract structured data from a document using LiteLLM with structured outputs.

    Features:
    - RAG mode with hybrid search (semantic + keyword)
    - Cross-encoder reranking for precision
    - Auto-retry with more context on low confidence
    """
    try:
        # Check cache first
        if request.doc_id:
            cache_key = get_cache_key(request.doc_id, request.prompt, request.model)
            if cache_key in extraction_cache:
                print(f"Cache hit for {request.column_name}")
                return extraction_cache[cache_key]

        # === RAG MODE: Retrieve relevant chunks ===
        extraction_result = None

        if request.doc_id and request.doc_id in document_index:
            indexed = document_index[request.doc_id]
            query = f"{request.column_name}: {request.prompt}"

            # First attempt: 5 chunks
            for attempt, top_k in enumerate([5, 10], start=1):
                relevant_chunks = retrieve_relevant_chunks(
                    query,
                    indexed["chunks"],
                    indexed["embeddings"],
                    top_k=top_k,
                    bm25_index=indexed.get("bm25_index"),
                    use_hybrid=True,
                    use_reranking=True,
                )

                document_text = "\n\n---\n\n".join([c["text"] for c in relevant_chunks])
                pages = sorted(set(c["page_estimate"] for c in relevant_chunks))
                page_context = (
                    f"\n(Relevant sections from pages: {', '.join(map(str, pages))})"
                )

                print(
                    f"RAG[attempt {attempt}]: {len(relevant_chunks)} chunks "
                    f"(~{len(document_text.split())} words) for '{request.column_name}'"
                )

                extraction_result = await perform_extraction(
                    document_text,
                    page_context,
                    request.column_name,
                    request.column_type,
                    request.prompt,
                    request.model,
                )

                # If confidence is not Low, we're done
                if extraction_result["confidence"] != "Low":
                    break

                # If Low confidence and we haven't retried yet, try with more chunks
                if attempt == 1 and len(indexed["chunks"]) > 5:
                    print(
                        f"Low confidence for '{request.column_name}', "
                        f"retrying with more context..."
                    )

        elif request.document_text:
            # Fallback: Use full document text (backwards compatible)
            extraction_result = await perform_extraction(
                request.document_text,
                "",
                request.column_name,
                request.column_type,
                request.prompt,
                request.model,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Either doc_id (for indexed documents) or document_text must be provided",
            )

        # Cache the result
        if request.doc_id:
            cache_key = get_cache_key(request.doc_id, request.prompt, request.model)
            extraction_cache[cache_key] = extraction_result

        return extraction_result

    except Exception as e:
        print(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-prompt")
async def generate_prompt_helper(request: PromptHelperRequest):
    """Generate an extraction prompt using LiteLLM."""
    try:
        prompt = f"""I need to configure a Large Language Model to extract a specific data field from business documents.

Field Name: "{request.name}"
Field Type: "{request.type}"
{f'Draft Prompt: "{request.current_prompt}"' if request.current_prompt else ""}

Please write a clear, effective prompt that I can send to the LLM to get the best extraction results for this field.
The prompt should describe what to look for and how to handle edge cases if applicable.
Return ONLY the prompt text, no conversational filler."""

        response = await litellm.acompletion(
            model=request.model,
            messages=[{"role": "user", "content": prompt}],
        )

        return {"prompt": response.choices[0].message.content.strip()}

    except Exception as e:
        print(f"Prompt generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def analyze_data_with_chat(request: ChatRequest):
    """Chat with the extracted data using LiteLLM."""
    try:
        system_instruction = f"""You are an intelligent data analyst assistant.
You have access to a dataset extracted from documents (provided in context).

{request.data_context}

Instructions:
1. Answer the user's question based strictly on the provided data table.
2. If comparing documents, mention them by name.
3. If the data is missing or N/A, state that clearly.
4. Keep answers professional and concise."""

        messages = [{"role": "system", "content": system_instruction}]

        # Add history
        for msg in request.history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": request.message})

        response = await litellm.acompletion(
            model=request.model,
            messages=messages,
        )

        return {"response": response.choices[0].message.content}

    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models")
async def list_available_models():
    """Return a list of suggested models for the frontend."""
    return {
        "models": [
            {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "anthropic/claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet"},
            {"id": "anthropic/claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku"},
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
