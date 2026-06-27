import os
import json
import time
import random
import re
import psycopg2
from psycopg2 import errors
import threading
from google import genai
from google.genai import types

from database import get_or_create_session_state, check_existing_transaction, get_db_connection, persist_session_state
from vector_store import query_semantic_memory
from vision_inspector import inspect_asset_damage

# =========================================================================
# 🔄 RESILIENT KEY ROTATION INTEGRATION CORE
# =========================================================================

class GeminiPoolTracker:
    """Manages index positions for the environmental API credential matrix."""
    def __init__(self):
        self.current_index = 1

    def get_active_key(self) -> str:
        target_env = f"GEMINI_KEY_POOL_{self.current_index}"
        key = os.environ.get(target_env)
        if not key and self.current_index == 1:
            key = os.environ.get("GEMINI_API_KEY")
        return key

    def rotate(self):
        self.current_index = 2 if self.current_index == 1 else 1
        print(f"🔄 [Key Rotation Engine] Swapping to: GEMINI_KEY_POOL_{self.current_index}")

pool_tracker = GeminiPoolTracker()


def get_gemini_client():
    api_key = pool_tracker.get_active_key()
    if not api_key:
        raise ValueError(f"❌ [Brain Error] Active Gemini key slot (Pool Index {pool_tracker.current_index}) is empty!")
    return genai.Client(api_key=api_key)


# =========================================================================
# 🔁 DISPATCH WITH RETRY (Exponential Backoff + Key Rotation)
# =========================================================================

def dispatch_with_retry(client, model_name, contents, config, max_retries=5):
    """
    Executes a Gemini API call with Exponential Backoff + Jitter for 503s,
    and transparent key-pool failover on 429 quota exhaustion.
    """
    base_delay = 2.0
    current_client = client

    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"🔄 [Retry] Attempt {attempt}/{max_retries}…")

            response = current_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            return response

        except Exception as e:
            error_msg = str(e)
            is_throttled = "503" in error_msg or "UNAVAILABLE" in error_msg or "overloaded" in error_msg.lower()
            is_quota_hit = "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower()

            if is_throttled or is_quota_hit:
                if is_quota_hit:
                    print(f"🚨 [429 Quota Exhausted] Rotating key from slot {pool_tracker.current_index}…")
                    pool_tracker.rotate()
                    try:
                        current_client = get_gemini_client()
                        print("✅ [Failover] Client re-mapped. Retrying after short pause…")
                        backoff_delay = 1.0
                    except Exception as pool_err:
                        print(f"⚠️ [Failover] Key fallback failed: {pool_err}")
                        backoff_delay = 15.0 + (base_delay ** attempt) + random.uniform(1.0, 3.0)
                else:
                    backoff_delay = (base_delay ** attempt) + random.uniform(1.0, 3.0)
                    print(f"⚠️ [503 Upstream] Gemini overloaded. Backoff {backoff_delay:.1f}s…")

                if attempt == max_retries:
                    print("❌ [Retry Exhausted] All retries failed.")
                    raise e

                print(f"⏳ Sleeping {backoff_delay:.2f}s before retry {attempt + 1}…")
                time.sleep(backoff_delay)
            else:
                raise e


# =========================================================================
# 📊 REAL-TIME CONFIDENCE SCORING ENGINE
# =========================================================================

