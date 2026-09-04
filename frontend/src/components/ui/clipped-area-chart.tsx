"use client";
// components/ui/clipped-area-chart.tsx — animated area chart revealed by a clip sweep
import { useId } from "react";
import { motion } from "framer-motion";

interface ClippedAreaChartProps {
  data: number[]; // cumulative values, chronological
  emptyText?: string;
}

export function ClippedAreaChart({ data, emptyText = "No data yet" }: ClippedAreaChartProps) {
  const id = useId().replace(/:/g, "");

  if (data.length < 2) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-zinc-500">
        {emptyText}
      </div>
    );
  }

  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => ({
    x: (i / (data.length - 1)) * 100,
    y: 38 - (v / max) * 32,
  }));
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
  const area = `${line} L100,40 L0,40 Z`;
  const last = pts[pts.length - 1];

  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-48 w-full" role="img"
      aria-label="Cumulative recovered amount over time">
      <defs>
        <linearGradient id={`fill-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
        </linearGradient>
        <clipPath id={`clip-${id}`}>
          <motion.rect x="0" y="0" height="40"
            initial={{ width: 0 }} animate={{ width: 100 }}
            transition={{ duration: 1.4, ease: "easeOut", delay: 0.6 }} />
        </clipPath>
      </defs>
      {/* subtle gridlines */}
      {[10, 20, 30].map((y) => (
        <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="#27272a" strokeWidth="0.2" />
      ))}
      <g clipPath={`url(#clip-${id})`}>
        <path d={area} fill={`url(#fill-${id})`} />
        <path d={line} fill="none" stroke="#10b981" strokeWidth="0.7"
          strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </g>
      <motion.circle cx={last.x} cy={last.y} r="1.2" fill="#10b981"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2 }} />
    </svg>
  );
}
