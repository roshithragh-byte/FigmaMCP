# Functional QA Report: Governed Figma Agent Gateway

**Date:** 2026-11-22T01:26:00Z  
**Surface:** API & Streamable HTTP MCP Server  
**Revision:** `82d0dcd` (`main`)  
**Status:** PASS (0 failing, 25/25 automated tests passed, 6/6 system functional probes passed)  

---

## 1. System Boundaries & Target Scope

- **Target:** `figma-mcp-server`
- **Interfaces Probed:**
  1. `/healthz` HTTP GET probe (Cloud Run liveness/readiness).
  2. `/mcp` Streamable HTTP SSE transport (JSON-RPC 2.0).
  3. FastMCP tool registry & execution surface (7 tools).
  4. Governance gates (`FIGMA_READ_ONLY`, `FIGMA_ALLOWED_FILE_KEYS`).
  5. Performance & Resource management (`compact_figma_node`, `TTLCache`, `SingleFlight`).
  6. Parameter validation & schema enforcement (Pydantic / FastMCP error boundaries).

---

## 2. Functional Contract Probes Summary

| ID | Contract Tested | Setup & Inputs | Expected Behavior | Observed Outcome | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PROBE-1** | Health Check (`/healthz`) | Standard Settings, `GET /healthz` | HTTP 200, `{"status": "ok"}` | HTTP 200 `{"status": "ok"}` | **PASS** |
| **PROBE-2** | Streamable HTTP Protocol | `POST /mcp` with `initialize` & `tools/list` | SSE event stream returning 7 tool definitions | HTTP 200 SSE stream with all 7 tools listed | **PASS** |
| **PROBE-3a** | Read-Only Gate | `read_only=True`, `post_file_comment` call | Block mutation, HTTP 403 error payload | HTTP 403 `Figma MCP server is running in read-only mode` | **PASS** |
| **PROBE-3b** | File Allowlist Gate | `allowed_file_keys=('allowed_1',)`, call on `unauthorized_3` | Block access, HTTP 403 error payload | HTTP 403 `Access to file 'unauthorized_3' is not allowed` | **PASS** |
| **PROBE-4** | AST Pruning & Cache Immutability | `get_figma_nodes` with `compact=True` then `compact=False` | Prune vectorData on call 1; keep uncompacted vectorData on call 2 | Call 1 returned pruned AST; Call 2 returned full vector data from cache | **PASS** |
| **PROBE-5** | TTLCache & SingleFlight Coalescing | Concurrent calls to identical key during slow fetch; maxsize=2; TTL=0.2s | Coalesce to 1 upstream call; evict LRU key; expire on TTL | 1 call executed for 2 concurrent tasks; LRU evicted k2; expired on TTL | **PASS** |
| **PROBE-6** | Input Validation Boundary | Scale -1.0; empty node_ids; invalid format 'exe' | Reject with HTTP 400 / ToolError without crashing server | Pydantic validation rejected all invalid inputs cleanly | **PASS** |

---

## 3. Automated Test Suite Execution

```text
============================= test session starts ==============================
collected 25 items

tests/test_cache.py::test_ttl_cache_basic_get_set PASSED                 [  4%]
tests/test_cache.py::test_ttl_cache_expiration PASSED                    [  8%]
tests/test_cache.py::test_ttl_cache_lru_eviction PASSED                  [ 12%]
tests/test_cache.py::test_single_flight_coalescing PASSED                [ 16%]
tests/test_cache.py::test_ttl_cache_force_refresh PASSED                 [ 20%]
tests/test_client.py::test_settings_fail_fast_when_token_missing PASSED  [ 24%]
tests/test_client.py::test_settings_invalid_port PASSED                  [ 28%]
tests/test_client.py::test_settings_repr_hides_token PASSED              [ 32%]
tests/test_client.py::test_input_validation_rejects_bad_inputs PASSED    [ 36%]
tests/test_client.py::test_client_sends_token_header_and_calls_all_endpoints PASSED [ 40%]
tests/test_client.py::test_client_handles_http_errors_cleanly[401] PASSED [ 44%]
tests/test_client.py::test_client_handles_http_errors_cleanly[403] PASSED [ 48%]
tests/test_client.py::test_client_handles_http_errors_cleanly[404] PASSED [ 52%]
tests/test_client.py::test_client_handles_http_errors_cleanly[429] PASSED [ 56%]
tests/test_compactor.py::test_compact_figma_node_prunes_vector_and_transforms PASSED [ 60%]
tests/test_compactor.py::test_compact_figma_node_deep_recursion_safety PASSED [ 64%]
tests/test_compactor.py::test_compact_figma_node_schema_resilience PASSED [ 68%]
tests/test_server.py::test_healthz_endpoint PASSED                       [ 72%]
tests/test_server.py::test_mcp_lists_all_seven_tools PASSED              [ 76%]
tests/test_server.py::test_mcp_tool_execution_and_error_handling PASSED  [ 80%]
tests/test_server.py::test_streamable_http_list_tools_over_http PASSED   [ 84%]
tests/test_server.py::test_read_only_mode_blocks_post_comment PASSED     [ 88%]
tests/test_server.py::test_allowed_file_keys_rejection PASSED            [ 92%]
tests/test_server.py::test_get_figma_nodes_compact_mode PASSED           [ 96%]
tests/test_server.py::test_allowed_file_keys_success_and_read_only_false PASSED [100%]

======================== 25 passed, 1 warning in 0.49s =========================
```

---

## 4. Defect Findings & Fixes

**Zero active defects.** All potential regressions identified during the review phase (cache mutation, task GC in SingleFlight, container memory bounding) have been verified fixed and immune to recurrence.
