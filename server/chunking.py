"""
Document chunking and embedding service for RAG-powered extraction.

Production-grade implementation with:
- Hybrid search (semantic + BM25 keyword matching)
- High-quality BGE embeddings
- Cross-encoder reranking for precision
- Configurable retrieval parameters
"""

from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
from typing import TypedDict, Optional
from rank_bm25 import BM25Okapi
import re


class DocumentChunk(TypedDict):
    text: str
    start_idx: int
    page_estimate: int


class RetrievalConfig(TypedDict, total=False):
    """Configuration for retrieval behavior."""

    top_k: int  # Final number of chunks to return
    semantic_weight: float  # Weight for semantic scores (0-1)
    use_reranking: bool  # Whether to use cross-encoder reranking
    rerank_top_n: int  # Number of candidates to rerank


# Default retrieval configuration
DEFAULT_CONFIG: RetrievalConfig = {
    "top_k": 5,
    "semantic_weight": 0.7,  # 70% semantic, 30% keyword
    "use_reranking": True,
    "rerank_top_n": 15,  # Rerank top 15 candidates
}


# Lazy-loaded models
_embedder: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None


def get_embedder() -> SentenceTransformer:
    """Lazy load the embedding model."""
    global _embedder
    if _embedder is None:
        # BGE-small: Better quality than MiniLM, still fast
        # Alternatively: "BAAI/bge-base-en-v1.5" for even better quality
        print("Loading embedding model (BAAI/bge-small-en-v1.5)...")
        _embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _embedder


