import { useEffect, useRef, useState } from "react";
import { animate, stagger } from "animejs";
import Camera from "./Camera";
import Keychain from "./Keychain";
import "./Locker.css";

import lockerBg from "../assets/purple_lockers.png";
import cellPhone from "../assets/final_cellphone.png";
import star from "../assets/final_star(1).png";
import auraLogo from "../assets/final_auralogo.png";

// In production, VITE_API_BASE can be set to the backend origin if it differs.
// For local dev, the Vite proxy handles /chat and /audio automatically.
const API_BASE = import.meta.env.VITE_API_BASE || "";

const Locker = ({ onResults }) => {
  const [budget, setBudget] = useState("");
  const [styleRequest, setStyleRequest] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [hasAudio, setHasAudio] = useState(false);
  const [hasPhoto, setHasPhoto] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Recording timer & waveform
  const [recSeconds, setRecSeconds] = useState(0);
  const [waveformPct, setWaveformPct] = useState(0);
  const recTimerRef = useRef(null);

  // Knot state
  const [knotConnected, setKnotConnected] = useState(false);
  const [knotUserId, setKnotUserId] = useState(null);

  const audioBlobRef = useRef(null);
  const photoBlobRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordedChunksRef = useRef([]);

  // Entrance animation — unchanged
  useEffect(() => {
    const timer = setTimeout(() => {
      const elements = document.querySelectorAll(".dynamic-asset");
      if (elements.length > 0) {
        try {
          animate(".dynamic-asset", {
            scale: [0, 1],
            opacity: [0, 1],
            delay: stagger(100),
            ease: "outElastic(1, .8)",
          });
        } catch (err) {
          console.error("Animation error:", err);
        }
      }
    }, 300);
    return () => clearTimeout(timer);
  }, []);

  // ── Knot helpers ──────────────────────────────────────────────────────────
  function getOrCreateUserId() {
    let id = localStorage.getItem("aura_knot_user_id");
    if (!id) {
      id = "aura-" + crypto.randomUUID();
      localStorage.setItem("aura_knot_user_id", id);
    }
    return id;
  }

  const handleKnotConnect = () => {
    const userId = getOrCreateUserId();
    setKnotUserId(userId);
    setKnotConnected(true);
  };

  const handleKnotDisconnect = () => {
    setKnotConnected(false);
    setKnotUserId(null);
  };

  // ── Voice recording ───────────────────────────────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordedChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        audioBlobRef.current = new Blob(recordedChunksRef.current, {
          type: mimeType,
        });
        setHasAudio(true);
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(recTimerRef.current);
        setWaveformPct(0);
      };

      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecSeconds(0);

      let secs = 0;
      recTimerRef.current = setInterval(() => {
        secs++;
        setRecSeconds(secs);
        setWaveformPct(Math.min(100, secs * 2));
      }, 1000);
    } catch (err) {
      console.error("[Locker] mic access denied:", err);
      setError("Microphone access denied.");
    }
  };

  const stopRecording = () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearInterval(recTimerRef.current);
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Called by Camera shutter — just stores the blob, doesn't submit
  const handlePhotoCapture = (photoBlob) => {
    if (photoBlob) {
      photoBlobRef.current = photoBlob;
      setHasPhoto(true);
    }
  };

  // Explicit submit — called by the Ask Aura button
  const handleSubmit = async () => {
    if (isLoading) return;

    // Stop any active recording so its chunks are flushed
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(recTimerRef.current);
      await new Promise((r) => setTimeout(r, 200));
    }

    setIsLoading(true);
    setError(null);

    const form = new FormData();
    if (photoBlobRef.current)
      form.append("image", photoBlobRef.current, "photo.jpg");
    if (audioBlobRef.current)
      form.append("audio", audioBlobRef.current, "voice.webm");
    if (styleRequest.trim()) form.append("text", styleRequest.trim());
    if (budget.trim()) form.append("max_budget", budget.trim());
    if (knotConnected && knotUserId) form.append("knot_token", knotUserId);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      // Attach the captured photo URL so Results can show it on the camera screen
      const photoUrl = photoBlobRef.current
        ? URL.createObjectURL(photoBlobRef.current)
        : null;
      onResults({ ...data, _photoUrl: photoUrl, _knotUserId: knotConnected ? knotUserId : null });
    } catch (err) {
      console.error("[Locker] submit error:", err);
      setError(err.message || "Something went wrong. Try again.");
      setIsLoading(false);
    }
  };

  const canSubmit = hasPhoto || hasAudio || styleRequest.trim().length > 0;

  return (
    <div className="viewport-wrapper">
      <div className="locker-canvas">
        <img src={lockerBg} className="locker-bg" alt="lockers" />

        <img src={star} className="dynamic-asset star-top" alt="star" />
        <img src={cellPhone} className="dynamic-asset flip-phone" alt="phone" />
        <img
          src={auraLogo}
          className={`aura-header${isLoading ? " cooking" : ""}`}
          alt="aura logo"
          onClick={handleSubmit}
          title={isLoading ? "Aura is cooking... 🍳" : "Ask Aura"}
        />

        {/* Camera — shutter stores the photo blob; submit button sends everything */}
        <Camera onCapture={handlePhotoCapture} isLoading={isLoading} />

        <div className="keychain-zone">
          <Keychain />
        </div>

        {/* ── Knot connect section ─────────────────────────────────────── */}
        <div className="knot-section">
          {!knotConnected ? (
            <>
              <p className="knot-status">
                Connect your Amazon account so Aura can personalise picks 🛒
              </p>
              <button
                className="btn-knot-connect"
                onClick={handleKnotConnect}
                disabled={isLoading}
              >
                🔗 Connect Amazon
              </button>
            </>
          ) : (
            <>
              <p className="knot-status connected">
                ✅ Amazon connected — picks will be personalised to you
              </p>
              <button
                className="btn-knot-disconnect"
                onClick={handleKnotDisconnect}
                disabled={isLoading}
              >
                Disconnect
              </button>
            </>
          )}
        </div>

        {/* ── Voice section with waveform ──────────────────────────────── */}
        <div className="voice-section">
          {/* Waveform bar */}
          <div className="waveform-bar">
            <div
              className="waveform-fill"
              style={{ width: `${waveformPct}%` }}
            />
          </div>
          {isRecording && (
            <span className="rec-timer">⏺ {recSeconds}s</span>
          )}

          <button
            className={`voice-btn ${isRecording ? "recording" : ""}`}
            onClick={toggleRecording}
            disabled={isLoading}
          />
          {isRecording && (
            <span className="recording-indicator">Recording...</span>
          )}
          {hasAudio && !isRecording && (
            <span className="recording-indicator" style={{ color: "#4caf50" }}>
              Voice ready ✓
            </span>
          )}
        </div>

        <div className="bottom-input-section">
          <div className="input-group">
            <label>Budget</label>
            <input
              type="text"
              placeholder="Enter your budget"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              disabled={isLoading}
            />
          </div>
          <div className="input-group">
            <label>Style Request</label>
            <textarea
              placeholder="Describe the style you want..."
              value={styleRequest}
              onChange={(e) => setStyleRequest(e.target.value)}
              rows="3"
              disabled={isLoading}
            />
          </div>
        </div>

        {isLoading && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              color: "white",
              fontSize: "18px",
              fontWeight: "bold",
              background: "rgba(0,0,0,0.55)",
              padding: "12px 28px",
              borderRadius: "30px",
              zIndex: 200,
              pointerEvents: "none",
            }}
          >
            Aura is cooking... 🍳
          </div>
        )}

        {error && (
          <div
            style={{
              position: "absolute",
              bottom: "230px",
              left: "50%",
              transform: "translateX(-50%)",
              backgroundColor: "rgba(200,40,40,0.9)",
              color: "white",
              padding: "10px 24px",
              borderRadius: "8px",
              fontSize: "14px",
              zIndex: 100,
              maxWidth: "600px",
              textAlign: "center",
            }}
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default Locker;
