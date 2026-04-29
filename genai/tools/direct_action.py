import json
from typing import Callable, Optional, Tuple


def handle_direct_action(
    prompt: str,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    logger,
) -> Tuple[Optional[dict], str]:
    """
    Convert a direct action request into a safe command proposal.
    Returns a dictionary with the command and target host, or an error string.
    """
    action_prompt = (
        "You are a system administrator's assistant. Your task is to convert a user's request into a single, safe Linux command. "
        "1.  **Identify the Action:** Determine if the user wants to list files (`ls`), delete a file (`rm`), or another simple file operation. "
        "2.  **Identify the Target:** Extract the target server's IP address or hostname. "
        "3.  **Identify the Path:** Extract the file or directory path. "
        "4.  **Assess Risk:** Determine if the command is destructive (e.g., `rm`, `find -delete`). "
        "5.  **Be Verbose:** For any destructive action, ensure the command produces output. Use verbose flags (e.g., `rm -v`) or print flags (e.g., `find ... -print -delete`). "
        "6.  **Handle Compound Requests:** If the user asks to show and then delete, combine the commands with a semicolon (e.g., `ls -l /some/dir; find /some/dir -name '*.log' -delete`)."
        "7.  **Format Output:** Return a JSON object with three keys: 'command' (string), 'target_host' (string), and 'is_destructive' (boolean). "
        "Return ONLY the JSON object.\n\n"
        "--- EXAMPLES ---\n"
        "User: 'list files in /var/log on server 10.1.10.5' -> {\"command\": \"ls -l /var/log\", \"target_host\": \"10.1.10.5\", \"is_destructive\": false}\n"
        "User: 'delete the file /tmp/error.log on the server 192.168.1.100' -> {\"command\": \"rm -v /tmp/error.log\", \"target_host\": \"192.168.1.100\", \"is_destructive\": true}\n"
        "User: 'show me the contents of /etc and delete all .tmp files there on server web-01' -> {\"command\": \"ls -l /etc; find /etc -name '*.tmp' -print -delete\", \"target_host\": \"web-01\", \"is_destructive\": true}\n\n"
        f"--- TASK ---\n"
        f"Generate the JSON for this request: '{prompt}'"
    )

    ok, _status, body = llm_query(action_prompt)
    if not ok:
        return None, "Sorry, I couldn't understand that command. Please try rephrasing."

    try:
        start_index = body.find("{")
        end_index = body.rfind("}")
        if start_index == -1 or end_index == -1:
            return None, "Sorry, I failed to generate a valid command structure."

        response_data = json.loads(body[start_index:end_index + 1])
        if "command" in response_data and "target_host" in response_data:
            return response_data, ""
        return None, "Sorry, I understood the request but couldn't determine the exact command or target server."
    except json.JSONDecodeError:
        logger.exception("Failed to decode JSON from direct action prompt.")
        return None, "Sorry, there was an issue interpreting the command."
