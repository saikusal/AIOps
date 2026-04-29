import os
import sys
import json
import logging
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Tuple
import binascii
import chardet
import gzip

# ====== Configuration ======
logger = logging.getLogger(__name__)
VERIFY_SSL = True  # SSL verification for URL fetching

MAX_FETCH_BYTES = 2 * 1024 * 1024   # 2 MB
CHUNK_SIZE_WORDS = 300
CHUNK_OVERLAP = 50
TOP_K_CHUNKS = 6

# Basic tokens (extend as needed). Add sensitive/drug keywords here.
BASIC_PROFANITY = [
    "fuck", "fucking", "shit", "bitch", "whore", "slut", "porn", "xxx", "cunt",
    "drugs", "medicine", "cocaine", "heroin", "lsd", "xanax", "alprazolam",
    "cannabis", "weed", "marijuana", "thc", "hashish", "buy", "order", "shop"
]

# ====== Utilities ======
def fetch_url_text(url: str, timeout: int = 15) -> Tuple[str, str, int, dict]:
    """
    Fetch a URL and try to extract readable text using chardet for robust encoding detection.
    Returns (title, text, status_code, headers)
    Raises on HTTP error.
    """
    headers = {"User-Agent": "asset-management-moderation/1.0"}
    logger.info(f"Fetching URL: {url}")
    resp = requests.get(url, headers=headers, timeout=timeout, stream=True, verify=VERIFY_SSL)
    status = resp.status_code
    resp.raise_for_status()

    clen = resp.headers.get("Content-Length")
    if clen and int(clen) > MAX_FETCH_BYTES:
        logger.warning(f"Content-Length {clen} exceeds max bytes {MAX_FETCH_BYTES}")
        raise RuntimeError(f"Content too large: {clen} bytes")

    raw = resp.raw.read(MAX_FETCH_BYTES + 1)
    if len(raw) > MAX_FETCH_BYTES:
        logger.warning(f"Downloaded content exceeds max bytes {MAX_FETCH_BYTES}")
        raise RuntimeError("Fetched content exceeds max allowed size")
    
    logger.info(f"Read {len(raw)} bytes from {url}. Raw preview: {raw[:100]!r}")

    # Check for and handle Gzip compression
    if raw.startswith(b'\x1f\x8b'):
        logger.info("Gzip content detected. Decompressing...")
        try:
            raw = gzip.decompress(raw)
            logger.info(f"Decompressed to {len(raw)} bytes. New raw preview: {raw[:100]!r}")
        except gzip.BadGzipFile as e:
            logger.error(f"Gzip decompression failed: {e}")
            raise RuntimeError(f"Gzip decompression failed: {e}")

    detected_encoding = None
    if raw:
        detection = chardet.detect(raw)
        logger.info(f"Chardet detection result: {detection}")
        if detection and detection['encoding'] and detection['confidence'] > 0.5: # Lowered confidence threshold
            detected_encoding = detection['encoding']
            logger.info(f"Using detected encoding: {detected_encoding} with confidence {detection['confidence']}")

    content_type = resp.headers.get("Content-Type", "").lower()
    logger.info(f"Content-Type: {content_type}")

    if "html" in content_type or url.lower().endswith(".html") or b"<html" in raw[:1000].lower():
        try:
            soup = BeautifulSoup(raw, "html.parser", from_encoding=detected_encoding)
            
            # Remove irrelevant tags before extracting text
            for element in soup(["script", "style", "head", "nav", "footer", "aside"]):
                element.decompose()

            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else url
            
            # Get text and clean up excessive whitespace
            text = soup.get_text(separator="\n")
            text = re.sub(r'\n\s*\n', '\n', text) # Collapse multiple empty lines
            
            logger.info(f"Successfully parsed HTML. Title: {title}. Text preview: {text.strip()[:200]!r}")
            return title, text, status, dict(resp.headers)
        except Exception as e:
            logger.error(f"HTML parsing failed: {e}", exc_info=True)
            raise RuntimeError(f"HTML parsing failed: {e}")

    try:
        encoding_to_try = detected_encoding or 'utf-8'
        logger.info(f"Falling back to non-HTML decode with encoding: {encoding_to_try}")
        text = raw.decode(encoding_to_try, errors="replace")
        logger.info(f"Successfully decoded as plain text. Preview: {text[:200]!r}")
        return url, text, status, dict(resp.headers)
    except Exception as e:
        logger.error(f"Final fallback decode failed: {e}", exc_info=True)
        raise RuntimeError("Unable to extract text from content")

def chunk_text(text: str, chunk_size_words: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size_words])
        chunks.append(chunk)
        i += chunk_size_words - overlap
    return chunks

