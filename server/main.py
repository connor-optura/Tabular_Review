from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from dotenv import load_dotenv
import tempfile
import os
import shutil
import litellm

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
    document_text: str
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
            return {"markdown": markdown_content}
        finally:
            # Clean up the temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        print(f"Error converting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== LLM Endpoints ==============


@app.post("/extract")
async def extract_column_data(request: ExtractionRequest):
    """Extract structured data from a document using LiteLLM with structured outputs."""
    try:
        # Format instruction based on column type
        format_instructions = {
            "date": "Format the date as YYYY-MM-DD.",
            "boolean": "Return 'true' or 'false' as the value string.",
            "number": "Return a clean number string, removing currency symbols if needed.",
            "list": "Return the items as a comma-separated string.",
        }
        format_instruction = format_instructions.get(
            request.column_type, "Keep the text concise."
        )

        prompt = f"""Extract specific information from the provided document.

DOCUMENT CONTENT:
{request.document_text}

Column Name: "{request.column_name}"
Extraction Instruction: {request.prompt}

Format Requirements:
- {format_instruction}
- Provide a confidence score (High/Medium/Low).
- Include the exact quote from the text where the answer is found.
- Provide a brief reasoning for your extraction."""

        response = litellm.completion(
            model=request.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise data extraction agent. Extract data exactly as requested from the document.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=ExtractionResponse,
        )

        # LiteLLM returns the parsed Pydantic model in message.content when using response_format
        result = response.choices[0].message.content

        # Handle both string (needs parsing) and already-parsed responses
        if isinstance(result, str):
            import json

            parsed = json.loads(result)
            return {
                "value": str(parsed.get("value", "")),
                "confidence": parsed.get("confidence", "Low"),
                "quote": parsed.get("quote", ""),
                "page": parsed.get("page", 1),
                "reasoning": parsed.get("reasoning", ""),
            }
        else:
            # Already a dict/model
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

        response = litellm.completion(
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

        response = litellm.completion(
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
