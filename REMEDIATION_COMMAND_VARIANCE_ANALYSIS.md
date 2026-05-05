# AIOps Remediation Command Variance Issue

## Problem Summary
The LLM is generating **different remediation commands for the same alert** on repeated calls. This causes inconsistent behavior and makes incident response unpredictable.

## Root Cause Analysis

### 1. **Non-Deterministic Temperature Settings**
**Location:** [`genai/llm_backend.py` Line 50](genai/llm_backend.py#L50)

```python
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.1"))
```

- **Current default:** `0.1` (allows randomness/variation)
- **Impact:** Each LLM call samples differently, producing varied outputs even with identical inputs
- **Applied in payload:** [`genai/llm_backend.py` Line 244](genai/llm_backend.py#L244)

### 2. **Analysis Prompt Construction**
**Location:** [`genai/views.py` Line 1980-2005](genai/views.py#L1980-L2005)

The `analyze_command_output()` function sends the same alert context to the LLM, but receives different remediation commands because:
- No random seed is set
- Temperature allows sampling-based generation
- Each call explores different parts of the probability distribution

### 3. **Missing Result Caching**
**Location:** [`genai/views.py` Line 3745-3900](genai/views.py#L3745-L3900)

The system stores alert recommendations in cache (line 3829-3854: `_store_recent_alert_recommendation()`), but:
- The cache is only checked for **future occurrences** of the same alert
- Within a single processing cycle, multiple LLM calls can happen
- No immediate caching of remediation results for quick lookup

## Solution: Three-Pronged Approach

### Solution 1: Set Temperature to 0 for Deterministic Responses ✅ CRITICAL

**File:** `genai/llm_backend.py`

**Change 1:**
```python
# Line 50 - Change default temperature
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))  # Changed from 0.1 to 0.0
```

**Change 2:** Add temperature parameter to the vLLM request payload (Line 103)
```python
payload = {
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.0,  # Add explicit temperature for vLLM
}
```

**Rationale:**
- Temperature = 0 means greedy decoding (always pick highest probability token)
- Guarantees deterministic output for identical inputs
- No randomness = consistent remediation decisions

### Solution 2: Add Remediation Command Caching Layer

**File:** `genai/views.py`

**In `analyze_command_output()` function (after Line 1940):**

```python
def _get_cached_remediation(alert_name: str, target_host: str, command_output_hash: str) -> Optional[Dict[str, Any]]:
    """Check if we already analyzed this exact command output."""
    cache_key = f"remediation_{alert_name}_{target_host}_{command_output_hash}"
    return cache.get(cache_key)

def _cache_remediation(alert_name: str, target_host: str, command_output_hash: str, result: Dict[str, Any]) -> None:
    """Store remediation analysis for 1 hour."""
    cache_key = f"remediation_{alert_name}_{target_host}_{command_output_hash}"
    cache.set(cache_key, result, 3600)
```

**Usage in `analyze_command_output()`:**
```python
# Add after creating the analysis_prompt (around line 2000)
import hashlib
command_output_hash = hashlib.md5(command_output.encode()).hexdigest()[:8]
alert_name = context.get("alert_name", "unknown")

cached_result = _get_cached_remediation(alert_name, target_host, command_output_hash)
if cached_result:
    logger.info("Using cached remediation for %s", alert_name)
    return True, cached_result.get("answer", ""), cached_result
```

### Solution 3: Track Remediation Variance for Monitoring

**File:** `genai/views.py` (Add new helper function)

```python
def _log_remediation_variance(alert_name: str, target_host: str, 
                               previous_command: Optional[str], 
                               new_command: str) -> None:
    """Alert if remediation recommendations change for the same alert."""
    if previous_command and previous_command != new_command:
        logger.warning(
            "REMEDIATION_VARIANCE_DETECTED | alert=%s | target=%s | "
            "previous=%s | new=%s",
            alert_name, target_host, previous_command, new_command
        )
        # Could send to monitoring system
```

## Implementation Checklist

- [ ] **Step 1:** Update `VLLM_TEMPERATURE` default to `0.0` in `.env` or `llm_backend.py` Line 50
- [ ] **Step 2:** Add temperature parameter to the vLLM payload in `llm_backend.py` Lines 100-105
- [ ] **Step 3:** Add caching helper functions in `genai/views.py` 
- [ ] **Step 4:** Integrate cache checking in `analyze_command_output()` 
- [ ] **Step 5:** Add variance logging for monitoring/debugging
- [ ] **Step 6:** Test with same alert fired multiple times → verify identical commands
- [ ] **Step 7:** Update environment variables documentation

## Environment Variable Configuration

Add/Update `.env`:
```bash
# Force deterministic remediation
VLLM_TEMPERATURE=0.0
VLLM_MAX_TOKENS=2048
VLLM_TEMPERATURE=0.0
```

## Verification Plan

1. **Determinism Test:**
   ```bash
   # Fire same alert 3 times using test endpoint
   # Verify remediation_command field is identical in all responses
   ```

2. **Cache Hit Test:**
   - Trigger alert → analyze command → stores cache
   - Same command output → should hit cache within 1 hour

3. **Regression Test:**
   - Verify quality of recommendations doesn't degrade with T=0
   - Monitor error rates in command execution

## Expected Impact

- ✅ **Consistency:** Same alert always → same remediation command
- ✅ **Predictability:** Ops teams can rely on consistent recommendations  
- ✅ **Cost:** Fewer LLM fallthrough attempts due to caching
- ✅ **Reliability:** Reduced variance-induced errors

## Related Code Locations

- Alert processing: `genai/views.py` → `ingest_alert_view()` (L3745)
- Command analysis: `genai/views.py` → `analyze_command_output()` (L1940)  
- Remediation coercion: `genai/views.py` → `_coerce_remediation_command()` (L1467)
- LLM backends: `genai/llm_backend.py` (L30-310)
- Recent alert cache: `genai/views.py` → `_store_recent_alert_recommendation()` (L1595)
