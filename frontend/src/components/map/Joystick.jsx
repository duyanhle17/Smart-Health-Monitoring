import { useCallback, useEffect, useRef, useState } from 'react';
import { STICK_RADIUS_PX, stickVector } from '../../lib/joystickMotion';

const BASE_PX = STICK_RADIUS_PX * 2 + 24;
const KNOB_PX = 56;

/**
 * Analog stick for nudging the selected worker. It reports a direction vector
 * and leaves the animation loop to the caller: a thumb held still fires no
 * further pointer events, so the caller must keep applying the last vector.
 *
 * `onRelease` fires once per gesture and is where the caller commits.
 */
export default function Joystick({ onVector, onRelease, label }) {
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const activeRef = useRef(false);
  const baseRef = useRef(null);

  const updateFrom = useCallback((clientX, clientY) => {
    const base = baseRef.current;
    if (!base) return;
    const rect = base.getBoundingClientRect();
    const vector = stickVector(
      clientX - (rect.left + rect.width / 2),
      clientY - (rect.top + rect.height / 2)
    );
    setKnob({ x: vector.x * STICK_RADIUS_PX, y: vector.y * STICK_RADIUS_PX });
    onVector(vector);
  }, [onVector]);

  const end = useCallback(() => {
    if (!activeRef.current) return;
    activeRef.current = false;
    setKnob({ x: 0, y: 0 });
    onVector({ x: 0, y: 0 });
    onRelease();
  }, [onVector, onRelease]);

  // A thumb routinely leaves the stick's own bounds mid-gesture, so movement
  // and release are tracked on the window rather than on the element.
  useEffect(() => {
    const move = (e) => {
      if (activeRef.current) updateFrom(e.clientX, e.clientY);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
  }, [updateFrom, end]);

  return (
    <div
      ref={baseRef}
      data-testid="joystick"
      onPointerDown={(e) => {
        e.stopPropagation();
        activeRef.current = true;
        updateFrom(e.clientX, e.clientY);
      }}
      className="relative rounded-full border-4 border-black bg-white/70 flex items-center justify-center"
      style={{ width: BASE_PX, height: BASE_PX, touchAction: 'none' }}
    >
      <span className="absolute -top-7 font-heavy uppercase text-[11px] whitespace-nowrap bg-black text-white px-2 py-0.5">
        {label}
      </span>
      <div
        data-testid="joystick-knob"
        className="rounded-full bg-black border-4 border-white pointer-events-none"
        style={{
          width: KNOB_PX,
          height: KNOB_PX,
          transform: `translate(${knob.x}px, ${knob.y}px)`,
        }}
      />
    </div>
  );
}