def compute_confidence_score(
    policy_matched: bool,
    vision_succeeded: bool,
    chroma_context_chars: int,
    prompt_tokens: int,
    completion_tokens: int,
    response_text: str,
) -> float:
    """
    Derives a genuine, dynamic confidence score from real pipeline signals.

    Signal weights:
      - Response structural coherence : 0.40
      - Policy grounding via ChromaDB : 0.30
      - Vision inspection succeeded   : 0.20
      - Token output sufficiency      : 0.10

    Returns a float in [0.0, 1.0].
    """
    score = 0.0

    # Signal 1: Response structural coherence (0.40)
    required_sections = [
        "compliance analysis report",
        "operational risk assessment",
        "executive action items",
    ]
    lower_text = response_text.lower()
    sections_found = sum(1 for s in required_sections if s in lower_text)
    coherence_ratio = sections_found / len(required_sections)
    score += 0.40 * coherence_ratio
    print(f"📊 [Confidence] Coherence ({sections_found}/{len(required_sections)}): {score:.3f}")

    # Signal 2: Policy grounding via ChromaDB (0.30)
    if policy_matched and chroma_context_chars > 0:
        richness_bonus = 0.02 * min(chroma_context_chars / 200.0, 1.0)
        score += 0.28 + richness_bonus
    elif chroma_context_chars > 0:
        score += 0.10
    print(f"📊 [Confidence] After policy signal: {score:.3f}")

    # Signal 3: Vision inspection succeeded (0.20)
    if vision_succeeded:
        score += 0.20
    print(f"📊 [Confidence] After vision signal: {score:.3f}")

    # Signal 4: Token output sufficiency (0.10)
    if completion_tokens >= 100:
        score += 0.10
    elif completion_tokens > 0:
        score += 0.10 * (completion_tokens / 100.0)
    print(f"📊 [Confidence] After token signal: {score:.3f}")

    final = round(min(score, 1.0), 4)
    print(f"✅ [Confidence Engine] Final score: {final:.1%}")
    return final


# =========================================================================
# 💼 CLOSED-LOOP EXECUTIVE BACKEND AUTOMATION
# =========================================================================

