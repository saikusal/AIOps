# doc_search/views.py
import os
import re
import json
import logging
import traceback
import tempfile
import time
import shutil
import subprocess
import threading
from typing import List, Tuple

from pathlib import Path
from io import BytesIO

from PIL import Image
import requests
from bs4 import BeautifulSoup
import cv2
import base64

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.core.files.base import ContentFile
from django.conf import settings

# text/pipeline libraries
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# file parsing libraries
try:
    import docx as python_docx  # python-docx (rename to avoid name conflict)
except Exception:
    python_docx = None

try:
    import fitz  # PyMuPDF for PDF images/text
except Exception:
    fitz = None

# optional OLE parser to try extract images from legacy .doc files (best-effort)
try:
    import olefile
except Exception:
    olefile = None

# Import your models and forms (adjust import path as needed)
from .models import Document, DocumentChunk, DocumentImage
from .forms import DocumentForm
from genai.models import GenAIChatHistory
from genai.views import genai_chat as general_llm_chat_fallback
from genai.semantic_cache import simple_cache
logger = logging.getLogger("doc_search")
logger.setLevel(logging.INFO)

# Config (env)
AIDE_API_URL = os.getenv("AIDE_API_URL")  # completions endpoint (completions route)
AIDE_API_KEY = os.getenv("AIDE_API_KEY")
VERIFY_SSL = os.getenv("AIDE_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
AIDE_TIMEOUT = int(os.getenv("AIDE_TIMEOUT", "60"))

CONFLUENCE_BASE = os.getenv("CONFLUENCE_BASE")  # e.g. https://your-org.atlassian.net/wiki
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")

TFIDF_MAX_FEATURES = int(os.getenv("TFIDF_MAX_FEATURES", "20000"))

# ----------------- helpers: file text & image extraction -----------------

def _extract_text_from_docx_bytes(document: Document, data: bytes) -> str:
    """
    Extract text and images from .docx bytes (python-docx).
    Saves images to DocumentImage model as PNG bytes.
    Returns extracted plain text (joined paragraphs).
    """
    if python_docx is None:
        raise RuntimeError("python-docx not installed")

    f = BytesIO(data)
    try:
        doc = python_docx.Document(f)
    except Exception as e:
        logger.exception("python-docx failed to open .docx bytes: %s", e)
        return ""

    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]

    # Extract images via doc.part.rels
    try:
        rels = doc.part.rels
    except Exception:
        rels = {}

    img_count = 0
    for rel in getattr(doc.part, "rels", {}).values():
        try:
            if "image" in rel.target_ref.lower():
                img_data = rel.target_part.blob
                # Filter out small images
                try:
                    with Image.open(BytesIO(img_data)) as pil_img:
                        width, height = pil_img.size
                        if width < 100 or height < 100:
                            logger.info(f"Skipping small image ({width}x{height}) from doc {document.id}")
                            continue
                except Exception:
                    logger.warning("Could not parse image to check dimensions; skipping.")
                    continue

                img_name = f"doc_{document.id}_img_{img_count}.png"
                DocumentImage.objects.create(
                    document=document,
                    image=ContentFile(img_data, name=img_name)
                )
                img_count += 1
        except Exception:
            # defensive: ignore any single image failure
            logger.exception("Failed to save docx image for doc %s", document.id)
            continue

    return "\n".join(paragraphs)


