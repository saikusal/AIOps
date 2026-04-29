import json
from typing import Callable, Dict, Tuple


def handle_general_chat(
    question: str,
    conversation_history: str,
    *,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    history_model,
    cache_store,
    logger,
) -> Dict[str, object]:
    prompt = (
        "You are a helpful assistant. Your response MUST be a single JSON object with two keys: 'answer' and 'follow_up_questions'.\n"
        "- 'answer': A string containing the direct answer to the user's question.\n"
        "- 'follow_up_questions': A list of 3-4 relevant follow-up questions a user might ask next.\n\n"
        f"RECENT CONVERSATION:\n{conversation_history or 'No prior conversation.'}\n\n"
        f"QUESTION: {question}\n\nJSON Response:"
    )
    ok, _status, body_text = llm_query(prompt)
    if not ok:
        raise RuntimeError(body_text)

    try:
        start_index = body_text.find("{")
        end_index = body_text.rfind("}")
        if start_index != -1 and end_index != -1:
            response_data = json.loads(body_text[start_index:end_index + 1])
        else:
            response_data = {"answer": body_text, "follow_up_questions": []}
        answer = response_data.get("answer", body_text)
        follow_ups = response_data.get("follow_up_questions", [])
    except json.JSONDecodeError:
        answer = body_text
        follow_ups = []

    response_data = {"question": question, "answer": answer, "follow_up_questions": follow_ups, "cached": False}
    try:
        history_model.objects.update_or_create(question=question, defaults={"answer": answer})
        cache_store.add(question, response_data)
    except Exception:
        logger.exception("Failed to persist or cache general chat history.")
    return response_data
