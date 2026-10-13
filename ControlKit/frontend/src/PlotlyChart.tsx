import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";

type Props = {
  data: unknown[];
  layout?: Record<string, unknown>;
  height?: number;
};

export function PlotlyChart({ data, layout, height = 360 }: Props) {
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const merged = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "#12141a",
      font: { color: "#c8cdd8", size: 12, family: "IBM Plex Sans, Segoe UI, sans-serif" },
      margin: { t: 36, r: 18, b: 48, l: 56 },
      xaxis: { gridcolor: "#2a2e38", zerolinecolor: "#3a3f4b", color: "#c8cdd8" },
      yaxis: { gridcolor: "#2a2e38", zerolinecolor: "#3a3f4b", color: "#c8cdd8" },
      legend: { orientation: "h", y: 1.12, font: { size: 11 } },
      ...layout,
      height,
    };
    void Plotly.react(node, data, merged, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
    return () => {
      Plotly.purge(node);
    };
  }, [data, layout, height]);

  return <div ref={el} className="plot" />;
}