def _extract_text_from_pdf_bytes(document: Document, data: bytes) -> str:
    """
    Use PyMuPDF (fitz) to extract text and page images from PDF bytes.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) not installed")

    text_parts = []
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page_num, page in enumerate(doc):
                try:
                    page_text = page.get_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception:
                    logger.exception("Failed to extract text from page %s of pdf doc %s", page_num, document.id)

                # images
                try:
                    for img_index, img in enumerate(page.get_images(full=True)):
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image.get("image")
                        if image_bytes:
                            # Filter out small images (likely logos/icons)
                            try:
                                with Image.open(BytesIO(image_bytes)) as pil_img:
                                    width, height = pil_img.size
                                    if width < 100 or height < 100:
                                        logger.info(f"Skipping small image ({width}x{height}) from doc {document.id}")
                                        continue
                            except Exception:
                                # If we can't parse it, probably best to skip
                                logger.warning("Could not parse image to check dimensions; skipping.")
                                continue

                            img_name = f"doc_{document.id}_page_{page_num}_img_{img_index}.png"
                            DocumentImage.objects.create(
                                document=document,
                                image=ContentFile(image_bytes, name=img_name),
                                page_number=page_num + 1
                            )
                except Exception:
                    logger.exception("Failed to extract images from PDF page %s for doc %s", page_num, document.id)
    except Exception:
        logger.exception("Failed to open pdf bytes for doc %s", document.id)
    return "\n".join(text_parts)


def _extract_images_from_ole_doc_bytes(document: Document, data: bytes) -> int:
    """
    Best-effort attempt to parse OLE .doc and pull embedded images using olefile.
    Returns number of images created. Not robust for all .doc variants.
    """
    if olefile is None:
        logger.debug("olefile not installed; skipping OLE fallback")
        return 0

    created = 0
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".doc")
        tmp.write(data)
        tmp.close()
        of = olefile.OleFileIO(tmp.name)
        streams = of.listdir(streams=True, storages=False)
        for s in streams:
            try:
                raw = of.openstream(s).read()
                if raw.startswith(b"\xff\xd8\xff"):  # jpg
                    ext = "jpg"
                elif raw.startswith(b"\x89PNG\r\n\x1a\n"):
                    ext = "png"
                else:
                    continue
                img_name = f"doc_{document.id}_ole_{created}.{ext}"
                DocumentImage.objects.create(document=document, image=ContentFile(raw, name=img_name))
                created += 1
            except Exception:
                continue
        of.close()
    except Exception:
        logger.exception("OLE extraction fallback failed for doc %s", document.id)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    return created


def _convert_doc_bytes_to_docx(data: bytes, tmp_dir: str = None, timeout: int = 30) -> str:
    """
    Convert .doc bytes to a .docx file using LibreOffice (soffice).
    Returns path to the converted .docx file.
    Raises RuntimeError on failure.
    Caller is responsible for cleaning up tmp_dir if created here.
    """
    created_tmp = False
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="docconv_")
        created_tmp = True

    try:
        in_path = os.path.join(tmp_dir, f"upload_{int(time.time()*1000)}.doc")
        with open(in_path, "wb") as wf:
            wf.write(data)

        # try conversion
        cmd = ["soffice", "--headless", "--convert-to", "docx", "--outdir", tmp_dir, in_path]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except FileNotFoundError:
            raise FileNotFoundError("LibreOffice 'soffice' binary not found in PATH")

        if proc.returncode != 0:
            # include stdout/stderr in error
            raise RuntimeError(f"LibreOffice conversion failed rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

        # expect output file with same base name but .docx
        base = Path(in_path).stem
        out_path = os.path.join(tmp_dir, base + ".docx")
        if os.path.exists(out_path):
            return out_path

        # fallback: search for any docx file in tmp_dir
        for f in os.listdir(tmp_dir):
            if f.lower().endswith(".docx"):
                return os.path.join(tmp_dir, f)

        raise RuntimeError("Converted .docx file not found after soffice conversion")
    except Exception:
        # propagate exception to caller for fallback logic
        raise
    finally:
        # We DO NOT auto-delete tmp_dir here; caller can remove it after reading out file
        pass


def _extract_text_from_doc_bytes(document: Document, data: bytes) -> str:
    """
    Primary function to extract text from legacy .doc bytes and save any images.
    Strategy:
      1) Try LibreOffice conversion to .docx, then call _extract_text_from_docx_bytes on converted bytes.
      2) Fallback to 'catdoc' (if available) for text-only extraction.
      3) As last resort, try naive decoding plus OLE-based image extraction (best-effort).
    """
    # Attempt 1: libreoffice conversion
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="docconv_")
        out_docx = _convert_doc_bytes_to_docx(data, tmp_dir=tmp_dir, timeout=30)
        # read converted docx bytes
        with open(out_docx, "rb") as f:
            docx_bytes = f.read()
        # call docx extractor (which will save images)
        text = _extract_text_from_docx_bytes(document, docx_bytes)
        return text
    except FileNotFoundError:
        # soffice not present
        logger.warning("LibreOffice 'soffice' not found; skipping conversion.")
    except Exception as e:
        logger.exception("DOC -> DOCX conversion failed: %s", e)

    # Attempt 2: catdoc (text only)
    try:
        proc = subprocess.run(['catdoc', '-'], input=data, capture_output=True, text=True, check=True)
        return proc.stdout
    except FileNotFoundError:
        logger.warning("`catdoc` not installed; cannot use it to extract text from .doc")
    except subprocess.CalledProcessError as e:
        logger.warning("`catdoc` failed: %s", e)

    # Attempt 3: best-effort decode + OLE image extraction
    try:
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            text = data.decode('latin-1', errors='replace')

        # try to save any images with OLE fallback
        _extract_images_from_ole_doc_bytes(document, data)
        return text
    except Exception as e:
        logger.exception("Final fallback for .doc extraction failed: %s", e)

    finally:
        # cleanup tmp_dir if created
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

    return ""


def call_aide_vision_completions(prompt: str, base64_images: List[str], timeout: int = 120):
    """
    Wrapper to call a vision-enabled AiDE completions endpoint.
    """
    if not AIDE_API_URL or not AIDE_API_KEY:
        return False, {"error": "AIDE_API_URL or AIDE_API_KEY not configured"}
    
    headers = {"Authorization": f"Bearer {AIDE_API_KEY}", "Content-Type": "application/json"}
    
    # Construct the messages payload with images
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt}
            ]
        }
    ]
    for b64_img in base64_images:
        messages[0]["content"].append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_img}"
            }
        })

    # NOTE: This assumes your vision model is available at the same base URL.
    # You may need a different URL or model name.
    payload = {"messages": messages, "model": "aide-vision"} 

    try:
        r = requests.post(AIDE_API_URL, headers=headers, json=payload, timeout=timeout, verify=VERIFY_SSL)
    except Exception as e:
        logger.exception("AIDE Vision request error: %s", e)
        return False, {"error": str(e)}

    try:
        j = r.json()
    except Exception:
        return False, {"error": f"Non-json response {r.status_code}", "text": r.text[:2000]}

    if r.status_code >= 400:
        return False, {"error": f"AIDE Vision HTTP {r.status_code}", "body": j}

    try:
        if isinstance(j, dict) and "choices" in j and j["choices"]:
            ch = j["choices"][0]
            if isinstance(ch.get("message"), dict):
                return True, {"text": ch["message"].get("content"), "raw": j}
        return True, {"text": json.dumps(j)[:4000], "raw": j}
    except Exception:
        return True, {"text": json.dumps(j)[:4000], "raw": j}


def _analyze_visual_media(document: Document, data: bytes, ext: str, max_frames=5) -> str:
    """
    Analyzes an image or video file by sending it to a multimodal AI
    and returns a text description.
    For videos, it extracts keyframes to send.
    """
    logger.info(f"Analyzing visual media for document {document.id} (type: {ext})")
    base64_images = []

    if ext in ('mp4', 'mov', 'avi'):
        # Video processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp_video:
            tmp_video.write(data)
            video_path = tmp_video.name
        
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                frame_indices = np.linspace(0, total_frames - 1, num=min(max_frames, total_frames), dtype=int)

                for i in frame_indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                    ret, frame = cap.read()
                    if ret:
                        _, buffer = cv2.imencode('.jpg', frame)
                        base64_images.append(base64.b64encode(buffer).decode('utf-8'))
            cap.release()
        except Exception as e:
            logger.exception(f"Failed to process video frames for doc {document.id}: {e}")
            return ""
        finally:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.unlink(video_path)

    elif ext in ('png', 'jpg', 'jpeg'):
        # Image processing
        base64_images.append(base64.b64encode(data).decode('utf-8'))
    
    else:
        return "" # Should not happen if called correctly

    if not base64_images:
        logger.warning(f"No images/frames extracted for visual media doc {document.id}")
        return ""

    prompt = "Describe the content of this image/these video frames in detail. What is happening? What objects are visible? If there is text, transcribe it."
    ok, resp = call_aide_vision_completions(prompt, base64_images)

    if not ok:
        logger.error(f"Vision AI analysis failed for doc {document.id}: {resp.get('error')}")
        return ""
    
    description = resp.get("text", "")
    logger.info(f"Vision AI generated description for doc {document.id}: {description[:200]}...")
    return description


def _safe_text_from_filefield(document: Document, file_field) -> str:
    """
    Accepts a Django FileField or UploadedFile. Detects by extension and delegates to proper extractor.
    Also saves images when extractor writes DocumentImage rows.
    """
    name = getattr(file_field, "name", "") or ""
    ext = name.lower().split(".")[-1]
    # read bytes
    try:
        # reset pointer if possible
        try:
            file_field.seek(0)
        except Exception:
            pass
        data = file_field.read()
    except Exception as e:
        logger.exception("Failed to read file bytes for document %s: %s", getattr(document, "id", None), e)
        return ""

    text = ""
    try:
        if ext in ('png', 'jpg', 'jpeg', 'mp4', 'mov', 'avi'):
            text = _analyze_visual_media(document, data, ext)
        elif ext == "doc":
            text = _extract_text_from_doc_bytes(document, data)
        elif ext in ("docx", "pptx", "xlsx"):
            # call docx extractor
            text = _extract_text_from_docx_bytes(document, data)
        elif ext == "pdf":
            text = _extract_text_from_pdf_bytes(document, data)
        else:
            # fallback: decode text
            text = data.decode("utf-8", errors="replace").replace("\x00", "")
    except Exception as e:
        logger.exception("Error extracting text from file %s: %s", name, e)
        # second chance: latin1
        try:
            text = data.decode("latin-1", errors="replace")
        except Exception:
            text = ""
    return text

# ----------------- helpers: text chunking -----------------
def chunk_text(text: str, chunk_size_words: int = 300, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size_words])
        chunks.append(chunk)
        i += chunk_size_words - overlap
    return chunks

# ----------------- helpers: Confluence fetching -----------------
def fetch_confluence_page_as_text(page_url: str) -> Tuple[str, dict]:
    """
    Fetch a Confluence page and return extracted text and metadata dict.
    page_url may be a full URL or a relative path; function expects CONFLUENCE_BASE + path if needed.
    """
    if not CONFLUENCE_BASE or not CONFLUENCE_USER or not CONFLUENCE_TOKEN:
        raise RuntimeError("Confluence credentials not configured in environment variables")

    # Normalize
    if page_url.startswith("/"):
        page_url = page_url[1:]
    if page_url.startswith("http"):
        full = page_url
    else:
        full = CONFLUENCE_BASE.rstrip("/") + "/" + page_url.lstrip("/")

    # If given a page web UI link, attempt to convert to REST API content endpoint:
    # (Confluence cloud page links often contain `/pages/viewpage.action?pageId=12345` or `/display/SPACE/<slug>`)
    # We'll attempt detection; if the provided full URL contains pageId query param, use REST API to fetch content.
    try:
        # naive parse for pageId
        from urllib.parse import urlparse, parse_qs
        u = urlparse(full)
        qs = parse_qs(u.query)
        page_id = qs.get("pageId", [None])[0]
        session = requests.Session()
        session.auth = (CONFLUENCE_USER, CONFLUENCE_TOKEN)
        headers = {"Accept": "application/json"}
        if page_id:
            api_url = f"{CONFLUENCE_BASE.rstrip('/')}/rest/api/content/{page_id}?expand=body.storage,version"
        else:
            # If this is already REST-like, use it; otherwise try to fetch the HTML and extract body
            if "/rest/api/content" in full and "expand=" in full:
                api_url = full
            else:
                # fallback: GET the page and extract visible HTML body
                r = session.get(full, auth=(CONFLUENCE_USER, CONFLUENCE_TOKEN), timeout=30, verify=VERIFY_SSL)
                r.raise_for_status()
                html = r.text
                text = BeautifulSoup(html, "html.parser").get_text(separator="\n")
                meta = {"source_url": full}
                return text, meta

        r = session.get(api_url, auth=(CONFLUENCE_USER, CONFLUENCE_TOKEN), headers=headers, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status()
        data = r.json()
        storage = data.get("body", {}).get("storage", {}).get("value", "")
        text = BeautifulSoup(storage, "html.parser").get_text(separator="\n")
        meta = {
            "source_url": full,
            "page_id": data.get("id"),
            "title": data.get("title"),
            "version": data.get("version", {}).get("number")
        }
        return text, meta
    except Exception as e:
        logger.exception("Failed to fetch Confluence page %s: %s", page_url, e)
        raise

# ----------------- index & retrieval (TF-IDF on-the-fly) -----------------
def build_tfidf_index(chunks: List[str], max_features: int = TFIDF_MAX_FEATURES):
    """
    Build TF-IDF vectorizer and term matrix for list of chunk texts.
    Returns (vectorizer, matrix)
    """
    vect = TfidfVectorizer(stop_words="english", max_features=max_features)
    X = vect.fit_transform(chunks)
    return vect, X

def query_tfidf(vectorizer, matrix, chunks, query, top_k=4):
    qv = vectorizer.transform([query])
    # compute similarity = dot product between matrix and qv
    sims = (matrix @ qv.T).toarray().reshape(-1)
    idxs = np.argsort(-sims)[:top_k]
    results = []
    for i in idxs:
        results.append((int(i), chunks[int(i)], float(sims[int(i)])))
    return results

# ----------------- AiDE calls -----------------
def get_embedding_aide(text: str, api_url: str, api_key: str, verify: bool = True) -> Tuple[bool, dict]:
    """
    Call embedding endpoint. Returns (ok, parsed_json_or_error_str)
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent":"asset-management/1.0"}
    payload = {"input": text}
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=30, verify=verify)
    except requests.exceptions.RequestException as e:
        return False, {"error": f"Request error: {e}"}
    try:
        data = r.json()
    except Exception:
        return False, {"error": f"Non-JSON response {r.status_code}: {r.text[:400]}"}
    if r.status_code >= 400:
        return False, {"error": f"HTTP {r.status_code}: {json.dumps(data)[:800]}"}
    return True, data

