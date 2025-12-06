export interface ConversionResult {
  markdown: string;
  docId: string;
  chunkCount: number;
}

export const processDocumentToMarkdown = async (
  file: File
): Promise<ConversionResult> => {
  try {
    const formData = new FormData();
    formData.append("file", file);

    // Send to local backend running Docling
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const response = await fetch(`${apiUrl}/convert`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Conversion failed: ${response.statusText}`);
    }

    const data = await response.json();
    return {
      markdown: data.markdown || "",
      docId: data.doc_id || "",
      chunkCount: data.chunk_count || 0,
    };
  } catch (error) {
    console.error("Document Conversion failed:", error);
    throw new Error(
      `Failed to convert ${file.name}. Is the backend server running?`
    );
  }
};
