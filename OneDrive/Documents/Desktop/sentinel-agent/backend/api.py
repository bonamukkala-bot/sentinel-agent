import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import asyncio

load_dotenv()

app = FastAPI(title="Sentinel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def stream_investigation(project_name: str):
    """Stream each step of the investigation as Server-Sent Events."""
    
    try:
        from sentinel import observe, cluster_and_hypothesize, experiment, verdict
        
        # Step 1: Observe
        yield f"data: {json.dumps({'step': 1, 'status': 'running', 'message': 'Pulling traces from Phoenix...'})}\n\n"
        
        trace_data = await asyncio.wait_for(
            asyncio.to_thread(observe, project_name),
            timeout=60.0
        )
        
        if trace_data.get("error") and not trace_data.get("traces"):
            err_msg = f"Failed to fetch traces: {trace_data['error']}"
            yield f"data: {json.dumps({'step': 1, 'status': 'error', 'message': err_msg})}\n\n"
            return
        
        total = trace_data.get('total', 0)
        yield f"data: {json.dumps({'step': 1, 'status': 'done', 'message': f'Found {total} traces for analysis', 'data': {'total': total}})}\n\n"
        
        # Step 2+3: Cluster + Hypothesize
        yield f"data: {json.dumps({'step': 2, 'status': 'running', 'message': 'Clustering failures and forming hypothesis...'})}\n\n"
        
        hypothesis = await asyncio.wait_for(
            asyncio.to_thread(cluster_and_hypothesize, trace_data),
            timeout=120.0
        )
        
        if hypothesis.get("error"):
            err_msg2 = f"Hypothesis failed: {hypothesis['error']}"
            yield f"data: {json.dumps({'step': 2, 'status': 'error', 'message': err_msg2})}\n\n"
            return
        
        yield f"data: {json.dumps({'step': 2, 'status': 'done', 'message': 'Hypothesis formed', 'data': hypothesis})}\n\n"
        
        # Step 4: Experiment
        yield f"data: {json.dumps({'step': 3, 'status': 'running', 'message': 'Running experiments to test hypothesis...'})}\n\n"
        
        experiment_results = await asyncio.wait_for(
            asyncio.to_thread(experiment, hypothesis),
            timeout=120.0
        )
        
        rate = experiment_results.get('failure_rate', 0)
        yield f"data: {json.dumps({'step': 3, 'status': 'done', 'message': f'Experiments complete. Failure rate: {rate:.0f}%', 'data': experiment_results})}\n\n"
        
        # Step 5: Verdict
        yield f"data: {json.dumps({'step': 4, 'status': 'running', 'message': 'Generating final verdict...'})}\n\n"
        
        final_verdict = await asyncio.wait_for(
            asyncio.to_thread(verdict, hypothesis, experiment_results),
            timeout=180.0
        )
        
        yield f"data: {json.dumps({'step': 4, 'status': 'done', 'message': 'Verdict ready', 'data': final_verdict})}\n\n"
        
        yield f"data: {json.dumps({'step': 5, 'status': 'complete', 'message': 'Investigation complete'})}\n\n"
        
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'step': 0, 'status': 'error', 'message': 'Step timed out. Phoenix may be slow — retry in 10 seconds.'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'step': 0, 'status': 'error', 'message': str(e)})}\n\n"


@app.get("/")
def root():
    return {"message": "Sentinel API is running", "status": "online"}


@app.get("/investigate/{project_name}")
async def investigate(project_name: str):
    return StreamingResponse(
        stream_investigation(project_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/projects")
def list_projects():
    return {
        "projects": ["patient-chatbot"],
        "default": "patient-chatbot"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "gemini": "connected" if os.getenv("GEMINI_API_KEY") else "missing",
        "phoenix": "connected" if os.getenv("PHOENIX_API_KEY") else "missing",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat()
    }