def extract_embedding_from_response(data) -> List[float]:
    """
    Extracts an embedding vector from various possible API response structures.
    """
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list) and data["data"]:
            first = data["data"][0]
            if isinstance(first, dict) and "embedding" in first:
                return list(first["embedding"])
        if "embedding" in data and isinstance(data["embedding"], list):
            return list(data["embedding"])
    return None

def call_aide_completions(prompt: str, timeout: int = None):
    """
    Wrapper to call the main AiDE API, which includes fallback logic.
    This avoids circular imports by importing locally.
    """
    from genai.views import query_aide_api

    ok, status, body_text = query_aide_api(prompt)

    if not ok:
        # The query_aide_api function already logs the error details.
        return False, {"error": f"AIDE call failed with status {status}", "detail": body_text}
    
    # The successful response from query_aide_api is the text content.
    # We wrap it in a dict to match the original expected format of this function.
    return True, {"text": body_text}

# ----------------- views -----------------
def document_manager(request: HttpRequest):
    """
    Document upload view — creates Document and triggers async chunk processing.
    """
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save()
            messages.success(request, "Uploaded; processing text to create chunks...")
            def _bg_worker(doc_id):
                try:
                    d = Document.objects.get(id=doc_id)
                    process_document_chunks(d)
                except Exception:
                    logger.exception("Background chunking failed for doc_id=%s", doc_id)
                    if 'd' in locals():
                        d.processing_status = 'FAILED'
                        d.save()
            transaction.on_commit(lambda: threading.Thread(target=_bg_worker, args=(doc.id,), daemon=True).start())
            return redirect('genai:genai_console')
    else:
        form = DocumentForm()
    documents = Document.objects.all().order_by("-uploaded_at")
    return render(request, "doc_search/document_manager.html", {"form": form, "documents": documents})


