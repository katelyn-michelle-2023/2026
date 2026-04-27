import { useEffect, useRef, useState } from "react";
import { animate, stagger } from "animejs";
import "./Locker.css";

import resultsBg from "../assets/result_page.png";
import cameraResults from "../assets/camera_results.png";
import auraResultsLogo from "../assets/aura_results_final.png";
import notebook from "../assets/notebook.png";
import photostrip from "../assets/photostrip.png";

const API_BASE = import.meta.env.VITE_API_BASE || "";

// Try-on images keyed by product index (0-3).
// Replace null values with real URLs once available.
// If product IDs are stable, key by id instead of index.
const TRY_ON_IMAGES = { 0: null, 1: null, 2: null, 3: null };

// Vertical positions of each photo-strip frame, relative to the strip container.
// These align with the 4 frame slots printed in photostrip.png — adjust if needed.
// top = distance from top of the photostrip container to each frame slot
// Calibrate these against photostrip.png visually
const STRIP_FRAMES = [
  { top: "165px", height: "150px" },
  { top: "332px", height: "150px" },
  { top: "500px", height: "150px" },
  { top: "670px", height: "150px" },
];

// Purchase badge status → label
function badgeLabel(status) {
  if (status === "pending") return "⏳ Ordered";
  if (status === "purchased") return "✓ Copped";
  if (status === "failed") return "✗ Failed";
  if (status === "skipped") return "→ Link to shop";
  return null;
}

