from typing import Any, Dict


def build_docs_proxy_body(body: Dict[str, Any], question: str, top_k: int, strict_docs: bool) -> Dict[str, Any]:
    proxy_body = body.copy()
    proxy_body.update({
        "query": question,
        "top_k": top_k,
        "use_documents": True,
        "strict_docs": strict_docs,
    })
    return proxy_body