def delete_document(request, doc_id):
    if request.method == 'POST':
        doc = get_object_or_404(Document, id=doc_id)
        doc.delete()
        messages.success(request, 'Document deleted successfully.')
    return redirect('genai:genai_console')

def process_document_chunks(document: Document, chunk_size_words: int = 300, overlap: int = 50, overwrite: bool = False) -> int:
    """
    Extract text and images from Document.file and create DocumentChunk and DocumentImage rows.
    Returns number of chunks created.
    """
    if overwrite:
        document.chunks.all().delete()
        document.images.all().delete()

    # attempt to load file content
    file_field = document.file
    text = ""
    try:
        with file_field.open('rb') as f:
            text = _safe_text_from_filefield(document, f)
    except Exception as e:
        logger.exception("Could not read file content for document %s: %s", document.id, e)
        text = ""

    # fallback: try fetch from document.url if present
    if (not text or not text.strip()) and getattr(document, "url", None):
        try:
            r = requests.get(document.url, timeout=20, verify=VERIFY_SSL)
            r.raise_for_status()
            html = r.text
            text = BeautifulSoup(html, "html.parser").get_text(separator="\n")
        except Exception:
            logger.exception("Failed to fetch text from Document.url for document %s", document.id)

    if not text:
        logger.warning("No text extracted for document id=%s name=%s", document.id, getattr(document, "title", document.file.name))
        document.processing_status = "FAILED"
        try:
            document.save()
        except Exception:
            pass
        return 0

    chunks = chunk_text(text, chunk_size_words=chunk_size_words, overlap=overlap)
    created = 0

    for idx, chunk in enumerate(chunks):
        try:
            DocumentChunk.objects.create(
                document=document,
                chunk_text=chunk,
                chunk_index=idx,
            )
            created += 1
        except Exception:
            logger.exception("Failed to create chunk %s for document %s", idx, document.id)

    document.processing_status = 'SUCCESS'
    try:
        document.save()
    except Exception:
        logger.exception("Failed to save document processing status")

    logger.info("Created %d chunks for document %s", created, document.id)
    return created