def _token_matches_in_text(tokens: List[str], text: str) -> List[str]:
    found = []
    s = (text or "").lower()
    for token in tokens:
        # use word boundary to reduce false positives; allow hyphen/underscore in words
        if re.search(r"\b" + re.escape(token.lower()) + r"\b", s):
            found.append(token.lower())
    return found

# ====== LLM call wrapper for content moderation ======
def call_aide_completions(prompt: str, timeout: int = 60) -> Tuple[bool, dict]:
    """Call the vLLM backend for content moderation analysis."""
    from genai.llm_backend import query_llm
    ok, _status, text = query_llm(prompt)
    if not ok:
        return False, {"error": text or "LLM call failed"}
    txt = text.strip()
    try:
        parsed = json.loads(txt)
        return True, parsed
    except Exception:
        m = re.search(r"(\{.*\})", txt, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
                return True, parsed
            except Exception:
                return False, {"error": "Could not parse JSON from model output", "raw": txt}
        return False, {"error": "Model output not JSON", "raw": txt}

def build_moderation_prompt(title: str, url: str, chunks: List[str]) -> str:
    context_parts = []
    for i, c in enumerate(chunks[:TOP_K_CHUNKS]):
        trimmed = c.strip().replace("\n", " ")
        if len(trimmed) > 1000:
            trimmed = trimmed[:1000] + "..."
        context_parts.append(f"CHUNK_IDX:{i}\n{trimmed}")
    context_block = "\n\n---\n\n".join(context_parts) or "(no text)"

    prompt = f"""
SYSTEM: You are a strict content moderation assistant. Use ONLY the provided CONTEXT sections to judge whether the page contains vulgar, explicit sexual content, graphic violence, hate speech, threats, or instructions for wrongdoing. Do NOT use outside knowledge.

PAGE_TITLE: {title}
PAGE_URL: {url}

CONTEXT:
{context_block}

TASK: Return JSON ONLY with the following fields:
{{
  "description": "A brief, one-sentence summary of the page content.",
  "verdict": one of ["allow","block","review"],
  "reasons": [list of categories, e.g. ["profanity","explicit_sex","hate_speech","sale_of_drugs"]],
  "severity": one of ["low","medium","high"],
  "confidence": float between 0 and 1,
  "evidence": [ up to 3 short text excerpts from the CONTEXT that justify the verdict ]
}}

Special rule: If the URL or title indicates *sale of drugs* (words like "buy", "order", "shop" combined with drug tokens such as "cannabis", "xanax", "cocaine"), return verdict "block".

If nothing in CONTEXT matches any unwanted content, return verdict = "allow".

Return only valid JSON.
"""
    return prompt

def scan_url_for_unwanted(url: str):
    try:
        title, text, status_code, headers = fetch_url_text(url)
    except Exception as e:
        # Treat fetch failures as review, not allow
        return {"description": "Could not fetch URL.", "verdict": "review", "reasons": ["fetch_failed"], "severity":"low", "confidence":0.35, "evidence":[str(e)[:200]]}

    # If scraped text is too short or looks like cloudflare/captcha, return review
    text_clean = (text or "").strip()
    if not text_clean or len(text_clean) < 100:
        return {"description": "Page was empty or too short to analyze.", "verdict":"review", "reasons":["no_text_fetched"], "severity":"low", "confidence":0.35, "evidence":[]}

    # Build chunks and call AiDE moderation for deeper check
    chunks = chunk_text(text_clean)
    prompt = build_moderation_prompt(title, url, chunks[:TOP_K_CHUNKS])

    ok, resp = call_aide_completions(prompt)
    if not ok:
        return {"description": "AI analysis failed.", "verdict": "review", "reasons": ["llm_call_failed"], "severity":"medium", "confidence":0.5, "evidence":[str(resp)[:200]]}

    # If resp is parsed JSON from model, validate fields
    res = resp
    # Fallback safety: ensure keys exist and types are sane
    description = res.get("description") if isinstance(res.get("description"), str) else "AI did not provide a description."
    verdict = res.get("verdict") if isinstance(res.get("verdict"), str) else "review"
    reasons = res.get("reasons") if isinstance(res.get("reasons"), list) else []
    severity = res.get("severity") if isinstance(res.get("severity"), str) else "medium"
    confidence = res.get("confidence") if isinstance(res.get("confidence"), (int,float)) else 0.5
    evidence = res.get("evidence") if isinstance(res.get("evidence"), list) else []

    return {"description": description, "verdict": verdict, "reasons": reasons, "severity": severity, "confidence": confidence, "evidence": evidence}
