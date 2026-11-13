import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3, LineChart as LineIcon } from "lucide-react";
import { CHART_COLORS, type ChartKind, type ChartSpec } from "../lib/chart";
import { formatCompact, formatNumber } from "../lib/format";
import type { Theme } from "../types";

interface TooltipPayload {
  name?: string | number;
  value?: number | string | null;
  color?: string;
  dataKey?: string | number;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayload[]; label?: string | number }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{String(label)}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="chart-tooltip-row">
          <span className="chart-swatch" style={{ background: p.color }} />
          <span className="chart-tooltip-name">{p.name}</span>
          <span className="chart-tooltip-value">
            {typeof p.value === "number" ? formatNumber(p.value) : (p.value ?? "NULL")}
          </span>
        </div>
      ))}
    </div>
  );
}

const GROUP = "__same_scale_group__";

export function ResultChart({ spec, theme }: { spec: ChartSpec; theme: Theme }) {
  const [kind, setKind] = useState<ChartKind>(spec.kind);
  const hasGroup = spec.series.length > 1;
  const [choice, setChoice] = useState<string>(hasGroup ? GROUP : spec.measures[0]);
  const series = choice === GROUP ? spec.series : [choice];
  const c = CHART_COLORS[theme];
  const multi = series.length > 1;

  const longestLabel = Math.max(...spec.data.map((d) => String(d[spec.xKey]).length));
  const rotate = kind === "bar" && (spec.data.length > 12 || (longestLabel > 10 && spec.data.length > 6));

  const axisProps = {
    tick: { fill: c.muted, fontSize: 12 },
    tickLine: false,
  } as const;

  const xAxis = (
    <XAxis
      dataKey={spec.xKey}
      {...axisProps}
      axisLine={{ stroke: c.axis }}
      interval={kind === "bar" && spec.data.length <= 30 ? 0 : "preserveStartEnd"}
      minTickGap={8}
      angle={rotate ? -35 : 0}
      textAnchor={rotate ? "end" : "middle"}
      height={rotate ? 84 : 30}
      tickFormatter={(v: unknown) => {
        const s = String(v);
        return s.length > 16 ? s.slice(0, 15) + "…" : s;
      }}
    />
  );
  const yAxis = (
    <YAxis {...axisProps} axisLine={false} width={64} tickFormatter={(v: number) => formatCompact(v)} />
  );
  const grid = <CartesianGrid vertical={false} stroke={c.grid} />;
  const legend = multi ? (
    <Legend verticalAlign="top" align="left" iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: c.ink, paddingBottom: 8 }} />
  ) : null;

  return (
    <div className="chart-wrap">
      <div className="chart-toolbar">
        <div className="chart-title">
          {series.join(", ")} <span className="muted">by {spec.xKey}</span>
        </div>
        {spec.measures.length > 1 && (
          <select className="measure-select" value={choice} onChange={(e) => setChoice(e.target.value)} aria-label="Measure to plot">
            {hasGroup && <option value={GROUP}>{spec.series.join(" + ")}</option>}
            {spec.measures.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}
        <div className="segmented small" role="group" aria-label="Chart type">
          <button className={kind === "bar" ? "active" : ""} onClick={() => setKind("bar")} title="Bar chart">
            <BarChart3 size={14} /> Bar
          </button>
          <button className={kind === "line" ? "active" : ""} onClick={() => setKind("line")} title="Line chart">
            <LineIcon size={14} /> Line
          </button>
        </div>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height={320}>
          {kind === "bar" ? (
            <BarChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2} barCategoryGap="20%">
              {grid}
              {xAxis}
              {yAxis}
              <Tooltip content={<ChartTooltip />} cursor={{ fill: c.hover }} />
              {legend}
              {series.map((s, i) => (
                <Bar key={s} dataKey={s} name={s} fill={c.series[i]} radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false} />
              ))}
            </BarChart>
          ) : (
            <LineChart data={spec.data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              {grid}
              {xAxis}
              {yAxis}
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: c.axis, strokeWidth: 1 }} />
              {legend}
              {series.map((s, i) => (
                <Line
                  key={s}
                  type="linear"
                  dataKey={s}
                  name={s}
                  stroke={c.series[i]}
                  strokeWidth={2}
                  dot={spec.data.length <= 36 ? { r: 4, fill: c.series[i], stroke: c.surface, strokeWidth: 2 } : false}
                  activeDot={{ r: 5, fill: c.series[i], stroke: c.surface, strokeWidth: 2 }}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      {spec.clipped > 0 && (
        <p className="chart-note">Showing the first {spec.data.length} rows in the chart ({spec.clipped} more in the table).</p>
      )}
    </div>
  );
}
