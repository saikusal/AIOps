#!/usr/bin/env python3
"""
rag_local.py

Read a local document, chunk it, attempt to get embeddings from a local vLLM endpoint,
fallback to TF-IDF if embedding calls fail, perform a similarity search,
and query the local OpenAI-compatible completions/chat endpoint with retrieved context.

Usage:
  python rag_local.py --file sample.pdf --question "Summarize the policy" --topk 4 --no-verify

Requirements:
  pip install requests numpy scikit-learn python-docx pdfplumber
    (pdfplumber optional for PDFs; python-docx optional for .docx)
"""
import os
import sys
import argparse
import json
import math
import requests
import numpy as np
from typing import List, Tuple

# Optional libs for reading docx/pdf
try:
    import pdfplumber
except Exception:
    pdfplumber = None
try:
    import docx
except Exception:
    docx = None

# Optional sklearn fallback
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
except Exception:
    TfidfVectorizer = None
    sklearn_cosine = None

# ----------------- config (edit or set env) -----------------
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")
VLLM_EMBEDDING_URL = os.getenv("VLLM_EMBEDDING_URL", "")
# completions/chat endpoint (if different set VLLM_EMBEDDING_URL)
VLLM_COMPLETIONS_URL = os.getenv(
    "VLLM_API_URL",
    VLLM_EMBEDDING_URL.replace("/embeddings", "/completions") if VLLM_EMBEDDING_URL else "",
)

TIMEOUT = 30

# ----------------- utilities -----------------
def read_txt_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_docx_file(path: str) -> str:
    if not docx:
        raise RuntimeError("python-docx not installed. pip install python-docx")
    d = docx.Document(path)
    paras = [p.text for p in d.paragraphs if p.text and p.text.strip()]
    return "\n".join(paras)

def read_pdf_file(path: str) -> str:
    if not pdfplumber:
        raise RuntimeError("pdfplumber not installed. pip install pdfplumber")
    texts = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                texts.append(t)
    return "\n".join(texts)

def read_document(path: str) -> str:
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No such file: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        return read_txt_file(path)
    if ext in (".docx",):
        return read_docx_file(path)
    if ext in (".pdf",):
        return read_pdf_file(path)
    # fallback: try to read as text
    return read_txt_file(path)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    tokens = text.split()
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        chunk = tokens[i:i+chunk_size]
        out.append(" ".join(chunk))
        i += (chunk_size - overlap)
    return out

