import { useState, useRef } from "react";

const API_URL = "https://charan-reddy222-sentinel-backend.hf.space";

const steps = [
  { id: 1, label: "Observe", icon: "🔍", desc: "Pulling traces from Phoenix" },
  { id: 2, label: "Cluster & Hypothesize", icon: "🧠", desc: "Clustering failures and forming hypothesis" },
  { id: 3, label: "Experiment", icon: "🧪", desc: "Testing hypothesis" },
  { id: 4, label: "Verdict", icon: "📋", desc: "Generating diagnosis" },
];

function StepCard({ step, status, message, data }) {
  const [expanded, setExpanded] = useState(false);

  const bgColor =
    status === "done"    ? "#0f2a1e" :
    status === "running" ? "#1a1a2e" :
    "#111";
  const borderColor =
    status === "done"    ? "#1d9e75" :
    status === "running" ? "#4f46e5" :
    "#222";
  const statusIcon =
    status === "done"    ? "✅" :
    status === "running" ? "⏳" :
    "⬜";

  return (
    <div style={{
      background: bgColor,
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      padding: "16px 20px",
      marginBottom: 12,
      transition: "all 0.4s ease",
      opacity: status ? 1 : 0.4,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 20 }}>{statusIcon}</span>
        <span style={{ fontSize: 18 }}>{step.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: "#fff", fontSize: 15 }}>{step.label}</div>
          <div style={{ color: status === "running" ? "#7c77f0" : "#888", fontSize: 13, marginTop: 2 }}>
            {message || step.desc}
            {status === "running" && (
              <span style={{ marginLeft: 6, animation: "pulse 1s infinite" }}>●</span>
            )}
          </div>
        </div>
        {data && status === "done" && (
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              background: "#222",
              border: "1px solid #444",
              color: "#aaa",
              borderRadius: 6,
              padding: "4px 10px",
              cursor: "pointer",
              fontSize: 12
            }}
          >
            {expanded ? "Hide" : "Details"}
          </button>
        )}
      </div>
      {step.id === 2 && status === "done" && data?.confidence === "low" && (
        <div style={{
          marginTop: 10,
          background: "#2a2000",
          border: "1px solid #ffd700",
          borderRadius: 8,
          padding: "8px 12px",
          color: "#ffd700",
          fontSize: 13,
          display: "flex",
          alignItems: "center",
          gap: 8
        }}>
          ⚠️ Low confidence — manual review recommended
        </div>
      )}
      {expanded && data && (
        <pre style={{
          marginTop: 12,
          background: "#0a0a0a",
          borderRadius: 8,
          padding: 12,
          fontSize: 12,
          color: "#7dd3b0",
          overflow: "auto",
          maxHeight: 300
        }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function VerdictCard({ verdict }) {
  if (!verdict) return null;
  const color =
    verdict.verdict === "CRITICAL" ? "#ff4444" :
    verdict.verdict === "HIGH"     ? "#ff8c00" :
    verdict.verdict === "MEDIUM"   ? "#ffd700" :
    "#1d9e75";

  return (
    <div style={{
      background: "#0a1628",
      border: `2px solid ${color}`,
      borderRadius: 16,
      padding: 24,
      marginTop: 20
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <span style={{
          background: color,
          color: "#000",
          fontWeight: 700,
          padding: "4px 14px",
          borderRadius: 20,
          fontSize: 14
        }}>
          {verdict.verdict}
        </span>
        <span style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}>
          {verdict.summary}
        </span>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>ROOT CAUSE</div>
        <div style={{ color: "#ccc", fontSize: 14, lineHeight: 1.6 }}>{verdict.root_cause}</div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>FIX RECOMMENDATION</div>
        <div style={{
          background: "#0f2a1e",
          border: "1px solid #1d9e75",
          borderRadius: 8,
          padding: 12,
          color: "#7dd3b0",
          fontSize: 14,
          lineHeight: 1.6
        }}>
          {verdict.fix_recommendation}
        </div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>ESTIMATED IMPACT</div>
        <div style={{ color: "#ccc", fontSize: 14 }}>{verdict.estimated_impact}</div>
      </div>
      <div>
        <div style={{ color: "#888", fontSize: 12, marginBottom: 8 }}>NEXT STEPS</div>
        {verdict.next_steps?.map((step, i) => (
          <div key={i} style={{
            display: "flex",
            gap: 10,
            marginBottom: 8,
            color: "#ccc",
            fontSize: 13
          }}>
            <span style={{ color: "#4f46e5", fontWeight: 700 }}>{i + 1}.</span>
            {step}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [project, setProject] = useState("patient-chatbot");
  const [running, setRunning] = useState(false);
  const [started, setStarted] = useState(false);   // ← show steps immediately on click
  const [stepStates, setStepStates] = useState({});
  const [verdict, setVerdict] = useState(null);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);

  const startInvestigation = () => {
    setRunning(true);
    setStarted(true);      // ← all 4 step cards appear immediately
    setStepStates({});
    setVerdict(null);
    setComplete(false);
    setError(null);

    const url = `${API_URL}/investigate/${encodeURIComponent(project)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);

        if (data.status === "complete") {
          setComplete(true);
          setRunning(false);
          es.close();
          return;
        }

        if (data.status === "error") {
          setError(data.message);
          setRunning(false);
          es.close();
          return;
        }

        setStepStates(prev => ({
          ...prev,
          [data.step]: { status: data.status, message: data.message, data: data.data }
        }));

        if (data.step === 4 && data.status === "done" && data.data) {
          setVerdict(data.data);
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    es.onerror = () => {
      setError("Connection lost. Is the backend running on port 8000?");
      setRunning(false);
      es.close();
    };
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0d0d0d",
      color: "#fff",
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: "40px 20px"
    }}>
      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>

      <div style={{ maxWidth: 760, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 40, textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>🛡️</div>
          <h1 style={{ fontSize: 32, fontWeight: 700, margin: 0 }}>Sentinel</h1>
          <p style={{ color: "#666", marginTop: 8, fontSize: 16 }}>
            Autonomous AI Quality Engineer
          </p>
        </div>

        {/* Input */}
        <div style={{
          background: "#111",
          border: "1px solid #222",
          borderRadius: 12,
          padding: 20,
          marginBottom: 24
        }}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 8 }}>TARGET PROJECT</div>
          <div style={{ display: "flex", gap: 12 }}>
            <input
              value={project}
              onChange={e => setProject(e.target.value)}
              disabled={running}
              style={{
                flex: 1,
                background: "#0a0a0a",
                border: "1px solid #333",
                borderRadius: 8,
                padding: "10px 14px",
                color: "#fff",
                fontSize: 14,
                outline: "none"
              }}
            />
            <button
              onClick={startInvestigation}
              disabled={running}
              style={{
                background: running ? "#333" : "#4f46e5",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                padding: "10px 24px",
                fontSize: 14,
                fontWeight: 600,
                cursor: running ? "not-allowed" : "pointer",
                transition: "background 0.2s"
              }}
            >
              {running ? "Investigating..." : "Investigate"}
            </button>
          </div>
        </div>

        {/* Steps — always show all 4 once started */}
        {started && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ color: "#666", fontSize: 12, marginBottom: 12 }}>
              INVESTIGATION PROGRESS
            </div>
            {steps.map(step => {
              const state = stepStates[step.id] || {};
              return (
                <StepCard
                  key={step.id}
                  step={step}
                  status={state.status || null}
                  message={state.message}
                  data={state.data}
                />
              );
            })}
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: "#2a0a0a",
            border: "1px solid #ff4444",
            borderRadius: 8,
            padding: 12,
            color: "#ff8888",
            fontSize: 13,
            marginTop: 12
          }}>
            ❌ {error}
          </div>
        )}

        {/* Verdict */}
        {verdict && <VerdictCard verdict={verdict} />}

        {/* Complete */}
        {complete && (
          <div style={{
            textAlign: "center",
            marginTop: 24,
            color: "#1d9e75",
            fontSize: 14
          }}>
            ✅ Investigation complete — Powered by Gemini 2.5 Flash + Arize Phoenix
          </div>
        )}
      </div>
    </div>
  );
}