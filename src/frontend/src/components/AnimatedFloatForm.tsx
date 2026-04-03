import React, { useEffect, useRef } from 'react';

const AnimatedFloatFormEnhanced = () => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const timeRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    const setCanvasDimensions = () => {
      canvas.width = 200;
      canvas.height = 200;
    };
    setCanvasDimensions();

    const draw = (timestamp) => {
      if (!ctx) return;
      
      timeRef.current += 0.016;
      const time = timeRef.current;
      
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Animated gradient with moving origin point
      const gradient = ctx.createLinearGradient(
        30 + Math.sin(time * 0.8) * 20,
        30 + Math.cos(time * 0.6) * 15,
        170 + Math.cos(time * 0.5) * 20,
        170 + Math.sin(time * 0.7) * 15
      );
      
      gradient.addColorStop(0, '#f8f7f5');
      gradient.addColorStop(0.2, '#f8f7f5');
      gradient.addColorStop(0.5, '#ffa178');
      gradient.addColorStop(0.8, '#ffa178');
      gradient.addColorStop(1, '#ff9066');
      
      // Animated scale effect (subtle breathing)
      const scale = 1 + Math.sin(time * 1.2) * 0.02;
      const centerX = 100;
      const centerY = 100;
      const radius = 95 * scale;
      
      ctx.save();
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();
      
      // Animated glow effect
      ctx.shadowBlur = 25 + Math.sin(time * 2) * 5;
      ctx.shadowColor = `rgba(255, 161, 120, ${0.3 + Math.sin(time * 1.5) * 0.1})`;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius - 5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 161, 120, 0.15)';
      ctx.fill();
      
      // Reset shadow
      ctx.shadowBlur = 0;
      
      // Animated orbiting particles
      for (let i = 0; i < 12; i++) {
        const angle = time * 1.2 + (i * Math.PI * 2 / 12);
        const orbitRadius = 105 + Math.sin(time * 1.8 + i) * 8;
        const x = centerX + Math.cos(angle) * orbitRadius;
        const y = centerY + Math.sin(angle) * orbitRadius;
        
        const particleSize = 2.5 + Math.sin(time * 3 + i) * 1;
        const opacity = 0.3 + Math.sin(time * 2.5 + i) * 0.2;
        
        ctx.beginPath();
        ctx.arc(x, y, particleSize, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 161, 120, ${opacity})`;
        ctx.fill();
      }
      
      // Inner animated wave effect
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 3; i++) {
        const waveRadius = 50 + Math.sin(time * 2 + i) * 15;
        ctx.beginPath();
        ctx.arc(centerX, centerY, waveRadius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255, 161, 120, ${0.1 - i * 0.03})`;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.restore();
      
      ctx.restore();
      
      animationRef.current = requestAnimationFrame(draw);
    };
    
    animationRef.current = requestAnimationFrame(draw);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []);

  return (
    <div style={{
      position: 'absolute',
      top: '100px',
      right: '0',
      width: '200px',
      height: '200px',
      zIndex: -1,
      pointerEvents: 'none'
    }}>
      <canvas
        ref={canvasRef}
        style={{
          width: '200px',
          height: '200px',
          filter: 'blur(12px)',
          borderRadius: '100px',
          display: 'block'
        }}
      />
    </div>
  );
};

export default AnimatedFloatFormEnhanced;