def get_reranker() -> CrossEncoder:
    """Lazy load the cross-encoder reranking model."""
    global _reranker
    if _reranker is None:
        # Fast and accurate reranker
        print("Loading reranker model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def preload_models():
    """Preload all models at startup (call from main.py)."""
    get_embedder()
    get_reranker()
    print("All RAG models loaded.")


def tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    # Lowercase and split on non-alphanumeric
    return re.findall(r"\b\w+\b", text.lower())


def chunk_document(
    text: str, chunk_size: int = 500, overlap: int = 100
) -> list[DocumentChunk]:
    """
    Split document into overlapping chunks with metadata.

    Args:
        text: Full document text
        chunk_size: Target number of words per chunk
        overlap: Number of overlapping words between chunks

    Returns:
        List of chunks with text, position, and estimated page number
    """
    words = text.split()
    chunks: list[DocumentChunk] = []

    if len(words) == 0:
        return chunks

    step = chunk_size - overlap
    if step <= 0:
        step = chunk_size // 2

    for i in range(0, len(words), step):
        chunk_text = " ".join(words[i : i + chunk_size])
        chunks.append(
            {
                "text": chunk_text,
                "start_idx": i,
                "page_estimate": i // 300 + 1,
            }
        )

    return chunks


def generate_embeddings(chunks: list[DocumentChunk]) -> np.ndarray:
    """
    Generate embeddings for all chunks.

    Args:
        chunks: List of document chunks

    Returns:
        Numpy array of embeddings, shape (num_chunks, embedding_dim)
    """
    if not chunks:
        return np.array([])

    embedder = get_embedder()
    texts = [c["text"] for c in chunks]

    # BGE models benefit from instruction prefix for retrieval
    embeddings = embedder.encode(
        texts,
        show_progress_bar=False,
        normalize_embeddings=True,  # Pre-normalize for cosine similarity
    )
    return np.array(embeddings)


def build_bm25_index(chunks: list[DocumentChunk]) -> BM25Okapi:
    """Build BM25 index for keyword search."""
    tokenized_chunks = [tokenize(c["text"]) for c in chunks]
    return BM25Okapi(tokenized_chunks)


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """Normalize scores to 0-1 range."""
    if len(scores) == 0:
        return scores
    min_s, max_s = scores.min(), scores.max()
    if max_s - min_s < 1e-9:
        return np.ones_like(scores)
    return (scores - min_s) / (max_s - min_s)


def hybrid_search(
    query: str,
    chunks: list[DocumentChunk],
    embeddings: np.ndarray,
    bm25_index: BM25Okapi,
    config: RetrievalConfig = DEFAULT_CONFIG,
) -> list[tuple[DocumentChunk, float]]:
    """
    Hybrid search combining semantic similarity and BM25 keyword matching.

    Args:
        query: Search query
        chunks: Document chunks
        embeddings: Pre-computed chunk embeddings (normalized)
        bm25_index: Pre-built BM25 index
        config: Retrieval configuration

    Returns:
        List of (chunk, score) tuples, sorted by combined score
    """
    if not chunks or embeddings.size == 0:
        return []

    top_k = config.get("top_k", 5)
    semantic_weight = config.get("semantic_weight", 0.7)
    keyword_weight = 1 - semantic_weight

    # === Semantic Search ===
    embedder = get_embedder()
    query_embedding = embedder.encode(
        [query], show_progress_bar=False, normalize_embeddings=True
    )

    # Cosine similarity (embeddings are pre-normalized)
    semantic_scores = np.dot(embeddings, query_embedding.T).flatten()

    # === BM25 Keyword Search ===
    query_tokens = tokenize(query)
    bm25_scores = np.array(bm25_index.get_scores(query_tokens))

    # === Combine Scores ===
    semantic_norm = normalize_scores(semantic_scores)
    bm25_norm = normalize_scores(bm25_scores)

    combined_scores = (semantic_weight * semantic_norm) + (keyword_weight * bm25_norm)

    # Get top candidates
    num_candidates = (
        config.get("rerank_top_n", 15) if config.get("use_reranking", True) else top_k
    )
    num_candidates = min(num_candidates, len(chunks))
    top_indices = np.argsort(combined_scores)[-num_candidates:][::-1]

    return [(chunks[i], combined_scores[i]) for i in top_indices]


def rerank_chunks(
    query: str,
    candidates: list[tuple[DocumentChunk, float]],
    top_k: int = 5,
) -> list[DocumentChunk]:
    """
    Rerank candidate chunks using cross-encoder for higher precision.

    Args:
        query: Original query
        candidates: List of (chunk, initial_score) from hybrid search
        top_k: Number of final chunks to return

    Returns:
        Top-K chunks after reranking
    """
    if not candidates:
        return []

    reranker = get_reranker()

    # Prepare pairs for cross-encoder
    pairs = [[query, chunk["text"]] for chunk, _ in candidates]

    # Get reranking scores
    rerank_scores = reranker.predict(pairs)

    # Sort by reranking score and return top-k
    ranked = sorted(zip(candidates, rerank_scores), key=lambda x: x[1], reverse=True)

    return [chunk for (chunk, _), _ in ranked[:top_k]]


def retrieve_relevant_chunks(
    query: str,
    chunks: list[DocumentChunk],
    embeddings: np.ndarray,
    top_k: int = 5,
    bm25_index: Optional[BM25Okapi] = None,
    use_hybrid: bool = True,
    use_reranking: bool = True,
) -> list[DocumentChunk]:
    """
    Find most relevant chunks using hybrid search + reranking.

    This is the main retrieval function that combines all techniques.

    Args:
        query: Search query (column name + prompt)
        chunks: List of document chunks
        embeddings: Pre-computed chunk embeddings
        top_k: Number of top chunks to return
        bm25_index: Pre-built BM25 index (built on-the-fly if None)
        use_hybrid: Whether to use hybrid search (semantic + BM25)
        use_reranking: Whether to use cross-encoder reranking

    Returns:
        Top-K most relevant chunks
    """
    if not chunks or embeddings.size == 0:
        return []

    config: RetrievalConfig = {
        "top_k": top_k,
        "semantic_weight": 0.7,
        "use_reranking": use_reranking,
        "rerank_top_n": min(15, len(chunks)),
    }

    # Build BM25 index if not provided and using hybrid search
    if use_hybrid:
        if bm25_index is None:
            bm25_index = build_bm25_index(chunks)

        candidates = hybrid_search(query, chunks, embeddings, bm25_index, config)
    else:
        # Pure semantic search fallback
        embedder = get_embedder()
        query_embedding = embedder.encode(
            [query], show_progress_bar=False, normalize_embeddings=True
        )
        similarities = np.dot(embeddings, query_embedding.T).flatten()
        top_indices = np.argsort(similarities)[-config["rerank_top_n"] :][::-1]
        candidates = [(chunks[i], similarities[i]) for i in top_indices]

    # Rerank if enabled
    if use_reranking and len(candidates) > top_k:
        return rerank_chunks(query, candidates, top_k)
    else:
        # Just return top-k from hybrid/semantic search
        return [chunk for chunk, _ in candidates[:top_k]]


def embed_query(query: str) -> np.ndarray:
    """Generate embedding for a single query."""
    embedder = get_embedder()
    return embedder.encode([query], show_progress_bar=False, normalize_embeddings=True)[
        0
    ]
