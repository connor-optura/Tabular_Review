export interface DocumentFile {
  id: string;
  name: string;
  type: string;
  size: number;
  content: string; // Base64 string for PDF/Images, or raw text for TXT
  mimeType: string;
  docId?: string; // Backend document ID for RAG-powered extraction
}

export type ColumnType = "text" | "number" | "date" | "boolean" | "list";

export interface Column {
  id: string;
  name: string;
  type: ColumnType;
  prompt: string;
  status: "idle" | "extracting" | "completed" | "error";
  width?: number;
}

export interface ExtractionCell {
  value: string;
  confidence: "High" | "Medium" | "Low";
  quote: string;
  page: number;
  reasoning: string;
  // UI State for review workflow
  status?: "verified" | "needs_review" | "edited";
}

export interface ExtractionResult {
  [docId: string]: {
    [colId: string]: ExtractionCell | null;
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "model";
  text: string;
  timestamp: number;
}

export type ViewMode = "grid" | "chat";
export type SidebarMode = "none" | "verify" | "chat";
