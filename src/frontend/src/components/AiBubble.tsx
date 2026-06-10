import { useEffect, useRef } from "react";
import gsap from "gsap";

// Pastel color blobs: pink, mint, lavender, peach
const BLOB_COLORS = [
  [255, 182, 193],
  [152, 251, 152],
  [216, 191, 246],
  [255, 218, 185],
] as const;

function drawBubble(ctx: CanvasRenderingContext2D, size: number, time: number) {
  ctx.clearRect(0, 0, size, size);

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.42;

  // Clip to circle
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();

  // Base fill
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.fillRect(0, 0, size, size);

  // 4 rotating color blobs
  const step = (Math.PI * 2) / BLOB_COLORS.length;
  BLOB_COLORS.forEach(([rc, gc, bc], i) => {
    const angle = time + step * i;
    const bx = cx + Math.cos(angle) * r * 0.52;
    const by = cy + Math.sin(angle) * r * 0.52;

    const grad = ctx.createRadialGradient(bx, by, 0, bx, by, r * 1.0);
    grad.addColorStop(0, `rgba(${rc},${gc},${bc},0.90)`);
    grad.addColorStop(1, `rgba(${rc},${gc},${bc},0.00)`);

    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  });

  // Specular highlight (top-left gloss)
  const hx = cx - r * 0.28;
  const hy = cy - r * 0.32;
  const hGrad = ctx.createRadialGradient(hx, hy, 0, hx, hy, r * 0.55);
  hGrad.addColorStop(0, "rgba(255,255,255,0.55)");
  hGrad.addColorStop(1, "rgba(255,255,255,0.00)");
  ctx.fillStyle = hGrad;
  ctx.fillRect(0, 0, size, size);

  ctx.restore();

  // Soft outer glow ring
  const glow = ctx.createRadialGradient(cx, cy, r * 0.9, cx, cy, r * 1.28);
  glow.addColorStop(0, "rgba(210,200,240,0.18)");
  glow.addColorStop(1, "rgba(210,200,240,0.00)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 1.28, 0, Math.PI * 2);
  ctx.fill();
}

interface AiBubbleProps {
  /** Diameter of the canvas in px. Default: 280 */
  size?: number;
  /** CSS blur strength in px. Default: 5 */
  blur?: number;
  /** Seconds for one full color rotation. Default: 20 */
  rotationSpeed?: number;
  /** Seconds for one breathing cycle. Default: 7 */
  breatheDuration?: number;
  /** Float distance in px. Default: 14 */
  floatDistance?: number;
}

export function AiBubble({
  size = 280,
  blur = 0,
  rotationSpeed = 20,
  breatheDuration = 7,
  // floatDistance = 14,
  floatDistance = 0,
}: AiBubbleProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const state = useRef({ time: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrapper = wrapperRef.current;
    if (!canvas || !wrapper) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = size;
    canvas.height = size;

    // Redraw every frame via GSAP ticker
    const tick = () => drawBubble(ctx, size, state.current.time);
    gsap.ticker.add(tick);

    // Color rotation (advances the angle each revolution takes `rotationSpeed` seconds)
    gsap.to(state.current, {
      time: Math.PI * 2 * 1000,
      duration: rotationSpeed * 1000,
      ease: "none",
      repeat: -1,
    });

    // Más movimiento: Breath + sway + tilt
    gsap.to(wrapper, {
      scale: 1.06,
      y: -floatDistance,
      x: floatDistance * 0.18,
      rotation: 2,
      transformOrigin: "50% 50%",
      duration: breatheDuration,
      repeat: -1,
      yoyo: true,
      ease: "sine.inOut",
    });

    gsap.to(wrapper, {
      x: -floatDistance * 0.16,
      y: floatDistance * 1.5,
      rotation: -1.5,
      duration: breatheDuration * 0.6,
      repeat: -1,
      yoyo: true,
      ease: "sine.inOut",
    });

    return () => {
      gsap.ticker.remove(tick);
      gsap.killTweensOf(state.current);
      gsap.killTweensOf(wrapper);
    };
  }, [size, blur, rotationSpeed, breatheDuration, floatDistance]);

  return (
    <div
      ref={wrapperRef}
      style={{ display: "inline-block", filter: `blur(${blur}px)` }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
