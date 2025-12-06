import {
  DocumentFile,
  ExtractionCell,
  Column,
  ExtractionResult,
} from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Helper for delay
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Generic retry wrapper
async function withRetry<T>(
  operation: () => Promise<T>,
  retries = 5,
  initialDelay = 1000
): Promise<T> {
  let currentTry = 0;
  while (true) {
    try {
      return await operation();
    } catch (error: any) {
      currentTry++;

      // Check for Rate Limit / Quota errors
      const isRateLimit =
        error?.status === 429 ||
        error?.message?.includes("429") ||
        error?.message?.includes("rate") ||
        error?.message?.includes("quota");

      if (isRateLimit && currentTry <= retries) {
        const delay =
          initialDelay * Math.pow(2, currentTry - 1) + Math.random() * 1000;
        console.warn(
          `Rate Limit hit. Retrying attempt ${currentTry} in ${delay.toFixed(
            0
          )}ms...`
        );
        await wait(delay);
        continue;
      }

      throw error;
    }
  }
}

export const extractColumnData = async (
  doc: DocumentFile,
  column: Column,
  modelId: string
): Promise<ExtractionCell> => {
  return withRetry(async () => {
    // Build request body - prefer doc_id for RAG mode, fallback to full text
    const requestBody: Record<string, unknown> = {
      column_name: column.name,
      column_type: column.type,
      prompt: column.prompt,
      model: modelId,
    };

    if (doc.docId) {
      // Use RAG mode with doc_id (much more efficient for large docs)
      requestBody.doc_id = doc.docId;
      console.log(
        `[RAG] Extracting "${column.name}" using indexed doc: ${doc.docId}`
      );
    } else {
      // Fallback: Decode Base64 and send full text
      let docText = "";
      try {
        docText = decodeURIComponent(escape(atob(doc.content)));
      } catch (e) {
        docText = atob(doc.content);
      }
      requestBody.document_text = docText;
      console.log(
        `[Legacy] Extracting "${column.name}" with full document text`
      );
    }

    const response = await fetch(`${API_BASE}/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || "Extraction failed");
    }

    const result = await response.json();

    return {
      value: String(result.value || ""),
      confidence: result.confidence || "Low",
      quote: result.quote || "",
      page: result.page || 1,
      reasoning: result.reasoning || "",
      status: "needs_review",
    };
  });
};

export const generatePromptHelper = async (
  name: string,
  type: string,
  currentPrompt: string | undefined,
  modelId: string
): Promise<string> => {
  try {
    const response = await fetch(`${API_BASE}/generate-prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        type,
        current_prompt: currentPrompt,
        model: modelId,
      }),
    });

    if (!response.ok) {
      throw new Error("Failed to generate prompt");
    }

    const result = await response.json();
    return result.prompt || "";
  } catch (error) {
    console.error("Prompt generation error:", error);
    return currentPrompt || `Extract the ${name} from the document.`;
  }
};

export const analyzeDataWithChat = async (
  message: string,
  context: {
    documents: DocumentFile[];
    columns: Column[];
    results: ExtractionResult;
  },
  history: any[],
  modelId: string
): Promise<string> => {
  let dataContext = "CURRENT EXTRACTION DATA:\n";
  dataContext += `Documents: ${context.documents
    .map((d) => d.name)
    .join(", ")}\n`;
  dataContext += `Columns: ${context.columns
    .map((c) => c.name)
    .join(", ")}\n\n`;
  dataContext += "DATA TABLE (CSV Format):\n";

  const headers = ["Document Name", ...context.columns.map((c) => c.name)].join(
    ","
  );
  dataContext += headers + "\n";

  context.documents.forEach((doc) => {
    const row = [doc.name];
    context.columns.forEach((col) => {
      const cell = context.results[doc.id]?.[col.id];
      const val = cell ? cell.value.replace(/,/g, " ") : "N/A";
      row.push(val);
    });
    dataContext += row.join(",") + "\n";
  });

  // Convert history to the format expected by the backend
  const formattedHistory = history.map((msg) => ({
    role: msg.role,
    content:
      typeof msg.parts === "string" ? msg.parts : msg.parts?.[0]?.text || "",
  }));

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        data_context: dataContext,
        history: formattedHistory,
        model: modelId,
      }),
    });

    if (!response.ok) {
      throw new Error("Chat request failed");
    }

    const result = await response.json();
    return result.response || "No response generated.";
  } catch (error) {
    console.error("Chat analysis error:", error);
    return "I apologize, but I encountered an error while analyzing the data. Please try again.";
  }
};

// Fetch available models from the backend
export const fetchAvailableModels = async (): Promise<
  { id: string; name: string }[]
> => {
  try {
    const response = await fetch(`${API_BASE}/models`);
    if (!response.ok) {
      throw new Error("Failed to fetch models");
    }
    const result = await response.json();
    return result.models;
  } catch (error) {
    console.error("Error fetching models:", error);
    // Return default models if fetch fails
    return [
      { id: "anthropic/claude-sonnet-4-20250514", name: "Claude Sonnet 4" },
      { id: "anthropic/claude-3-5-haiku-latest", name: "Claude 3.5 Haiku" },
    ];
  }
};
