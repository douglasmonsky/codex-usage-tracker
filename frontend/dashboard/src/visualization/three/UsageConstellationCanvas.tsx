import { useEffect, useRef, useState } from 'react';

import styles from './UsageConstellation.module.css';
import { createUsageConstellationScene, type UsageConstellationScene } from './usageConstellationScene';
import type { UsageConstellationModel, UsageConstellationPoint } from './types';

type UsageConstellationCanvasProps = {
  model: UsageConstellationModel;
  onOpenCall: (recordId: string) => void;
  onUnavailable: () => void;
  resetSignal: number;
};

type HoverState = {
  point: UsageConstellationPoint;
  x: number;
  y: number;
};

export default function UsageConstellationCanvas(props: UsageConstellationCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<UsageConstellationScene | null>(null);
  const openCallRef = useRef(props.onOpenCall);
  const unavailableRef = useRef(props.onUnavailable);
  const [hovered, setHovered] = useState<HoverState | null>(null);
  openCallRef.current = props.onOpenCall;
  unavailableRef.current = props.onUnavailable;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      sceneRef.current = createUsageConstellationScene({
        canvas,
        model: props.model,
        onHover: (point, position) => {
          setHovered(point && position ? { point, ...position } : null);
        },
        onOpen: point => openCallRef.current(point.recordId),
      });
    } catch {
      unavailableRef.current();
    }
    return () => {
      sceneRef.current?.destroy();
      sceneRef.current = null;
    };
  }, [props.model]);

  useEffect(() => {
    if (props.resetSignal > 0) sceneRef.current?.reset();
  }, [props.resetSignal]);

  return (
    <div className={styles.canvasFrame}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        data-testid="usage-constellation-canvas"
        aria-hidden="true"
      />
      {hovered ? (
        <div className={styles.tooltip} style={{ left: hovered.x, top: hovered.y }} aria-hidden="true">
          <strong>{hovered.point.model}</strong>
          <span>{hovered.point.totalTokens.toLocaleString()} tokens</span>
          <span>{Math.round(hovered.point.cachedPercent)}% cached</span>
          <span>{hovered.point.credits.toFixed(2)} estimated credits</span>
          <small>{hovered.point.thread}</small>
        </div>
      ) : null}
    </div>
  );
}
