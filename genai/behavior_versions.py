import os
from typing import Any, Dict


def current_behavior_version_payload() -> Dict[str, Any]:
    return {
        "name": os.getenv("AIOPS_AGENT_BEHAVIOR_NAME", "default"),
        "prompt_version": os.getenv("AIOPS_PROMPT_VERSION", "prompt-v1"),
        "policy_version": os.getenv("AIOPS_POLICY_VERSION", "policy-v1"),
        "model_version": os.getenv("AIOPS_MODEL_VERSION", os.getenv("VLLM_MODEL_NAME", "vllm")),
        "evidence_rules_version": os.getenv("AIOPS_EVIDENCE_RULES_VERSION", "evidence-v1"),
        "ranking_version": os.getenv("AIOPS_RANKING_VERSION", "ranking-v1"),
        "metadata_json": {
            "llm_backend": "vllm",
            "vllm_model_name": os.getenv("VLLM_MODEL_NAME", ""),
        },
    }