@csrf_exempt
def ingest_confluence(request):
    """
    POST endpoint to ingest a Confluence page or space.
    Expected JSON:
    {
        "page_url": "https://...viewpage.action?pageId=12345"
    }
    OR
    {
        "space_key": "SPACEKEY"   # (optionally) to ingest recent pages from a space - simple implementation below
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
        page_url = body.get("page_url")
        space_key = body.get("space_key")
        created_docs = []
        if page_url:
            text, meta = fetch_confluence_page_as_text(page_url)
            # create Document record
            doc = Document.objects.create(title=meta.get("title", f"Confluence:{meta.get('page_id','unknown')}"), source_url=meta.get("source_url"), uploaded_by=None)
            # save text to a storage file so that process_document_chunks can optionally read it
            # Alternatively, create chunks directly
            chunks = chunk_text(text)
            for i, c in enumerate(chunks):
                DocumentChunk.objects.create(document=doc, chunk_text=c, chunk_index=i)
            created_docs.append({"doc_id": doc.id, "title": doc.title, "chunks": len(chunks)})
            return JsonResponse({"status": "ok", "created": created_docs})
        elif space_key:
            # naive: list content in space via REST API and ingest top N pages
            if not CONFLUENCE_BASE:
                return JsonResponse({"error": "CONFLUENCE_BASE not configured"}, status=500)
            session = requests.Session()
            session.auth = (CONFLUENCE_USER, CONFLUENCE_TOKEN)
            # get pages in the space (paginated)
            start = 0
            limit = 25
            while True:
                api = f"{CONFLUENCE_BASE.rstrip('/')}/rest/api/content?spaceKey={space_key}&limit={limit}&start={start}&expand=body.storage,version"
                r = session.get(api, auth=(CONFLUENCE_USER, CONFLUENCE_TOKEN), timeout=30, verify=VERIFY_SSL)
                r.raise_for_status()
                data = r.json()
                results = data.get("results", [])
                if not results:
                    break
                for page in results:
                    storage = page.get("body", {}).get("storage", {}).get("value", "")
                    text = BeautifulSoup(storage, "html.parser").get_text(separator="\n")
                    doc = Document.objects.create(title=page.get("title", "Confluence Page"), source_url=f"{CONFLUENCE_BASE.rstrip('/')}/pages/viewpage.action?pageId={page.get('id')}", uploaded_by=None)
                    chunks = chunk_text(text)
                    for i, c in enumerate(chunks):
                        DocumentChunk.objects.create(document=doc, chunk_text=c, chunk_index=i)
                    created_docs.append({"doc_id": doc.id, "title": doc.title, "chunks": len(chunks)})
                # pagination
                if "size" in data and data.get("size") < limit:
                    break
                start += limit
            return JsonResponse({"status": "ok", "created": created_docs})
        else:
            return JsonResponse({"error": "page_url or space_key required"}, status=400)
    except Exception as e:
        logger.exception("ingest_confluence error: %s", e)
        return JsonResponse({"error": str(e), "trace": traceback.format_exc()}, status=500)


def _clear_service_request_session(request, state_key):
    """
    Robustly clears ALL service request and pending-initiation state from the session
    to ensure a true reset. This now iterates through all session keys to be certain.
    """
    keys_to_delete = []
    # Find all keys related to service requests, regardless of session_id, to be safe.
    for key in list(request.session.keys()):
        if str(key).startswith('service_request_') or str(key).startswith('pending_sr_'):
            keys_to_delete.append(key)

    if keys_to_delete:
        for key in keys_to_delete:
            del request.session[key]
        logger.info(f"CRITICAL: Cleared comprehensive session state for keys: {keys_to_delete}")
        # Explicitly marking the session as modified is crucial to ensure the deletion is saved.
        request.session.modified = True
    else:
        logger.info(f"No service request state found in session to clear for base key {state_key}.")


def _normalize_for_matching(text: str) -> str:
    """A robust way to normalize strings for comparison by collapsing whitespace."""
    if not isinstance(text, str):
        return ""
    # Collapses all internal whitespace and removes leading/trailing spaces.
    return ' '.join(text.strip().lower().split())


@csrf_exempt
def service_request_handler(request: HttpRequest, original_query_override: str = None):
    """
    Manages the stateful conversation for creating a service request.
    This is a full state machine that handles conditional fields, executing one step per request.
    """
    return JsonResponse(
        {"answer": "Service request integration is disabled in this AIOps build."},
        status=400,
    )

@csrf_exempt
def search_documents(request: HttpRequest):
    """
    POST JSON:
    {
      "query": "text",
      "top_k": 4,
      "use_documents": true,
      "strict_docs": false,
      "session_id": "..."
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        body = json.loads(request.body or "{}")
    except Exception as e:
        logger.exception("search_documents: bad json: %s", e)
        return JsonResponse({"error": "invalid_json", "detail": str(e)}, status=400)

    logger.info(f"search_documents: Received body: {body}")

    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"error": "query_required"}, status=400)

    # --- DEFINITIVE FIX for Password Reset Flow ---
    # Replicate the password reset patterns from the main genai view to ensure
    # these queries are always routed to the old, dedicated handler.
    password_reset_patterns = [
        r'reset\s+(my\s+)?password',
        r'password\s+reset',
        r'forgot\s+(my\s+)?password',
        r'change\s+(my\s+)?password',
        r'update\s+(my\s+)?password',
        r'unlock\s+(my\s+)?account',
        r'account\s+locked',
        r'cant\s+login',
        r'login\s+issue',
        r'unable to login'
    ]
    if any(re.search(pattern, query, re.IGNORECASE) for pattern in password_reset_patterns):
        logger.warning(f"Password reset query detected. Routing '{query}' directly to genai_chat handler.")
        return general_llm_chat_fallback(request)

    session_id = body.get("session_id", "default_session")
    state_key = f"service_request_{session_id}"

    # --- UNIVERSAL CANCEL LOGIC ---
    # This is the highest priority. If the user wants to cancel, we reset everything.
    if query.lower() in ["cancel", "stop", "exit", "start over", "reset"]:
        _clear_service_request_session(request, state_key)
        # We also clear the simple_cache for this specific query to break any potential cache loops.
        simple_cache.delete(query)
        return JsonResponse({
            "answer": "Okay, I've cancelled the current request. The session will be cleared in 5 seconds.",
            "action": "reset_session"
        })
    
    def _to_bool(v, default=False):
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "y")
        return default

    use_documents = _to_bool(body.get("use_documents"), default=True)
    strict_docs = _to_bool(body.get("strict_docs"), default=False)
    try:
        top_k = int(body.get("top_k", 4))
    except Exception:
        top_k = 4

    logger.info("search_documents flags -> use_documents=%s, strict_docs=%s, top_k=%d, query='%s'",
                use_documents, strict_docs, top_k, query[:200])

    if not use_documents:
        logger.info("search_documents -> GENERAL LLM path for query: %s", query)
        prompt = f"You are a helpful assistant.\n\nQUESTION: {query}\n\nANSWER:"
        ok, resp = call_aide_completions(prompt)
        if not ok:
            logger.error("AIDE completion failed (general): %s", resp)
            return JsonResponse({"error": "AIDE_completion_failed", "detail": resp}, status=500)
        answer_text = resp.get("text") if isinstance(resp, dict) else str(resp)
        return JsonResponse({"question": query, "answer": answer_text, "sources": [], "raw_model": resp})

    # RAG path
    logger.info("search_documents -> DOCUMENT RAG path for query: %s (top_k=%d)", query, top_k)
    chunks_qs = DocumentChunk.objects.select_related("document").all()
    if not chunks_qs.exists():
        return JsonResponse({"error": "no_documents_indexed", "message": "No document chunks are present."}, status=400)

    chunk_texts = [c.chunk_text for c in chunks_qs]
    try:
        vectorizer, matrix = build_tfidf_index(chunk_texts)
    except Exception as e:
        logger.exception("Failed to build TF-IDF index: %s", e)
        return JsonResponse({"error": "tfidf_index_failed", "detail": str(e)}, status=500)

    try:
        top_results = query_tfidf(vectorizer, matrix, chunk_texts, query, top_k=top_k)
    except Exception as e:
        logger.exception("TF-IDF query failed: %s", e)
        return JsonResponse({"error": "tfidf_query_failed", "detail": str(e)}, status=500)

    # If no relevant documents are found and strict mode is off, fall back to the general chatbot.
    # This keeps RAG available while allowing broader assistant behavior by default.
    if not top_results or (top_results and top_results[0][2] < 0.1):
        logger.warning(f"No relevant documents found for query '{query[:100]}...'.")
        if not strict_docs:
            logger.info("search_documents -> GLOBAL fallback path for query: %s", query)
            body["use_documents"] = False
            request._body = json.dumps(body).encode("utf-8")
            return general_llm_chat_fallback(request)
        top_results = [] # Ensure top_results is empty

    # Get distinct document titles from the chunks queryset, and filter out None values
    all_titles = chunks_qs.values_list('document__title', flat=True)
    unique_titles = set(title for title in all_titles if title is not None)
    known_titles = sorted(list(unique_titles))
    logger.info("AI is aware of the following documents: %s", known_titles)

    # Build context + sources
    context_parts = []
    sources = []
    all_image_urls = []
    for idx, text_snippet, score in top_results:
        try:
            chunk_obj = chunks_qs[idx]
            images = DocumentImage.objects.filter(document=chunk_obj.document)
            image_urls = [request.build_absolute_uri(image.image.url) for image in images]
            all_image_urls.extend(image_urls)
        except Exception:
            chunk_obj = None
            image_urls = []

        src = {
            "chunk_id": getattr(chunk_obj, "id", None),
            "document_id": getattr(getattr(chunk_obj, "document", None), "id", None),
            "document_title": getattr(getattr(chunk_obj, "document", None), "title", None),
            "chunk_index": getattr(chunk_obj, "chunk_index", None),
            "score": float(score),
            "images": image_urls,
        }
        sources.append(src)
        context_parts.append(f"Source (doc: {src['document_title']}, idx: {src['chunk_index']}, score: {src['score']:.3f}):\n{text_snippet}")

    context = "\n\n---\n\n".join(context_parts)
    
    # Add image URLs to the context if any exist
    if all_image_urls:
        image_context = "\n\nIMAGES:\n" + "\n".join(all_image_urls)
        context += image_context

    base_prompt = (
        "You are an assistant answering a user question based on the provided context. "
        "Your response MUST be a single JSON object.\n"
        "1. If the answer is in the context, the JSON must have two keys:\n"
        "   - 'answer': A string containing the direct answer to the user's question, citing source document titles. If the context includes image URLs, display them using Markdown.\n"
        "   - 'follow_up_questions': A list of 3-4 relevant follow-up questions a user might ask next.\n"
        "2. If the answer is NOT in the context, the JSON must have two different keys:\n"
        "   - 'answer': The string 'I couldn't find an answer in the available documents. Please upload more documents or rephrase the question.'\n"
        "   - 'follow_up_questions': A list of 2-3 follow-up questions focused on the missing information.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {query}\n\n"
        "JSON Response:"
    )

    if strict_docs:
        # This instruction reinforces the rules in the base_prompt, ensuring the AI offers to create a ticket
        # when the answer is not in the context, while still restricting it to the provided documents.
        prompt = "You MUST answer using ONLY the provided context. Do not use any external knowledge. If the answer is not in the context, you MUST follow rule #2 in the instructions below precisely.\n" + base_prompt
    else:
        prompt = "You may supplement your answer with general knowledge if the context is insufficient.\n" + base_prompt

    ok, resp = call_aide_completions(prompt)
    if not ok:
        logger.error("AIDE completion failed (RAG): %s", resp)
        return JsonResponse({"error": "AIDE_completion_failed", "detail": resp}, status=500)

    try:
        # The response should be a JSON string.
        response_text = resp.get("text", "{}")
        # Clean the text to make sure it's valid JSON
        # Find the first '{' and the last '}'
        start_index = response_text.find('{')
        end_index = response_text.rfind('}')
        if start_index != -1 and end_index != -1:
            json_string = response_text[start_index:end_index+1]
            response_data = json.loads(json_string)
        else:
            # Fallback if no JSON object is found
            response_data = {"answer": response_text, "follow_up_questions": []}

        answer_text = response_data.get("answer", "Sorry, I couldn't formulate a response.")
        follow_up_questions = response_data.get("follow_up_questions", [])
        action = None

    except json.JSONDecodeError:
        logger.warning("Failed to decode JSON from AI response. Treating as plain text.")
        answer_text = resp.get("text", "Sorry, I received an invalid response from the AI.")
        follow_up_questions = []
        action = None
    except Exception as e:
        logger.exception("Error processing AI response: %s", e)
        answer_text = "An unexpected error occurred while processing the response."
        follow_up_questions = []
        action = None


    import markdown2
    answer_html = markdown2.markdown(answer_text)

    # Persist the interaction to history
    try:
        GenAIChatHistory.objects.update_or_create(
            question=query,
            defaults={'answer': answer_html}
        )
    except Exception as e:
        logger.exception("Failed to save RAG chat history for query: %s", query)

    response_data = {
        "question": query,
        "answer": answer_html,
        "sources": sources,
        "follow_up_questions": follow_up_questions,
        "action": action,
        "raw_model": resp,
        "debug_info": {"known_documents": known_titles},
        "cached": False
    }
    return JsonResponse(response_data)
