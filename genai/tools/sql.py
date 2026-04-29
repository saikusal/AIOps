import json
import re
from typing import Callable, Dict, List, Optional, Tuple


def handle_sql(
    prompt: str,
    *,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    get_full_schema_for_prompt: Callable[..., str],
    target_table: str,
    extract_sql_from_markdown: Callable[[str], str],
    strip_after_stop_tokens: Callable[[str], str],
    ensure_select_prefix: Callable[[str], str],
    quote_text_literals: Callable[[str], str],
    prefer_ilike_for_strings: Callable[[str], str],
    extract_selected_columns: Callable[[str], List[str]],
    suggest_visualization: Callable[[List[str], List[Tuple]], dict],
    rows_to_json_safe_lists: Callable[[List[Tuple]], List[List]],
    safe_preview_value: Callable[[object, int], object],
    history_model,
    db_connection,
    forbidden_sql,
    logger,
) -> Tuple[Optional[dict], dict, str, str]:
    schema = get_full_schema_for_prompt(target_table=target_table, max_tables=6, sample_rows_limit=0, max_total_chars=3000)
    sql_system = (
        "You are a PostgreSQL SQL generator. Return exactly ONE valid SQL SELECT statement only.\n"
        "Use ONLY the exact column names present in the schema below. If impossible to answer, return exactly: SELECT 'NOT_POSSIBLE' AS note;\n"
        "Return SQL only (no explanation)."
    )
    full_prompt = f"{sql_system}\n\nSCHEMA:\n{schema}\n\nQUESTION: {prompt}\nSQL:"
    ok, _status, body = llm_query(full_prompt)
    logger.info("LLM raw for SQL prompt: %s", (body or "")[:1000])
    if not ok:
        return None, {}, "Error: AI service failed.", ""

    raw_text = (body or "").strip()
    candidate = extract_sql_from_markdown(raw_text)
    candidate = strip_after_stop_tokens(candidate)
    candidate = ensure_select_prefix(candidate)
    candidate = quote_text_literals(candidate)
    generated_sql = prefer_ilike_for_strings(candidate.strip())
    if not generated_sql.endswith(";"):
        generated_sql = generated_sql + ";"
    logger.info("Generated SQL (trimmed): %.500s", generated_sql)

    normalized_q = " ".join(prompt.lower().split())
    try:
        history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": "Pending"})
    except Exception:
        logger.exception("Failed to persist generated_sql early.")

    if forbidden_sql.search(generated_sql):
        err = "Error: Generated forbidden SQL statement."
        try:
            history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist forbidden SQL error.")
        return None, {}, err, generated_sql

    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [target_table])
            valid_cols = [r[0] for r in cursor.fetchall()]
    except Exception:
        valid_cols = []
        logger.exception("Failed to fetch valid columns for validation.")

    selected_cols = extract_selected_columns(generated_sql)
    logger.info("Selected columns: %s", selected_cols)
    if selected_cols and "*" not in selected_cols:
        invalid = [col for col in selected_cols if col and col not in valid_cols]
        if invalid:
            err = f"Error: Query uses unknown columns: {', '.join(invalid)}"
            try:
                history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
            except Exception:
                logger.exception("Failed to persist invalid-columns error.")
            return None, {}, err, generated_sql

    try:
        with db_connection.cursor() as cursor:
            cursor.execute("EXPLAIN " + generated_sql)
    except Exception as exc:
        logger.exception("EXPLAIN failed: %s", exc)
        err = "Error: Invalid SQL generated; please rephrase."
        try:
            history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist EXPLAIN error.")
        return None, {}, err, generated_sql

    try:
        safe_sql = generated_sql if re.search(r"\blimit\b", generated_sql, flags=re.IGNORECASE) else generated_sql.rstrip(";") + " LIMIT 1000;"
        with db_connection.cursor() as cursor:
            cursor.execute(safe_sql)
            cols = [col[0] for col in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            results = {"columns": cols, "rows": rows}
    except Exception as exc:
        logger.exception("DB execution failed: %s", exc)
        err = "Error: DB execution failed."
        try:
            history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist DB exec error.")
        return None, {}, err, generated_sql

    vis = suggest_visualization(results["columns"], results["rows"])
    answer_blob = {
        "rows_count": len(results["rows"]),
        "preview": [{c: safe_preview_value(v, 80) for c, v in zip(results["columns"], row)} for row in results["rows"][:5]],
        "visualization": vis,
    }
    try:
        history_model.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": json.dumps(answer_blob)})
    except Exception:
        logger.exception("Failed to persist successful SQL run.")

    results_json_safe = {"columns": results["columns"], "rows": rows_to_json_safe_lists(results["rows"])}
    return results_json_safe, vis, "", generated_sql