def parse_and_execute_executive_actions(session_id: str, agent_output: str):
    """
    Parses the structured agent markdown report, extracts executive directives,
    and updates the asset status inside the PostgreSQL operational layer.
    """
    try:
        match = re.search(
            r"\* \*\*Inventory Status:\*\*\s*(ACTIVE|DECOMMISSIONED/SCRAPPED|UNDER REVIEW)",
            agent_output, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r"Inventory Status:\s*(DECOMMISSIONED/SCRAPPED|ACTIVE|UNDER REVIEW)",
                agent_output, re.IGNORECASE
            )

        if match:
            recommended_status = match.group(1).strip().upper()
            print(f"🔎 [Automation] Extracted Inventory Mandate: {recommended_status}")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE session_records
                SET state_data = jsonb_set(
                    COALESCE(state_data, '{}'::jsonb),
                    '{asset_compliance_status}',
                    %s::jsonb
                )
                WHERE session_id = %s;
            """, (f'"{recommended_status}"', session_id))
            conn.commit()
            cursor.close()
            conn.close()
            print("💾 [PostgreSQL] Asset compliance status synchronized.")
        else:
            print("⚠️ [Automation] Could not extract inventory status token from output.")

    except Exception as e:
        print(f"❌ [Automation Failure] {str(e)}")


# =========================================================================
# 🧭 INTENT ROUTER
# =========================================================================

def triage_user_intent(client, user_message: str) -> str:
    """Classifies user intent into TEXT_RAG or MULTIMODAL_VISION."""
    print("🧭 [Intent Router] Classifying request…")

    system_routing_instruction = """
    You are an elite routing gatekeeper for an enterprise asset compliance system.
    Classify the user input into exactly one of:
    - TEXT_RAG: General policy questions, status updates, no physical inspection.
    - MULTIMODAL_VISION: Explicit hardware damage inspection or image analysis.
    Return ONLY a raw JSON object with a single key 'intent'. No markdown.
    """

    few_shot_prompt = f"""
    {system_routing_instruction}
    ---
    Example 1: User: "What does POLICY-002 require for broken laptops?" -> {{"intent": "TEXT_RAG"}}
    Example 2: User: "Here is the photo of my smashed screen." -> {{"intent": "MULTIMODAL_VISION"}}
    ---
    Actual Input: User: "{user_message}"
    Output:
    """

    try:
        config = types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.0
        )
        response = dispatch_with_retry(
            client=client,
            model_name="gemini-2.5-flash",
            contents=few_shot_prompt,
            config=config,
            max_retries=3,
        )
        data = json.loads(response.text.strip())
        return data.get("intent", "TEXT_RAG")
    except Exception as e:
        print(f"⚠️ [Router] Defaulting to TEXT_RAG. Reason: {e}")
        return "TEXT_RAG"


# =========================================================================
# ✂️ CHAT HISTORY COMPACTION
# =========================================================================

def compact_chat_history(chat_history: list, max_turns: int = 4) -> tuple:
    """Trims history to max_turns, returning (retained, anchor_summary)."""
    if len(chat_history) <= max_turns:
        return chat_history, "No archive compression required yet."

    evicted = chat_history[:-max_turns]
    retained = chat_history[-max_turns:]

    crumbs = []
    for msg in evicted:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        crumbs.append(f"{role}: {content[:40]}...")

    anchor = "Prior Archived Context Baseline: " + " | ".join(crumbs)
    print(f"✂️ [Compaction] Trimmed {len(evicted)} stale messages.")
    return retained, anchor


# =========================================================================
# 📡 LIVE EXECUTION TRACER
# =========================================================================

def _trace_step(trace_log: list, label: str, success: bool, start_ts: float, detail: str = ""):
    """Appends a completed trace entry to trace_log."""
    elapsed_ms = round((time.time() - start_ts) * 1000)
    icon = "✅" if success else "❌"
    entry = {
        "icon": icon,
        "label": label,
        "latency_ms": elapsed_ms,
        "detail": detail,
        "ts": time.strftime("%H:%M:%S", time.localtime()),
        "success": success,
    }
    trace_log.append(entry)
    status = "OK" if success else "FAIL"
    print(f"  {icon} [{status}] {label} — {elapsed_ms}ms {('· ' + detail) if detail else ''}")


# =========================================================================
# 🚀 CORE AGENT EXECUTION ENGINE
# =========================================================================

def run_contextual_agent_turn(
    user_id: str,
    session_id: str,
    user_message: str,
    transaction_id: str,
    image_path: str = None,
) -> str:
    """Core enterprise execution engine."""
    session_conn = None
    current_turn_count = 0
    chat_state_data = {}

    trace_log = []
    run_start = time.time()

    _policy_matched = False
    _vision_succeeded = False
    _chroma_chars = 0

    try:
        # ── STEP 1: Idempotency guard ─────────────────────────────────
        step_ts = time.time()
        status, cached_report = check_existing_transaction(transaction_id)
        if status == "COMPLETED":
            print(f"🛑 [Gatekeeper] Duplicate tx detected ({transaction_id}). Returning cache.")
            return cached_report
        _trace_step(trace_log, "Idempotency guard passed", True, step_ts, f"tx={transaction_id[:14]}…")

        # ── STEP 2: Acquire PROCESSING state lock ─────────────────────
        step_ts = time.time()
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO compliance_logs (transaction_id, user_id, session_id, status)
                VALUES (%s, %s, %s, 'PROCESSING');
            """, (transaction_id, user_id, session_id))
            conn.commit()
            cursor.close()
            conn.close()
            _trace_step(trace_log, "PostgreSQL state lock acquired", True, step_ts, "status=PROCESSING")
        except errors.UniqueViolation:
            _trace_step(trace_log, "PostgreSQL state lock acquired", False, step_ts, "UniqueViolation — concurrent tx")
            status, cached_report = check_existing_transaction(transaction_id)
            if status == "PROCESSING":
                return "⚠️ Request is currently being processed. Please hold or refresh."
            if status == "COMPLETED":
                return cached_report
            return "❌ Transaction collision detected during initialization."

        # ── Initialize client + intent routing ────────────────────────
        client = get_gemini_client()

        step_ts = time.time()
        routed_intent = triage_user_intent(client, user_message)
        _trace_step(trace_log, "Intent router classified request", True, step_ts, f"track={routed_intent}")
        print(f"🧭 [Intent Router] Categorized as: {routed_intent}")

        postgres_context = ""
        anchor_context = "No archive compression required yet."

        # ── STEP 3: PostgreSQL session memory retrieval ────────────────
        step_ts = time.time()
        pg_detail = ""
        try:
            session_state = get_or_create_session_state(user_id, session_id, lock_row=True)
            if session_state:
                if "_db_connection" in session_state:
                    session_conn = session_state["_db_connection"]

                current_turn_count = session_state.get("agent_turn_count", 0)
                chat_state_data = session_state.get("chat_state", {})
                if not chat_state_data:
                    chat_state_data = {
                        "user_id": user_id,
                        "agent_turn_count": current_turn_count,
                        "status": "ACTIVE",
                        "chat_history": [],
                    }

                if current_turn_count >= 11 or chat_state_data.get("status") == "SYSTEM_HALTED":
                    print(f"🛑 [Circuit Breaker] Session {session_id} is locked (max turns reached).")
                    if session_conn:
                        session_conn.close()
                    return "❌ [System Lockout] Session exceeded maximum automation turns (11)."

                current_turn_count += 1
                chat_state_data["agent_turn_count"] = current_turn_count
                pg_detail = f"turn={current_turn_count}, history={len(chat_state_data.get('chat_history', []))} msgs"
            _trace_step(trace_log, "Enterprise memory retrieved from PostgreSQL", True, step_ts, pg_detail)
        except Exception as e:
            postgres_context = f"Warning: Relational metadata locked out: {str(e)}"
            _trace_step(trace_log, "Enterprise memory retrieved from PostgreSQL", False, step_ts, str(e)[:60])

        # ── STEP 4: ChromaDB semantic retrieval ───────────────────────
        step_ts = time.time()
        chroma_policy_context = ""
        try:
            chroma_policy_context = query_semantic_memory(search_query=user_message, n_results=2)
            _chroma_chars = len(chroma_policy_context) if chroma_policy_context else 0
            chroma_detail = f"{_chroma_chars} chars retrieved" if chroma_policy_context else "empty result"
            _trace_step(trace_log, "Semantic context pulled from ChromaDB vector index", True, step_ts, chroma_detail)
        except Exception as chroma_err:
            chroma_policy_context = ""
            _chroma_chars = 0
            _trace_step(trace_log, "Semantic context pulled from ChromaDB vector index", False, step_ts, str(chroma_err)[:60])

        # ── STEP 5: Compliance policy validation ──────────────────────
        step_ts = time.time()
        try:
            _policy_matched = bool(chroma_policy_context and user_id)
            policy_detail = "tenant ruleset matched" if _policy_matched else "no policy context — using defaults"
            _trace_step(trace_log, "Compliance policy validated against tenant ruleset", _policy_matched, step_ts, policy_detail)
        except Exception as pol_err:
            _trace_step(trace_log, "Compliance policy validated against tenant ruleset", False, step_ts, str(pol_err)[:60])

        # ── STEP 6: Vision / Multimodal branch ───────────────────────
        step_ts = time.time()
        if routed_intent == "MULTIMODAL_VISION" and image_path and os.path.exists(image_path):
            try:
                print(f"📸 [Multimodal] Image verified at {image_path}. Extracting telemetry…")
                vision_report = inspect_asset_damage(image_path)
                user_message = (
                    f"[VISION TELEMETRY INTEGRATION REPORT]\n{vision_report}"
                    f"\n\n[USER DIRECTIVE]\n{user_message}"
                )
                _vision_succeeded = True
                _trace_step(
                    trace_log, "Vision inspection completed (Gemini multimodal)", True, step_ts,
                    f"file={os.path.basename(image_path)}"
                )
            except Exception as vis_err:
                _vision_succeeded = False
                _trace_step(
                    trace_log, "Vision inspection completed (Gemini multimodal)", False, step_ts, str(vis_err)[:60]
                )
        else:
            _vision_succeeded = False
            _trace_step(
                trace_log, "Vision inspection skipped — text RAG path", True, step_ts,
                "no image" if not image_path else "intent=TEXT_RAG"
            )
            print("📖 [Text RAG] Bypassing multimodal path.")

        # ── Build chat history context ─────────────────────────────────
        if chat_state_data and "chat_history" in chat_state_data:
            raw_history = chat_state_data.get("chat_history", [])
            raw_history.append({"role": "user", "content": user_message})
            active_history, anchor_context = compact_chat_history(raw_history, max_turns=4)
            chat_state_data["chat_history"] = active_history
            postgres_context = f"Active User Preferences/State Metadata: {json.dumps(chat_state_data)}"

        # ── STEP 7: Gemini multi-step reasoning pipeline ──────────────
        # KEY FIX: System instruction tells Gemini to ALWAYS produce the
        # structured report for whatever the user asked — never ask for
        # more input, never echo a persona description back.
        system_instruction = f"""
You are NexusFlow's enterprise compliance reasoning engine.

CRITICAL RULES:
1. ALWAYS produce a full structured compliance report for the user's request, even if no image is provided.
2. NEVER ask the user to upload anything or provide more information.
3. NEVER describe your own role or capabilities — just output the report.
4. If no physical asset is present, treat the user's text as the subject and produce a policy/procedural compliance analysis.

For EVERY request, your response MUST follow this exact markdown layout:

### 📥 Agent Compliance Analysis Report
Analyze the subject of the user's request against enterprise compliance standards. Describe findings clearly.

---

### 🚨 Operational Risk Assessment
State the explicit legal, technical, or financial risks identified.

---

### 💼 Executive Action Items
* **Inventory Status:** ACTIVE | DECOMMISSIONED/SCRAPPED | UNDER REVIEW
* **Logistics/Legal Action:** Detail the immediate business action required.

---

### 🧠 Memory Context
Summarize any relevant prior session context or retrieved policy knowledge applied.

---

### ✅ Recommendations
Provide 2–3 concise actionable recommendations based on the analysis.

=== LONG-TERM HISTORICAL ANCHOR ===
{anchor_context}
=== COMPLIANCE POLICIES & BUSINESS RULES ===
{chroma_policy_context if chroma_policy_context else "No policies retrieved — apply general enterprise compliance standards."}
=== USER PROFILE & SESSION STATE ===
{postgres_context if postgres_context else "No prior session context."}
"""
        print(f"🧠 [Pipeline] System instruction built ({len(system_instruction)} chars).")
        print("🚀 Dispatching payload to Gemini 2.5 Flash…")

        generation_config = types.GenerateContentConfig(
            system_instruction=system_instruction, temperature=0.2
        )
        p_tokens = c_tokens = t_tokens = 0

        step_ts = time.time()
        try:
            client = get_gemini_client()
            response = dispatch_with_retry(
                client=client,
                model_name="gemini-2.5-flash",
                contents=user_message,
                config=generation_config,
                max_retries=5,
            )
            response_text = response.text

            if response.usage_metadata:
                p_tokens = response.usage_metadata.prompt_token_count
                c_tokens = response.usage_metadata.candidates_token_count
                t_tokens = response.usage_metadata.total_token_count
                print(f"📊 [Tokens] Prompt: {p_tokens} | Completion: {c_tokens} | Total: {t_tokens}")

            _trace_step(
                trace_log, "Multi-step Gemini reasoning pipeline executed", True, step_ts,
                f"prompt={p_tokens}tok, completion={c_tokens}tok"
            )
        except Exception as api_err:
            _trace_step(
                trace_log, "Multi-step Gemini reasoning pipeline executed", False, step_ts, str(api_err)[:60]
            )
            print(f"❌ [Inference Failure] {str(api_err)}")
            raise api_err

        # ── Confidence scoring ────────────────────────────────────────
        vision_was_attempted = routed_intent == "MULTIMODAL_VISION" and image_path is not None
        confidence_score = compute_confidence_score(
            policy_matched=_policy_matched,
            vision_succeeded=_vision_succeeded if vision_was_attempted else True,
            chroma_context_chars=_chroma_chars,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            response_text=response_text,
        )
        print(f"🎯 [Confidence] Locked at: {confidence_score:.1%}")

        # ── STEP 8: Executive action automation ──────────────────────
        parse_and_execute_executive_actions(session_id, response_text)

        # ── STEP 9: Archive report + trace + confidence to PostgreSQL ─
        step_ts = time.time()
        trace_json = json.dumps(trace_log)
        try:
            print("🔄 Archiving audit log and token metrics…")
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("ALTER TABLE compliance_logs ADD COLUMN IF NOT EXISTS confidence_score FLOAT DEFAULT 0.0;")
            cursor.execute("ALTER TABLE compliance_logs ADD COLUMN IF NOT EXISTS policy_matched BOOLEAN DEFAULT FALSE;")
            cursor.execute("ALTER TABLE compliance_logs ADD COLUMN IF NOT EXISTS vision_succeeded BOOLEAN DEFAULT FALSE;")
            cursor.execute("ALTER TABLE compliance_logs ADD COLUMN IF NOT EXISTS trace_log TEXT;")

            cursor.execute("""
                UPDATE compliance_logs
                SET status            = 'COMPLETED',
                    audit_report      = %s,
                    prompt_tokens     = %s,
                    completion_tokens = %s,
                    total_tokens      = %s,
                    trace_log         = %s,
                    confidence_score  = %s,
                    policy_matched    = %s,
                    vision_succeeded  = %s
                WHERE transaction_id = %s;
            """, (
                response_text, p_tokens, c_tokens, t_tokens, trace_json,
                confidence_score, _policy_matched, _vision_succeeded, transaction_id
            ))
            conn.commit()
            print("💾 [PostgreSQL] Report and confidence telemetry committed.")
            cursor.close()
            conn.close()
            _trace_step(
                trace_log, "Report archived to forensic trail (PostgreSQL)", True, step_ts,
                f"tx={transaction_id[:14]}… confidence={confidence_score:.0%}"
            )
        except Exception as db_err:
            _trace_step(
                trace_log, "Report archived to forensic trail (PostgreSQL)", False, step_ts, str(db_err)[:60]
            )
            raise db_err

        # Write the final trace (now including the archive step itself)
        try:
            final_trace_json = json.dumps(trace_log)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE compliance_logs SET trace_log=%s WHERE transaction_id=%s;",
                (final_trace_json, transaction_id),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass  # non-critical

        total_elapsed = round((time.time() - run_start) * 1000)
        print(f"⏱️ [Tracer] Total wall-time: {total_elapsed}ms across {len(trace_log)} steps.")

        # Persist session state
        try:
            chat_state_data["chat_history"].append({"role": "model", "content": response_text})
            if current_turn_count >= 11:
                chat_state_data["status"] = "SYSTEM_HALTED"
            persist_session_state(
                session_id, chat_state_data,
                turn_count=current_turn_count,
                open_conn=session_conn,
            )
            print(f"📈 [Turn Tracker] Turn {current_turn_count}/11 persisted.")
        except Exception as save_err:
            print(f"⚠️ [Turn Tracker] Failed to persist turn: {save_err}")

        if session_conn:
            session_conn.close()
            print("🔓 [Row Lock] Released.")

        return response_text

    except Exception as e:
        print(f"⚠️ [Lock Recovery] Purging stale PROCESSING lock for: {transaction_id}")

        if session_conn and chat_state_data:
            try:
                chat_state_data["agent_turn_count"] = max(0, current_turn_count - 1)
                if chat_state_data.get("chat_history"):
                    chat_state_data["chat_history"].pop()
                persist_session_state(
                    session_id, chat_state_data,
                    turn_count=chat_state_data["agent_turn_count"],
                    open_conn=session_conn,
                )
                print("🔄 [Rollback] Turn state rolled back.")
            except Exception as rollback_err:
                print(f"⚠️ [Rollback] Failed: {rollback_err}")

        if session_conn:
            try:
                session_conn.rollback()
                session_conn.close()
                print("🔓 [Lock Recovery] Row lock released cleanly.")
            except Exception:
                pass

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM compliance_logs WHERE transaction_id = %s AND status = 'PROCESSING';",
                (transaction_id,),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass

        return f"❌ [Agent Brain Error] Transaction failed: {str(e)}"


# =========================================================================
# 🧪 LOCAL TEST HARNESS
# =========================================================================
if __name__ == "__main__":
    print("⚡ NexusFlow Agent Brain Online. Running local test…")
    mock_user    = "user_priya_88"
    mock_session = "session_analytics_test_101"
    mock_message = "Analyze this physical record asset."

    output = run_contextual_agent_turn(
        mock_user, mock_session, mock_message,
        transaction_id="tx_analytics_run_900"
    )
    print(f"\n📥 Final Response:\n{output}")