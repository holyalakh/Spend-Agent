import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartArtifact } from "../types";

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
}

function getKeys(artifact: ChartArtifact): { nameKey: string; valueKey: string } {
  const sample = artifact.data[0] ?? {};
  const keys = Object.keys(sample);

  const nameKey =
    artifact.x_key ??
    artifact.name_key ??
    keys.find((k) => typeof sample[k] === "string") ??
    keys[0] ??
    "name";

  const valueKey =
    artifact.y_key ??
    artifact.value_key ??
    keys.find((k) => typeof sample[k] === "number") ??
    keys[1] ??
    "value";

  return { nameKey, valueKey };
}

const COLORS = ["#0078d4", "#4ec9b0", "#dcdcaa", "#ce9178", "#c586c0", "#569cd6"];

export function ChartArtifactView({ artifact }: ChartArtifactViewProps) {
  const { nameKey, valueKey } = getKeys(artifact);

  const chartData = artifact.data.map((row) => ({
    name: String(row[nameKey] ?? ""),
    value: Number(row[valueKey] ?? 0),
  }));

  return (
    <div className="rounded-lg border border-cursor-border bg-cursor-input p-4">
      {artifact.title && (
        <h3 className="mb-3 text-sm font-medium text-cursor-text">{artifact.title}</h3>
      )}
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {artifact.chart_type === "line" ? (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3e3e3e" />
              <XAxis dataKey="name" tick={{ fill: "#6b6b6b", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b6b6b", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#2d2d2d", border: "1px solid #3e3e3e", fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "#cccccc" }} />
              <Line type="monotone" dataKey="value" stroke="#0078d4" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          ) : artifact.chart_type === "pie" ? (
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
              >
                {chartData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#2d2d2d", border: "1px solid #3e3e3e", fontSize: 12 }}
              />
            </PieChart>
          ) : (
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3e3e3e" />
              <XAxis dataKey="name" tick={{ fill: "#6b6b6b", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b6b6b", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#2d2d2d", border: "1px solid #3e3e3e", fontSize: 12 }}
              />
              <Bar dataKey="value" fill="#0078d4" radius={[4, 4, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
