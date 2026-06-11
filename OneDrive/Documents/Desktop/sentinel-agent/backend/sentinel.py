import os
import re
import json
import time
from dotenv import load_dotenv
from google import genai
from phoenix.client import Client

load_dotenv()

# Initialize clients
gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
phoenix = Client(
    base_url="https://app.phoenix.arize.com/s/bonamukkalacharan",
    api_key=os.getenv("PHOENIX_API_KEY")
)

def gemini_generate(prompt: str) -> str:
    """Call Gemini with retry on 429/503, fallback to gemini-2.0-flash."""
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    
    for model in models:
        for attempt in range(3):
            try:
                response = gemini.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": 0.1,
                        "thinking_config": {"thinking_budget": 0}
                    }
                )
                print(f"   ✅ {model} responded")
                return response.text
            except Exception as e:
                err = str(e)
                if "429" in err:
                    match = re.search(r"retryDelay.*?(\d+)s", err)
                    wait = int(match.group(1)) + 2 if match else 15
                    print(f"   ⚠️  Rate limited ({model}), waiting {wait}s...")
                    time.sleep(wait)
                elif "503" in err or "UNAVAILABLE" in err:
                    wait = 5 * (attempt + 1)
                    print(f"   ⚠️  Unavailable ({model}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        print(f"   ⚠️  {model} exhausted, trying fallback...")
    
    raise Exception("All Gemini models exhausted. Wait a minute and retry.")


# ============================================================
# STEP 1: OBSERVE — Pull failed traces from Phoenix
# ============================================================
def observe(project_name: str = "patient-chatbot") -> dict:
    print("\n🔍 STEP 1: OBSERVE — Pulling traces from Phoenix...")
    
    try:
        spans = phoenix.spans.get_spans_dataframe(
            project_identifier=project_name,
        )
        
        if spans is None or len(spans) == 0:
            return {"error": "No traces found", "traces": []}
        
        print(f"   Found {len(spans)} total spans")
        
        trace_data = []
        for _, span in spans.iterrows():
            try:
                input_val = str(span["attributes.input.value"])
                output_val = str(span["attributes.output.value"])
                status = str(span["status_code"])
                
                if input_val and input_val != "nan" and len(input_val) > 10:
                    trace_data.append({
                        "input": input_val[:300],
                        "output": output_val[:300] if output_val != "nan" else "NO OUTPUT",
                        "status": status,
                    })
            except Exception:
                continue
        
        print(f"   Extracted {len(trace_data)} traces for analysis")
        return {"traces": trace_data, "total": len(trace_data)}
    
    except Exception as e:
        print(f"   Error fetching traces: {e}")
        return {"error": str(e), "traces": []}


# ============================================================
# STEP 2+3: CLUSTER + HYPOTHESIZE — Find patterns with Gemini
# ============================================================
def cluster_and_hypothesize(trace_data: dict) -> dict:
    print("\n🧠 STEP 2: CLUSTER — Finding failure patterns...")
    print("💡 STEP 3: HYPOTHESIZE — Forming hypothesis...")
    
    traces = trace_data.get("traces", [])
    if not traces:
        return {"error": "No traces to analyze"}
    
    sample = traces[:30]
    slim_traces = []
    for t in sample:
        slim_traces.append({
            "input": str(t.get("input", ""))[:200],
            "output": str(t.get("output", ""))[:200],
            "status": t.get("status", t.get("status_code", ""))
        })
    
    traces_text = json.dumps(slim_traces, indent=2)
    
    prompt = f"""You are Sentinel, an autonomous AI quality engineer.

Analyze these {len(slim_traces)} traces (sampled from {len(traces)} total) from a broken AI chatbot.

TRACES:
{traces_text}

Find the TOP failure pattern. Respond ONLY in this exact JSON format:
{{
    "failure_pattern": "one sentence description",
    "pattern_percentage": "estimated % of traces affected",
    "hypothesis": "specific falsifiable hypothesis",
    "evidence": ["evidence 1", "evidence 2", "evidence 3"],
    "test_questions": ["q1", "q2", "q3", "q4", "q5"],
    "confidence": "high/medium/low"
}}"""

    try:
        raw = gemini_generate(prompt).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        print(f"   Pattern found: {result.get('failure_pattern', '')[:80]}...")
        print(f"   Hypothesis: {result.get('hypothesis', '')[:80]}...")
        print(f"   Confidence: {result.get('confidence', '')}")
        return result
    except Exception as e:
        print(f"   JSON parse error: {e}")
        return {"error": str(e)}


# ============================================================
# STEP 4: EXPERIMENT — Test the hypothesis
# ============================================================
def experiment(hypothesis_data: dict) -> dict:
    print("\n🧪 STEP 4: EXPERIMENT — Testing hypothesis...")
    
    from patient_chatbot import ask_chatbot

    guaranteed_triggers = [
        "What is your return policy and how long does shipping take?",
        "Can you give me a discount on my order?",
        "What about a repair service for my laptop?",
        "Do you offer subscription plans or payment options?",
        "What about cancellations?",
    ]
    
    gemini_questions = hypothesis_data.get("test_questions", [])
    all_questions = guaranteed_triggers + [
        q for q in gemini_questions if q not in guaranteed_triggers
    ]

    results = []
    failures = 0

    for q in all_questions:
        result = ask_chatbot(q)
        results.append({
            "question": q,
            "is_failure": result["is_failure"],
            "failure_type": result["failure_type"],
            "answer_preview": result["answer"][:100]
        })
        if result["is_failure"]:
            failures += 1
        print(f"   Test: {'❌ FAIL' if result['is_failure'] else '✅ PASS'} | {q[:60]}...")

    failure_rate = (failures / len(all_questions)) * 100
    hypothesis_confirmed = failure_rate >= 60

    print(f"\n   Failure rate: {failure_rate:.0f}%")
    print(f"   Hypothesis {'✅ CONFIRMED' if hypothesis_confirmed else '❌ REFUTED'}")

    return {
        "test_results": results,
        "failure_rate": failure_rate,
        "hypothesis_confirmed": hypothesis_confirmed,
        "tests_run": len(all_questions),
        "failures_found": failures
    }


# ============================================================
# STEP 5: VERDICT — Generate final diagnosis
# ============================================================
def verdict(hypothesis_data: dict, experiment_data: dict) -> dict:
    print("\n📋 STEP 5: VERDICT — Generating diagnosis...")
    
    prompt = f"""You are Sentinel, an autonomous AI quality engineer.

You investigated an AI chatbot and here are your findings:

HYPOTHESIS: {hypothesis_data.get('hypothesis')}
FAILURE PATTERN: {hypothesis_data.get('failure_pattern')}
EVIDENCE: {hypothesis_data.get('evidence')}
EXPERIMENT RESULTS: {experiment_data.get('failure_rate')}% failure rate on test questions
HYPOTHESIS CONFIRMED: {experiment_data.get('hypothesis_confirmed')}

Generate a verdict report in this EXACT JSON format:
{{
    "verdict": "CRITICAL/HIGH/MEDIUM/LOW",
    "summary": "one sentence summary of what is wrong",
    "root_cause": "specific root cause explanation",
    "fix_recommendation": "specific actionable fix the developer should make",
    "estimated_impact": "what % of users are affected and how",
    "next_steps": ["step 1", "step 2", "step 3"]
}}

Return ONLY the JSON, no other text."""

    try:
        raw = gemini_generate(prompt).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return result
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# MAIN: Run full Sentinel investigation
# ============================================================
def run_investigation(project_name: str = "patient-chatbot") -> dict:
    print("=" * 60)
    print("🛡️  SENTINEL — Autonomous AI Quality Engineer")
    print("=" * 60)
    print(f"Target: {project_name}")
    
    trace_data = observe(project_name)
    if "error" in trace_data and not trace_data.get("traces"):
        print(f"❌ Investigation failed: {trace_data['error']}")
        return trace_data
    
    hypothesis = cluster_and_hypothesize(trace_data)
    if "error" in hypothesis:
        print(f"❌ Hypothesis failed: {hypothesis['error']}")
        return hypothesis
    
    experiment_results = experiment(hypothesis)
    final_verdict = verdict(hypothesis, experiment_results)
    
    report = {
        "project": project_name,
        "traces_analyzed": trace_data.get("total", 0),
        "hypothesis": hypothesis,
        "experiment": experiment_results,
        "verdict": final_verdict
    }
    
    print("\n" + "=" * 60)
    print("🎯 FINAL VERDICT")
    print("=" * 60)
    print(json.dumps(final_verdict, indent=2))
    
    return report


if __name__ == "__main__":
    report = run_investigation("patient-chatbot")
    with open("investigation_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\n✅ Full report saved to investigation_report.json")