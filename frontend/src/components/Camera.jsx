// src/components/Camera.jsx
import { useState, useRef, useEffect } from "react";
import { animate, stagger } from "animejs";
import cameraImg from "../assets/final_camera1.png";
import sayImg from "../assets/final_say.png";
import cheeseImg from "../assets/final_cheese.png";

// NOTE: The video/loading overlay is positioned to align with the camera screen
// in final_camera1.png. Adjust top/left/width/height below if the image changes.
const SCREEN = { top: "160px", left: "45px", width: "570px", height: "415px" };

const Camera = ({ onCapture, isLoading }) => {
  const [isPhotoTaken, setIsPhotoTaken] = useState(false);
  const [capturedUrl, setCapturedUrl] = useState(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  // Start camera feed on mount; clean up on unmount
  useEffect(() => {
    let active = true;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((err) => console.warn("[Camera] camera access denied:", err));

    return () => {
      active = false;
      if (streamRef.current)
        streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const playBounce = (target) => {
    animate(target, {
      scale: [1, 1.15, 1],
      duration: 300,
      easing: "easeOutElastic(1, .6)",
    });
  };

  const handleRetake = async () => {
    // Clear the frozen frame
    setCapturedUrl(null);
    onCapture && onCapture(null);
    // Restart the live stream
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch (err) {
      console.warn("[Camera] retake camera access denied:", err);
    }
  };

  const handleShutterClick = () => {
    if (isLoading) return;

    setIsPhotoTaken(true);
    // Camera body: quick squish then snap back to exactly 1
    animate(".digicam-body", {
      scale: [1, 0.95, 1],
      duration: 150,
      easing: "easeInOutQuad",
    });
    // Say/Cheese stickers: pop up then hard-return to scale 1 so they don't stay big
    animate([".say-text", ".cheese-text"], {
      scale: [1, 1.3, 1],
      rotate: [0, 8, -8, 0],
      duration: 500,
      delay: stagger(60),
      easing: "easeInOutQuad",
    });
    setTimeout(() => setIsPhotoTaken(false), 2000);

    // Capture frame from video stream into canvas → blob → freeze on screen
    if (videoRef.current && canvasRef.current && streamRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      // Mirror the draw to match the CSS scaleX(-1) on the video
      const ctx = canvas.getContext("2d");
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(video, 0, 0);
      canvas.toBlob(
        (blob) => {
          // Stop the live stream — we don't need it anymore
          streamRef.current.getTracks().forEach((t) => t.stop());
          // Freeze: show the captured frame on the camera screen
          setCapturedUrl(URL.createObjectURL(blob));
          setTimeout(() => onCapture && onCapture(blob), 350);
        },
        "image/jpeg",
        0.92,
      );
    } else {
      // Camera not available — continue without photo
      setTimeout(() => onCapture && onCapture(null), 350);
    }
  };

  return (
    <div
      className="camera-wrapper"
      style={{
        position: "absolute",
        top: "100px",
        left: "50px",
        width: "1000px",
        zIndex: 20,
      }}
    >
      <img
        src={sayImg}
        className="say-text"
        onClick={(e) => playBounce(e.currentTarget)}
        style={{
          opacity: 1,
          position: "absolute",
          top: "-10px",
          left: "150px",
          width: "100px",
          cursor: "pointer",
        }}
      />

      <img
        src={cheeseImg}
        className="cheese-text"
        onClick={(e) => playBounce(e.currentTarget)}
        style={{
          opacity: 1,
          position: "absolute",
          top: "10px",
          left: "220px",
          width: "200px",
          cursor: "pointer",
        }}
      />

      {/* Live viewfinder — hidden once photo is taken */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          position: "absolute",
          top: SCREEN.top,
          left: SCREEN.left,
          width: SCREEN.width,
          height: SCREEN.height,
          objectFit: "cover",
          borderRadius: "4px",
          zIndex: 25,
          transform: "scaleX(-1)",
          display: capturedUrl ? "none" : "block",
        }}
      />

      {/* Frozen captured frame — shown after shutter click */}
      {capturedUrl && (
        <img
          src={capturedUrl}
          alt="captured"
          style={{
            position: "absolute",
            top: SCREEN.top,
            left: SCREEN.left,
            width: SCREEN.width,
            height: SCREEN.height,
            objectFit: "cover",
            borderRadius: "4px",
            zIndex: 25,
            pointerEvents: "none",
          }}
        />
      )}

      {/* Retake button — sits below the camera body */}
      {capturedUrl && (
        <button
          onClick={handleRetake}
          style={{
            position: "absolute",
            top: "600px",
            left: SCREEN.left,
            zIndex: 50,
            padding: "8px 28px",
            background: "rgba(0,0,0,0.7)",
            color: "white",
            border: "2px solid rgba(255,255,255,0.7)",
            borderRadius: "20px",
            fontSize: "13px",
            fontWeight: "bold",
            cursor: "pointer",
            pointerEvents: "auto",
          }}
        >
          ↺ Retake
        </button>
      )}

      {/* Loading overlay on camera screen */}
      {isLoading && (
        <div
          style={{
            position: "absolute",
            top: SCREEN.top,
            left: SCREEN.left,
            width: SCREEN.width,
            height: SCREEN.height,
            backgroundColor: "rgba(0,0,0,0.65)",
            borderRadius: "4px",
            zIndex: 30,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontSize: "14px",
            fontWeight: "bold",
            textAlign: "center",
          }}
        >
          Aura is cooking... 🍳
        </div>
      )}

      {/* Hidden canvas used for frame capture */}
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* Shutter Button — unchanged position, disabled while loading */}
      <button
        onClick={handleShutterClick}
        disabled={isLoading}
        style={{
          position: "absolute",
          top: "290px",
          left: "688px",
          width: "50px",
          height: "50px",
          borderRadius: "50%",
          backgroundColor: isLoading ? "#aaa" : "#ffffff",
          border: "3px solid #ddd",
          cursor: isLoading ? "not-allowed" : "pointer",
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          zIndex: 50,
          transition: "transform 0.1s",
        }}
        onMouseDown={(e) => {
          if (!isLoading) e.currentTarget.style.transform = "scale(0.9)";
        }}
        onMouseUp={(e) => {
          e.currentTarget.style.transform = "scale(1)";
        }}
      />

      <img
        src={cameraImg}
        className="digicam-body"
        style={{ width: "900px", display: "block" }}
      />
    </div>
  );
};

export default Camera;