def cosine_similarity(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    # vec shape (d,), matrix shape (n,d)
    if matrix.size == 0:
        return np.zeros((0,))
    # safe norms
    denom = (np.linalg.norm(vec) * np.linalg.norm(matrix, axis=1))
    denom = np.where(denom == 0, 1e-9, denom)
    return np.dot(matrix, vec) / denom

# ----------------- vLLM calls -----------------
def get_embedding_vllm(text: str, api_url: str, api_key: str, verify: bool = True) -> Tuple[bool, dict]:
    """
    Call embedding endpoint. Returns (ok, parsed_json_or_error_str)
    Expecting returned structure may vary; we'll return the parsed json.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent":"rag-local/1.0"}
    payload = {"input": text}
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=TIMEOUT, verify=verify)
    except requests.exceptions.SSLError as e:
        return False, f"SSL error: {e}"
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {e}"
    try:
        data = r.json()
    except Exception:
        return False, f"Non-JSON response {r.status_code}: {r.text[:400]}"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {json.dumps(data)[:800]}"
    return True, data

def extract_embedding_from_response(data) -> List[float]:
    """
    Different OpenAI-compatible embedding deployments may return shapes like:
      {"data":[{"embedding":[...] , ... }], "model": ...}
    or {"embedding": [...]}
    This tries several patterns.
    """
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list) and len(data["data"])>0:
            first = data["data"][0]
            if isinstance(first, dict) and "embedding" in first:
                return list(first["embedding"])
        if "embedding" in data and isinstance(data["embedding"], list):
            return list(data["embedding"])
    # fallback: search recursively
    def find_emb(o):
        if isinstance(o, dict):
            for v in o.values():
                res = find_emb(v)
                if res is not None: return res
        if isinstance(o, list):
            # if the list contains numbers, treat as embedding
            if len(o)>0 and all(isinstance(x,(int,float)) for x in o[:10]):
                return o
            for item in o:
                res = find_emb(item)
                if res is not None: return res
        return None
    emb = find_emb(data)
    return list(emb) if emb is not None else None

def call_completion_vllm(prompt: str, api_url: str, api_key: str, verify: bool = True) -> Tuple[bool, dict]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent":"rag-local/1.0"}
    payload = {"messages": [{"role":"user","content": prompt}]}
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=TIMEOUT, verify=verify)
    except requests.exceptions.SSLError as e:
        return False, {"error": f"SSL error: {e}"}
    except requests.exceptions.RequestException as e:
        return False, {"error": f"Request error: {e}"}
    try:
        data = r.json()
    except Exception:
        return False, {"error": f"Non-JSON response {r.status_code}: {r.text[:400]}"}
    if r.status_code >= 400:
        return False, {"error": f"HTTP {r.status_code}: {json.dumps(data)[:800] if isinstance(data,dict) else str(data)}"}
    return True, data

# ----------------- fallback (TF-IDF) -----------------
def build_tfidf_index(chunks: List[str]):
    if TfidfVectorizer is None:
        raise RuntimeError("scikit-learn not installed. Install scikit-learn to use tf-idf fallback.")
    vect = TfidfVectorizer(stop_words="english", max_features=20000)
    mat = vect.fit_transform(chunks)  # shape (n_chunks, features)
    return vect, mat

def tfidf_query_sim(query: str, vect, mat):
    qv = vect.transform([query])
    sim = sklearn_cosine(mat, qv).reshape(-1)
    return sim

# ----------------- main flow -----------------
def retrieve_context(chunks: List[str], embeddings_matrix: np.ndarray, query_embedding: np.ndarray, topk: int = 3) -> List[Tuple[int, str, float]]:
    sims = cosine_similarity(query_embedding, embeddings_matrix)
    idx = np.argsort(-sims)[:topk]
    return [(int(i), chunks[int(i)], float(sims[int(i)])) for i in idx]

def run_rag(filepath: str, question: str, vllm_embed_url: str, vllm_comp_url: str, vllm_key: str, verify_ssl: bool = True, topk: int = 3):
    print("Reading document:", filepath)
    text = read_document(filepath)
    print("Document length (chars):", len(text))
    chunks = chunk_text(text, chunk_size=400, overlap=50)
    print("Chunk count:", len(chunks))

    # 1) try to get chunk embeddings from the local endpoint
    embeddings = []
    print("Attempting to fetch embeddings from the local endpoint for each chunk. Verify SSL:", verify_ssl)
    embeddings_ok = True
    for i, ch in enumerate(chunks):
        ok, res = get_embedding_vllm(ch[:10000], vllm_embed_url, vllm_key, verify=verify_ssl)
        if not ok:
            print(f"Embedding API failed on chunk {i}: {res}")
            embeddings_ok = False
            break
        emb = extract_embedding_from_response(res)
        if emb is None:
            print(f"Could not extract embedding from response for chunk {i}; falling back.")
            embeddings_ok = False
            break
        embeddings.append(emb)
    if embeddings_ok and len(embeddings) == len(chunks):
        print("Embeddings obtained from the local endpoint for all chunks.")
        embeddings_matrix = np.array(embeddings, dtype=float)
        # embed the query
        ok, qres = get_embedding_vllm(question, vllm_embed_url, vllm_key, verify=verify_ssl)
        if not ok:
            print("Failed to embed query via the local endpoint:", qres)
            # degrade to TF-IDF fallback below
            embeddings_ok = False
        else:
            qemb = extract_embedding_from_response(qres)
            if qemb is None:
                print("Could not extract query embedding; falling back.")
                embeddings_ok = False
            else:
                qemb = np.array(qemb, dtype=float)
    if not embeddings_ok:
        # fall back to TF-IDF approach if embeddings failed
        print("Using TF-IDF fallback for similarity search (no external embeddings).")
        if TfidfVectorizer is None:
            raise RuntimeError("scikit-learn is required for fallback; pip install scikit-learn")
        vect, mat = build_tfidf_index(chunks)
        sims = tfidf_query_sim(question, vect, mat)  # shape (n_chunks,)
        topk = min(topk, len(chunks))
        idx = np.argsort(-sims)[:topk]
        context_parts = []
        for i in idx:
            context_parts.append({"i": int(i), "chunk": chunks[int(i)], "score": float(sims[int(i)])})
    else:
        # use embeddings result
        context_parts = retrieve_context(chunks, embeddings_matrix, qemb, topk=topk)

    # Build combined context text
    ctx_texts = []
    for item in context_parts:
        # item may be tuple (i, chunk, score) or dict fallback
        if isinstance(item, dict):
            ctx_texts.append(f"Source #{item['i']} (score={item['score']:.3f}):\n{item['chunk']}\n")
        else:
            idx, chunk, score = item
            ctx_texts.append(f"Source #{idx} (score={score:.3f}):\n{chunk}\n")
    context = "\n\n---\n\n".join(ctx_texts)
    # Craft a prompt instructing model to use context and answer question concisely
    prompt = (
        "You are a helpful assistant answering questions using the provided document excerpts.\n"
        "Use only the provided excerpts to answer. If information is not present, say \"I could not find that in the documents.\".\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER (concise):"
    )
    print("Sending prompt to the local vLLM completions endpoint...")
    ok, comp_res = call_completion_vllm(prompt, vllm_comp_url, vllm_key, verify=verify_ssl)
    if not ok:
        print("Completion call failed:", comp_res.get("error"))
        return {"error": comp_res}
    # try to extract message
    out_text = None
    try:
        if isinstance(comp_res, dict):
            # new style
            if "choices" in comp_res and isinstance(comp_res["choices"], list) and comp_res["choices"]:
                ch0 = comp_res["choices"][0]
                if isinstance(ch0, dict):
                    msg = ch0.get("message")
                    if isinstance(msg, dict):
                        out_text = msg.get("content")
                    if not out_text:
                        out_text = ch0.get("text")
            # top-level fallback
            for k in ("text", "response", "result"):
                if not out_text and k in comp_res and isinstance(comp_res[k], str):
                    out_text = comp_res[k]
    except Exception as e:
        print("Error parsing completion response:", e)
    print("\n=== ANSWER ===")
    print(out_text or "(no extracted text)")
    return {"answer": out_text, "raw_completion_response": comp_res, "context_parts": context_parts}

# ----------------- script entry -----------------
def main():
    parser = argparse.ArgumentParser(description="Local RAG tester with vLLM completions + embedding fallback")
    parser.add_argument("--file", "-f", required=True, help="Local document path (pdf, txt, docx)")
    parser.add_argument("--question", "-q", required=True, help="Question to ask the document")
    parser.add_argument("--topk", type=int, default=3, help="How many chunks to include as context")
    parser.add_argument("--no-verify", dest="verify_ssl", action="store_false", help="Disable SSL verification for requests")
    parser.add_argument("--verify", dest="verify_ssl", action="store_true", help="Enable SSL verification")
    parser.set_defaults(verify_ssl=False)  # default off since you were seeing SSL issues; change as needed
    args = parser.parse_args()

    vllm_key = VLLM_API_KEY
    vllm_embed_url = VLLM_EMBEDDING_URL
    vllm_comp_url = VLLM_COMPLETIONS_URL

    if vllm_key.startswith("REPLACE") and not os.getenv("VLLM_API_KEY"):
        print("WARNING: VLLM_API_KEY not set; authenticated completions/embeddings will fail unless you edit the script or set env var.")
    print("vLLM embed URL:", vllm_embed_url)
    print("vLLM completions URL:", vllm_comp_url)
    print("Verify SSL:", args.verify_ssl)

    res = run_rag(args.file, args.question, vllm_embed_url, vllm_comp_url, vllm_key, verify_ssl=args.verify_ssl, topk=args.topk)
    # Optionally save result to file
    outpath = "rag_result.json"
    with open(outpath, "w", encoding="utf-8") as fo:
        json.dump(res, fo, indent=2, ensure_ascii=False)
    print("Saved result to", outpath)

if __name__ == "__main__":
    main()