const Results = ({ data, onBack }) => {
  const [activeIdx, setActiveIdx] = useState(0);
  const audioRef = useRef(null);

  // Purchase flow state
  const [purchaseStatus, setPurchaseStatus] = useState({}); // { item_id: { status } }
  const [purchaseConfirmed, setPurchaseConfirmed] = useState(false);
  const [purchaseLoading, setPurchaseLoading] = useState(false);
  const [purchaseSkipped, setPurchaseSkipped] = useState(false);

  // Subscription banner state
  const [cancelledSubs, setCancelledSubs] = useState({}); // { sub_id: true }
  const [cancellingId, setCancellingId] = useState(null);

  const picks = data?.picks || [];
  const audioUrl = data?.audio_url || null;
  const photoUrl = data?._photoUrl || null;
  const knotUserId = data?._knotUserId || null;
  const transcript = data?.transcript || null;
  const activeSubscriptions = data?.active_subscriptions || [];
  const pick = picks[activeIdx] || null;

  // Picks that can be auto-purchased (have an amazon_asin) — only shown when Knot connected
  const purchasablePicks = picks.filter((p) => p.amazon_asin);
  const showPurchaseSection =
    knotUserId && purchasablePicks.length > 0 && !purchaseSkipped && !purchaseConfirmed;

  const purchaseTotal = purchasablePicks.reduce(
    (sum, p) => sum + (p.price_usd || 0),
    0
  );

  // Entrance animations — unchanged
  useEffect(() => {
    animate(".result-asset", {
      opacity: [0, 1],
      scale: [0.9, 1],
      rotate: (el) => {
        if (el.classList.contains("results-photostrip")) return -5;
        if (el.classList.contains("results-notebook")) return 3;
        return 0;
      },
      delay: stagger(150),
      ease: "outBack",
    });
  }, []);

  // Auto-play Aura's voice note on load
  useEffect(() => {
    if (audioRef.current && audioUrl) {
      audioRef.current
        .play()
        .catch((err) => console.warn("[Results] autoplay blocked:", err));
    }
  }, [audioUrl]);

  // Fade notebook content on active pick change
  useEffect(() => {
    animate(".notebook-content", {
      opacity: [0, 1],
      translateY: [8, 0],
      duration: 280,
      ease: "outQuad",
    });
  }, [activeIdx]);

  // ── Inline purchase confirm ───────────────────────────────────────────────
  const handlePurchaseConfirm = async () => {
    setPurchaseLoading(true);
    const form = new FormData();
    if (knotUserId) form.append("knot_token", knotUserId);
    form.append("execute_purchase", "true");

    try {
      const res = await fetch(`${API_BASE}/chat`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const result = await res.json();

      if (result.purchase_status) {
        const statusMap = {};
        result.purchase_status.forEach((s) => {
          statusMap[s.item_id] = s;
        });
        setPurchaseStatus(statusMap);
      }
      setPurchaseConfirmed(true);
    } catch (err) {
      console.error("[Results] purchase error:", err);
    } finally {
      setPurchaseLoading(false);
    }
  };

  // ── Cancel subscription ───────────────────────────────────────────────────
  const handleCancelSub = async (subId) => {
    setCancellingId(subId);
    try {
      const res = await fetch(`${API_BASE}/cancel-subscription/${subId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setCancelledSubs((prev) => ({ ...prev, [subId]: true }));
    } catch (err) {
      console.error("[Results] cancel sub error:", err);
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="viewport-wrapper">
      <div className="locker-canvas">
        <img src={resultsBg} className="locker-bg" alt="bg" />

        {/* Top Logo */}
        <img
          src={auraResultsLogo}
          className="result-asset results-logo"
          alt="logo"
        />

        {/* Notebook — static image layer */}
        <img
          src={notebook}
          className="result-asset results-notebook"
          alt="notebook"
        />

        {/* Product image — left page of the notebook */}
        {pick?.image_url && (
          <img
            src={pick.image_url}
            alt={pick.name}
            style={{
              position: "absolute",
              top: "250px",
              left: "355px",
              width: "310px",
              height: "380px",
              objectFit: "cover",
              borderRadius: "6px",
              zIndex: 8,
              transform: "rotate(-7deg)",
              transformOrigin: "top left",
              pointerEvents: "none",
              boxShadow: "2px 4px 16px rgba(0,0,0,0.18)",
            }}
          />
        )}

        {/* Notebook content — overlaid on the right page of the notebook PNG.
            Adjust top/left/width/height to match the right-page area in notebook.png. */}
        {pick && (
          <div
            className="notebook-content"
            style={{
              position: "absolute",
              top: "200px",
              left: "800px",
              width: "375px",
              height: "570px",
              zIndex: 10,
              overflow: "hidden",
              padding: "18px 20px",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              transform: "rotate(-5deg)",
              transformOrigin: "top left",
            }}
          >
            <div
              style={{
                fontSize: "17px",
                fontWeight: "bold",
                color: "#1a1a1a",
                lineHeight: 1.3,
              }}
            >
              {pick.name}
            </div>
            <div
              style={{
                fontSize: "13px",
                color: "#666",
              }}
            >
              {pick.brand}
            </div>
            <div
              style={{ fontSize: "22px", fontWeight: "bold", color: "#a855f7" }}
            >
              ${pick.price_usd ?? pick.price ?? "—"}
            </div>
            {pick.justification && (
              <div
                style={{
                  fontSize: "12px",
                  fontStyle: "italic",
                  color: "#333",
                  lineHeight: 1.55,
                  borderLeft: "2px solid #e879a0",
                  paddingLeft: "9px",
                }}
              >
                "{pick.justification}"
              </div>
            )}
            {pick.recommended_size && (
              <div
                style={{
                  fontSize: "12px",
                  color: "#555",
                  background: "#f0e8ff",
                  borderRadius: "6px",
                  padding: "7px 10px",
                }}
              >
                <strong>Size rec:</strong> {pick.recommended_size}
                {pick.size_adjustment && pick.size_adjustment !== "none" && (
                  <span> · size {pick.size_adjustment}</span>
                )}
                {pick.fit_flags?.length > 0 && (
                  <div style={{ marginTop: "px", fontSize: "11px" }}>
                    {pick.fit_flags.join(" · ")}
                  </div>
                )}
              </div>
            )}

            {/* Purchase status badge for active pick */}
            {purchaseStatus[pick.id] && (
              <div
                className={`purchase-badge ${purchaseStatus[pick.id].status}`}
                style={{ alignSelf: "flex-start" }}
              >
                {badgeLabel(purchaseStatus[pick.id].status)}
              </div>
            )}

            <a
              href={pick.url || pick.product_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                marginTop: "auto",
                display: "inline-block",
                padding: "9px 20px",
                background: "linear-gradient(135deg, #e879a0, #a855f7)",
                color: "white",
                borderRadius: "20px",
                textDecoration: "none",
                fontWeight: "bold",
                fontSize: "13px",
                textAlign: "center",
              }}
            >
              Shop →
            </a>
          </div>
        )}

        {/* Camera — static image + optional try-on overlay.
            Adjust the overlay top/left/width/height to match the screen in camera_results.png. */}
        <div
          style={{
            position: "absolute",
            top: "500px",
            left: "10px",
            width: "500px",
            zIndex: 20,
          }}
        >
          <img
            src={cameraResults}
            className="result-asset"
            alt="camera"
            style={{ width: "100%", display: "block" }}
          />{" "}
          {/* Show captured photo on the camera screen */}
          {photoUrl && (
            <img
              src={photoUrl}
              alt="your photo"
              style={{
                position: "absolute",
                top: "100px",
                left: "42px",
                width: "300px",
                height: "220px",
                objectFit: "cover",
                borderRadius: "4px",
                transform: "rotate(12deg)",
                transformOrigin: "center center",
              }}
            />
          )}{" "}
          {TRY_ON_IMAGES[activeIdx] && (
            <img
              src={TRY_ON_IMAGES[activeIdx]}
              alt="try-on"
              style={{
                position: "absolute",
                top: "60px",
                left: "85px",
                width: "240px",
                height: "300px",
                objectFit: "cover",
                borderRadius: "4px",
              }}
            />
          )}
        </div>

        {/* Photostrip — static image + 4 clickable product-image overlays */}
        <div
          style={{
            position: "absolute",
            top: "0px",
            right: "30px",
            width: "280px",
            zIndex: 40,
            pointerEvents: "auto",
          }}
        >
          <img
            src={photostrip}
            className="result-asset results-photostrip"
            alt="photostrip"
            style={{ width: "100%", display: "block" }}
          />

          {picks.slice(0, 4).map((p, i) => (
            <div
              key={p.id || i}
              onClick={() => setActiveIdx(i)}
              style={{
                position: "absolute",
                top: STRIP_FRAMES[i].top,
                left: "0x",
                width: "236px",
                height: STRIP_FRAMES[i].height,
                cursor: "pointer",
                borderRadius: "4px",
                overflow: "hidden",
                outline: activeIdx === i ? "3px solid #e879a0" : "none",
                outlineOffset: "2px",
                boxShadow:
                  activeIdx === i ? "0 0 14px rgba(232,121,160,0.85)" : "none",
                transition: "box-shadow 0.2s, outline 0.2s",
                zIndex: 41,
                pointerEvents: "auto",
              }}
            >
              {p.image_url ? (
                <img
                  src={p.image_url}
                  alt={p.name}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    background: "#ddd",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "11px",
                    color: "#999",
                  }}
                >
                  No image
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Aura's voice note — auto-plays, controls visible top-right */}
        {audioUrl && (
          <audio
            ref={audioRef}
            src={`${API_BASE}${audioUrl}`}
            controls
            style={{
              position: "absolute",
              top: "18px",
              right: "340px",
              height: "30px",
              opacity: 0.85,
              zIndex: 50,
            }}
          />
        )}

        {/* ── Transcript box ─────────────────────────────────────────────── */}
        {transcript && (
          <div className="transcript-box">🎙 &ldquo;{transcript}&rdquo;</div>
        )}

        {/* ── Subscription banner ────────────────────────────────────────── */}
        {activeSubscriptions.length > 0 && (
          <div className="sub-banner">
            <h3>👀 Aura noticed something…</h3>
            <div className="sub-list">
              {activeSubscriptions.map((sub) =>
                cancelledSubs[sub.id] ? (
                  <div key={sub.id} className="sub-item">
                    <span style={{ color: "#16a34a", fontSize: "0.85rem" }}>
                      ✓ Cancelled
                    </span>
                  </div>
                ) : (
                  <div key={sub.id} className="sub-item">
                    <span className="sub-name">{sub.name}</span>
                    {sub.monthly_cost_usd != null && (
                      <span className="sub-cost">
                        ${sub.monthly_cost_usd}/mo
                      </span>
                    )}
                    {sub.is_cancellable ? (
                      <button
                        className="btn-danger-sm"
                        onClick={() => handleCancelSub(sub.id)}
                        disabled={cancellingId === sub.id}
                      >
                        {cancellingId === sub.id ? "Cancelling…" : "Cancel"}
                      </button>
                    ) : (
                      <span style={{ fontSize: "0.75rem", color: "#555" }}>
                        Not cancellable
                      </span>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
        )}

        {/* ── Inline purchase section ────────────────────────────────────── */}
        {showPurchaseSection && (
          <div className="purchase-section">
            <h3>🛒 Cop the Look</h3>
            <p className="purchase-desc">
              Aura will place these orders on your Amazon account automatically.
              Real money, real clothes.
            </p>
            <ul className="purchase-list">
              {purchasablePicks.map((p) => (
                <li key={p.id || p.name}>
                  <span>{p.name}</span>
                  <span>${p.price_usd}</span>
                </li>
              ))}
            </ul>
            <div className="purchase-total">
              Total: ${purchaseTotal.toFixed(2)}
            </div>
            <div className="purchase-btn-row">
              <button
                className="btn-purchase-confirm"
                onClick={handlePurchaseConfirm}
                disabled={purchaseLoading}
              >
                {purchaseLoading ? "Placing order…" : "✦ Yes, cop it all"}
              </button>
              <button
                className="btn-purchase-skip"
                onClick={() => setPurchaseSkipped(true)}
                disabled={purchaseLoading}
              >
                Nah, just browse
              </button>
            </div>
          </div>
        )}

        {purchaseConfirmed && (
          <div className="purchase-confirmed-msg">
            {Object.values(purchaseStatus).filter((s) => s.status === "pending")
              .length > 0
              ? `Aura copped ${
                  Object.values(purchaseStatus).filter(
                    (s) => s.status === "pending"
                  ).length
                } item(s) for you ✓`
              : "Order submitted — check your Amazon for confirmation ✓"}
          </div>
        )}

        <button className="result-asset retake-btn" onClick={onBack}>
          RETAKE PHOTO
        </button>
      </div>
    </div>
  );
};

export default Results;
