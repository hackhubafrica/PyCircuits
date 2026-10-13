import { useCallback, useEffect, useMemo, useState } from "react";
import { analyzePlant, interconnect, pidClosedLoop, pidTune, sfAckermann, sfLqr, simulateCustom } from "./api";
import { PlotlyChart } from "./PlotlyChart";
import type {
  AnalyzeResponse,
  FormKind,
  IcBlock,
  InterconnectResponse,
  PidClosedLoop,
  PidGains,
  PlantSpec,
  SfResponse,
  TimeSeries,
} from "./types";

const STORAGE_KEY = "controllens.plant";

const EXAMPLES: { name: string; plant: PlantSpec }[] = [
  { name: "2nd-order (1 / s²+s+1)", plant: { form: "tf", num: [1], den: [1, 1, 1] } },
  { name: "DC motor 4 / s(s+12)", plant: { form: "tf", num: [4], den: [1, 12, 0] } },
  { name: "Inverted pendulum 1/(s²−9.81)", plant: { form: "tf", num: [1], den: [1, 0, -9.81] } },
  { name: "3rd-order 1/((s+1)(s+2)(s+3))", plant: { form: "tf", num: [1], den: [1, 6, 11, 6] } },
];

type Tab = "step" | "impulse" | "custom" | "bode" | "nyquist" | "rlocus" | "sf" | "interconnect";

function parseList(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const v = Number(s);
      if (!Number.isFinite(v)) throw new Error(`Not a number: ${s}`);
      return v;
    });
}

function parseMatrix(text: string): number[][] {
  const rows = text
    .split(/[;\n]+/)
    .map((r) => r.trim())
    .filter(Boolean)
    .map(parseList);
  if (!rows.length) throw new Error("Matrix is empty.");
  const w = rows[0].length;
  if (rows.some((r) => r.length !== w)) throw new Error("Matrix rows must have equal length.");
  return rows;
}

function fmt(n: number | null | undefined, digits = 3): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a !== 0 && (a >= 1e4 || a < 1e-3)) return n.toExponential(2);
  return n.toFixed(digits);
}

function fmtC(z: { re: number; im: number }): string {
  const im = z.im;
  const sign = im < 0 ? "−" : "+";
  return `${fmt(z.re)} ${sign} ${fmt(Math.abs(im))}j`;
}

function parsePoles(text: string): { re: number; im: number }[] {
  return text
    .split(/[,;]+/)
    .map((tok) => tok.trim())
    .filter(Boolean)
    .map((tok) => {
      const cleaned = tok.replace(/i$/i, "j").replace(/\s/g, "");
      if (/^[+-]?\d*\.?\d+(e[+-]?\d+)?$/i.test(cleaned)) {
        return { re: Number(cleaned), im: 0 };
      }
      const m = cleaned.match(/^([+-]?\d*\.?\d*)?([+-]\d*\.?\d*)j$/i);
      if (!m) throw new Error(`Could not parse pole "${tok}"`);
      const rePart = m[1];
      const imPart = m[2];
      const re = !rePart || rePart === "+" ? 0 : rePart === "-" ? 0 : Number(rePart);
      const im = imPart === "+" ? 1 : imPart === "-" ? -1 : Number(imPart);
      return { re, im };
    });
}

function defaultPolesFor(order: number): string {
  if (order <= 1) return "-1";
  if (order === 2) return "-1+2j, -1-2j";
  if (order === 3) return "-2, -1+2j, -1-2j";
  const parts: string[] = ["-1+1j", "-1-1j"];
  while (parts.length < order) parts.push("-2");
  return parts.join(", ");
}

function parseCsvTU(text: string): { t: number[]; u: number[] } {
  const t: number[] = [];
  const u: number[] = [];
  for (const line of text.split(/\n+/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const parts = trimmed.split(/[,\s]+/).filter(Boolean).map(Number);
    if (parts.length < 2 || parts.some((x) => !Number.isFinite(x))) {
      throw new Error(`Bad sample line: ${trimmed}`);
    }
    const time = parts[0];
    if (t.length && time <= t[t.length - 1]) {
      throw new Error(`Time values must be strictly increasing (t=${time} repeats or is out of order).`);
    }
    t.push(time);
    u.push(parts[1]);
  }
  if (t.length < 2) throw new Error("Need at least two t,u samples.");
  return { t, u };
}

function fmtPoly(coeffs: (number | null)[]): string {
  return coeffs.map((v) => fmt(v, 4)).join(", ");
}

function maxAbs(vals: (number | null)[]): number {
  let m = 0;
  for (const v of vals) {
    if (v !== null && Number.isFinite(v)) m = Math.max(m, Math.abs(v));
  }
  return m;
}

function moveItem<T>(arr: T[], i: number, dir: -1 | 1): T[] {
  const j = i + dir;
  if (j < 0 || j >= arr.length) return arr;
  const copy = arr.slice();
  const tmp = copy[i];
  copy[i] = copy[j];
  copy[j] = tmp;
  return copy;
}

type BlockKind = "tf" | "ss" | "pid" | "gain";

type BlockRow = {
  key: number;
  id: string;
  kind: BlockKind;
  num: string;
  den: string;
  a: string;
  b: string;
  c: string;
  d: string;
  gains: string;
  k: string;
};

let nextBlockKey = 1;

function newBlockRow(id: string): BlockRow {
  return {
    key: nextBlockKey++,
    id,
    kind: "tf",
    num: "1",
    den: "1, 1, 1",
    a: "0, 1; -1, -1",
    b: "0; 1",
    c: "1, 0",
    d: "0",
    gains: "1, 0, 0",
    k: "1",
  };
}

function ChainEditor(props: {
  label: string;
  chain: string[];
  options: string[];
  onAdd: (id: string) => void;
  onMove: (i: number, dir: -1 | 1) => void;
  onRemove: (i: number) => void;
}) {
  const free = props.options.filter((o) => !props.chain.includes(o));
  return (
    <div>
      <label>{props.label}</label>
      <div className="chips">
        {props.chain.length === 0 ? <span className="hint">(empty)</span> : null}
        {props.chain.map((id, i) => (
          <span className="chip" key={`${id}-${i}`}>
            {id}
            <button className="chip-btn" title="Move up" onClick={() => props.onMove(i, -1)}>
              ↑
            </button>
            <button className="chip-btn" title="Move down" onClick={() => props.onMove(i, 1)}>
              ↓
            </button>
            <button className="chip-btn" title="Remove" onClick={() => props.onRemove(i)}>
              ×
            </button>
          </span>
        ))}
        {free.length ? (
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) props.onAdd(e.target.value);
            }}
          >
            <option value="">+ add block…</option>
            {free.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : null}
      </div>
    </div>
  );
}

function line(x: (number | null)[], y: (number | null)[], name: string, extra: Record<string, unknown> = {}) {
  return {
    type: "scatter",
    mode: "lines",
    x,
    y,
    name,
    hovertemplate: "%{x:.4g}<br>%{y:.4g}<extra>" + name + "</extra>",
    ...extra,
  };
}

export default function App() {
  const [form, setForm] = useState<FormKind>("tf");
  const [numText, setNumText] = useState("1");
  const [denText, setDenText] = useState("1, 1, 1");
  const [aText, setAText] = useState("0, 1; -1, -1");
  const [bText, setBText] = useState("0; 1");
  const [cText, setCText] = useState("1, 0");
  const [dText, setDText] = useState("0");
  const [tFinal, setTFinal] = useState(12);
  const [tab, setTab] = useState<Tab>("step");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("Ready");
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [custom, setCustom] = useState<TimeSeries | null>(null);
  const [customCsv, setCustomCsv] = useState("0, 0\n1, 1\n4, 1\n8, 0");
  const [gains, setGains] = useState<PidGains>({ Kp: 1, Ki: 0, Kd: 0 });
  const [pid, setPid] = useState<PidClosedLoop | null>(null);
  const [polesText, setPolesText] = useState("-2, -1+2j, -1-2j");
  const [polesTouched, setPolesTouched] = useState(false);
  const [tuneMsg, setTuneMsg] = useState<string | null>(null);
  const [sfMode, setSfMode] = useState<"ackermann" | "lqr">("ackermann");
  const [sf, setSf] = useState<SfResponse | null>(null);
  const [sfMsg, setSfMsg] = useState<string | null>(null);
  const [qText, setQText] = useState("1, 1");
  const [rText, setRText] = useState("1");
  const [blocks, setBlocks] = useState<BlockRow[]>(() => {
    const plantRow = newBlockRow("b1");
    const pidRow = newBlockRow("b2");
    pidRow.kind = "pid";
    return [plantRow, pidRow];
  });
  const [fwdChain, setFwdChain] = useState<string[]>(["b2", "b1"]);
  const [parChain, setParChain] = useState<string[]>([]);
  const [fbChoice, setFbChoice] = useState<string>("unity");
  const [icResult, setIcResult] = useState<InterconnectResponse | null>(null);
  const [icMsg, setIcMsg] = useState<string | null>(null);

  const plantFromForm = useCallback((): PlantSpec => {
    if (form === "tf") {
      return { form, num: parseList(numText), den: parseList(denText) };
    }
    const B = parseMatrix(bText);
    const C = parseMatrix(cText);
    const D = parseMatrix(dText);
    return { form, A: parseMatrix(aText), B, C, D };
  }, [form, numText, denText, aText, bText, cText, dText]);

  const runAnalyze = useCallback(async () => {
    setError(null);
    setStatus("Computing…");
    try {
      const plant = plantFromForm();
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ form, numText, denText, aText, bText, cText, dText, tFinal }));
      const data = await analyzePlant(plant, tFinal);
      setAnalysis(data);
      setPolesText((prev) => (polesTouched ? prev : defaultPolesFor(data.plant.order)));
      setStatus("Plant analyzed");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("Error");
    }
  }, [plantFromForm, form, numText, denText, aText, bText, cText, dText, tFinal, polesTouched]);

  useEffect(() => {
    let nextForm: FormKind = "tf";
    let nextNum = "1";
    let nextDen = "1, 1, 1";
    let nextA = "0, 1; -1, -1";
    let nextB = "0; 1";
    let nextC = "1, 0";
    let nextD = "0";
    let nextT = 12;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Record<string, string | number>;
        if (saved.form === "tf" || saved.form === "ss") nextForm = saved.form;
        if (typeof saved.numText === "string") nextNum = saved.numText;
        if (typeof saved.denText === "string") nextDen = saved.denText;
        if (typeof saved.aText === "string") nextA = saved.aText;
        if (typeof saved.bText === "string") nextB = saved.bText;
        if (typeof saved.cText === "string") nextC = saved.cText;
        if (typeof saved.dText === "string") nextD = saved.dText;
        if (typeof saved.tFinal === "number") nextT = saved.tFinal;
      }
    } catch {
      /* keep defaults */
    }
    setForm(nextForm);
    setNumText(nextNum);
    setDenText(nextDen);
    setAText(nextA);
    setBText(nextB);
    setCText(nextC);
    setDText(nextD);
    setTFinal(nextT);
    setStatus("Computing…");
    try {
      const plant: PlantSpec =
        nextForm === "tf"
          ? { form: "tf", num: parseList(nextNum), den: parseList(nextDen) }
          : { form: "ss", A: parseMatrix(nextA), B: parseMatrix(nextB), C: parseMatrix(nextC), D: parseMatrix(nextD) };
      void analyzePlant(plant, nextT)
        .then((data) => {
          setAnalysis(data);
          setPolesText((prev) => (prev === "-2, -1+2j, -1-2j" ? defaultPolesFor(data.plant.order) : prev));
          setStatus("Plant analyzed");
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("Error");
        });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("Error");
    }
  }, []);

  useEffect(() => {
    if (!analysis) return;
    const handle = window.setTimeout(() => {
      try {
        const plant = plantFromForm();
        void pidClosedLoop(plant, gains, tFinal)
          .then((data) => {
            setPid(data);
            setTuneMsg(null);
          })
          .catch((e: unknown) => {
            setPid(null);
            setTuneMsg(e instanceof Error ? e.message : String(e));
          });
      } catch (e) {
        setTuneMsg(e instanceof Error ? e.message : String(e));
      }
    }, 200);
    return () => window.clearTimeout(handle);
  }, [gains, analysis, plantFromForm, tFinal]);

  const applyExample = (plant: PlantSpec) => {
    setForm(plant.form);
    if (plant.form === "tf") {
      setNumText((plant.num ?? []).join(", "));
      setDenText((plant.den ?? []).join(", "));
    }
  };

  const runCustom = async () => {
    setError(null);
    try {
      const { t, u } = parseCsvTU(customCsv);
      const data = await simulateCustom(plantFromForm(), t, u);
      setCustom(data);
      setTab("custom");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runTune = async (method: "zn" | "pole_placement") => {
    setTuneMsg(null);
    try {
      const poles = method === "pole_placement" ? parsePoles(polesText) : undefined;
      const result = await pidTune(plantFromForm(), method, poles);
      setGains({ ...result.gains, N: gains.N ?? null });
      setTuneMsg(result.message);
    } catch (e) {
      setTuneMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const runSf = async () => {
    setSfMsg(null);
    setError(null);
    setStatus("Designing…");
    try {
      const plant = plantFromForm();
      let res: SfResponse;
      if (sfMode === "ackermann") {
        res = await sfAckermann(plant, parsePoles(polesText));
      } else {
        const Q = parseList(qText);
        const R = Number(rText);
        if (!Number.isFinite(R)) throw new Error("R must be a number.");
        res = await sfLqr(plant, Q, R);
      }
      setSf(res);
      setSfMsg(res.message);
      setStatus("State feedback designed");
    } catch (e) {
      setSfMsg(e instanceof Error ? e.message : String(e));
      setStatus("Error");
    }
  };

  const toIcBlock = (row: BlockRow): IcBlock => {
    switch (row.kind) {
      case "tf":
        return { id: row.id, kind: "tf", num: parseList(row.num), den: parseList(row.den) };
      case "ss":
        return {
          id: row.id,
          kind: "ss",
          A: parseMatrix(row.a),
          B: parseMatrix(row.b),
          C: parseMatrix(row.c),
          D: parseMatrix(row.d),
        };
      case "pid": {
        const g = parseList(row.gains);
        if (g.length < 1 || g.length > 3) throw new Error(`Block ${row.id}: gains must be Kp, Ki, Kd.`);
        return { id: row.id, kind: "pid", gains: { Kp: g[0] ?? 0, Ki: g[1] ?? 0, Kd: g[2] ?? 0 } };
      }
      case "gain": {
        const g = parseList(row.k);
        if (g.length !== 1) throw new Error(`Block ${row.id}: enter a single gain k.`);
        return { id: row.id, kind: "gain", k: g[0] };
      }
    }
  };

  const blockIds = blocks.map((b) => b.id);

  const addBlock = () => {
    if (blocks.length >= 6) return;
    const used = new Set(blockIds);
    let n = blocks.length + 1;
    while (used.has(`b${n}`)) n += 1;
    setBlocks([...blocks, newBlockRow(`b${n}`)]);
  };

  const removeBlock = (key: number) => {
    const row = blocks.find((r) => r.key === key);
    if (!row) return;
    setBlocks(blocks.filter((r) => r.key !== key));
    setFwdChain(fwdChain.filter((id) => id !== row.id));
    setParChain(parChain.filter((id) => id !== row.id));
    if (fbChoice === row.id) setFbChoice("unity");
  };

  const renameBlock = (key: number, newId: string) => {
    const row = blocks.find((r) => r.key === key);
    if (!row || row.id === newId) return;
    const old = row.id;
    setBlocks(blocks.map((r) => (r.key === key ? { ...r, id: newId } : r)));
    setFwdChain(fwdChain.map((id) => (id === old ? newId : id)));
    setParChain(parChain.map((id) => (id === old ? newId : id)));
    if (fbChoice === old) setFbChoice(newId);
  };

  const setBlockField = (key: number, field: string, value: string) => {
    setBlocks(blocks.map((r) => (r.key === key ? ({ ...r, [field]: value } as BlockRow) : r)));
  };

  const runInterconnect = async () => {
    setError(null);
    setIcMsg(null);
    setStatus("Composing…");
    try {
      if (!fwdChain.length) throw new Error("Add at least one block to the forward path.");
      const payload: IcBlock[] = blocks.map(toIcBlock);
      const fb: string | string[] = fbChoice === "none" || fbChoice === "unity" ? fbChoice : [fbChoice];
      const res = await interconnect(payload, fwdChain, parChain.length ? parChain : null, fb);
      setIcResult(res);
      const fbLabel =
        typeof res.structure.feedback === "string" ? res.structure.feedback : res.structure.feedback.join(" → ");
      setIcMsg(`Composite of order ${res.plant.order} · feedback: ${fbLabel}`);
      setStatus("Interconnection analyzed");
      setTab("interconnect");
    } catch (e) {
      setIcMsg(e instanceof Error ? e.message : String(e));
      setStatus("Error");
    }
  };

  const useComposite = async () => {
    if (!icResult) return;
    setError(null);
    try {
      const toArr = (vals: (number | null)[]): number[] =>
        vals.map((v, i) => {
          if (v === null || !Number.isFinite(v)) throw new Error(`Composite coefficient ${i} is not finite.`);
          return v;
        });
      const numArr = toArr(icResult.composite.num);
      const denArr = toArr(icResult.composite.den);
      const numStr = numArr.join(", ");
      const denStr = denArr.join(", ");
      setForm("tf");
      setNumText(numStr);
      setDenText(denStr);
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ form: "tf", numText: numStr, denText: denStr, aText, bText, cText, dText, tFinal }),
      );
      setStatus("Computing…");
      const data = await analyzePlant({ form: "tf", num: numArr, den: denArr }, tFinal);
      setAnalysis(data);
      setPolesText((prev) => (polesTouched ? prev : defaultPolesFor(data.plant.order)));
      setTab("step");
      setStatus("Composite loaded as plant");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("Error");
    }
  };

  const plot = useMemo(() => {
    const accent = "#6ea8ff";
    const closed = "#3dd68c";
    if (tab === "sf") {
      if (!sf) {
        return { data: [] as unknown[], layout: { title: "State-feedback design — pick Ackermann or LQR and press Design" } };
      }
      const openMax = maxAbs(sf.open_step.y);
      const clMax = maxAbs(sf.closed_step.y);
      const openDiverges = openMax > 1e3 && openMax > 100 * Math.max(clMax, 1e-12);
      const data: unknown[] = [];
      if (!openDiverges) {
        data.push(
          line(sf.open_step.t, sf.open_step.y, "Open-loop step", {
            xaxis: "x",
            yaxis: "y",
            line: { color: accent, dash: "dot" },
          }),
        );
      }
      data.push(
        line(sf.closed_step.t, sf.closed_step.y, "Closed-loop step", {
          xaxis: "x",
          yaxis: "y",
          line: { color: closed },
        }),
      );
      data.push({
        type: "scatter",
        mode: "markers",
        name: "Open-loop poles",
        x: sf.open_loop_poles.map((p) => p.re),
        y: sf.open_loop_poles.map((p) => p.im),
        xaxis: "x2",
        yaxis: "y2",
        marker: { color: "#ff6b6b", size: 9, symbol: "x" },
      });
      data.push({
        type: "scatter",
        mode: "markers",
        name: "Closed-loop poles",
        x: sf.closed_loop_poles.map((p) => p.re),
        y: sf.closed_loop_poles.map((p) => p.im),
        xaxis: "x2",
        yaxis: "y2",
        marker: { color: "#3dd68c", size: 10, symbol: "diamond" },
      });
      if (sf.desired_poles && sf.desired_poles.length) {
        data.push({
          type: "scatter",
          mode: "markers",
          name: "Desired poles",
          x: sf.desired_poles.map((p) => p.re),
          y: sf.desired_poles.map((p) => p.im),
          xaxis: "x2",
          yaxis: "y2",
          marker: { color: "#e6c35c", size: 10, symbol: "circle-open" },
        });
      }
      return {
        data,
        layout: {
          title: `State feedback — ${sf.method === "lqr" ? "LQR" : "Ackermann"}`,
          grid: { rows: 1, columns: 2, pattern: "independent" },
          xaxis: { title: "t (s)" },
          yaxis: { title: "y" },
          xaxis2: { title: "Real" },
          yaxis2: { title: "Imag", zeroline: true },
        },
      };
    }
    if (tab === "interconnect") {
      if (!icResult) {
        return { data: [] as unknown[], layout: { title: "Compose blocks, then press “Compose & analyze”" } };
      }
      return {
        data: [line(icResult.step.t, icResult.step.y, "Composite step", { line: { color: accent } })],
        layout: { title: "Interconnection step response", xaxis: { title: "t (s)" }, yaxis: { title: "y" } },
      };
    }
    if (!analysis) return { data: [] as unknown[], layout: {} as Record<string, unknown> };
    if (tab === "step" || tab === "impulse") {
      const series = tab === "step" ? analysis.step : analysis.impulse;
      const data = [line(series.t, series.y, tab === "step" ? "Plant y(t)" : "Impulse y(t)", { line: { color: accent } })];
      if (tab === "step" && pid) {
        data.push(
          line(pid.closed_loop_step.t, pid.closed_loop_step.y, "Closed-loop y(t)", { line: { color: closed } }),
        );
      }
      return {
        data,
        layout: { title: tab === "step" ? "Step response" : "Impulse response", xaxis: { title: "t (s)" }, yaxis: { title: "y" } },
      };
    }
    if (tab === "custom") {
      const data: unknown[] = [];
      if (custom) {
        data.push(line(custom.t, custom.y, "y(t)", { line: { color: accent } }));
        if (custom.u) data.push(line(custom.t, custom.u, "u(t)", { line: { color: "#e6c35c", dash: "dot" } }));
      }
      return { data, layout: { title: "Arbitrary input", xaxis: { title: "t (s)" }, yaxis: { title: "y, u" } } };
    }
    if (tab === "bode") {
      const b = analysis.bode;
      const cl = pid?.loop_bode;
      const traces: unknown[] = [
        line(b.omega, b.mag_db, "Plant |G|", { yaxis: "y", line: { color: accent }, xaxis: "x" }),
        line(b.omega, b.phase_deg, "Plant ∠G", { yaxis: "y2", line: { color: "#c89bff" }, xaxis: "x2" }),
      ];
      if (cl) {
        traces.push(line(cl.omega, cl.mag_db, "Loop |CG|", { yaxis: "y", line: { color: closed }, xaxis: "x" }));
        traces.push(line(cl.omega, cl.phase_deg, "Loop ∠CG", { yaxis: "y2", line: { color: "#8fe0b4" }, xaxis: "x2" }));
      }
      return {
        data: traces,
        layout: {
          title: "Bode plot",
          grid: { rows: 2, columns: 1, pattern: "independent" },
          xaxis: { type: "log", title: "" },
          xaxis2: { type: "log", title: "ω (rad/s)", matches: "x" },
          yaxis: { title: "Magnitude (dB)" },
          yaxis2: { title: "Phase (deg)" },
          hovermode: "x unified",
        },
      };
    }
    if (tab === "nyquist") {
      return {
        data: [
          line(analysis.nyquist.real, analysis.nyquist.imag, "G(jω)", { line: { color: accent } }),
          {
            type: "scatter",
            mode: "markers",
            x: [-1],
            y: [0],
            name: "−1 + 0j",
            marker: { color: "#ff6b6b", size: 10, symbol: "x" },
          },
        ],
        layout: {
          title: "Nyquist diagram",
          xaxis: { title: "Re G(jω)", zeroline: true, scaleanchor: "y" },
          yaxis: { title: "Im G(jω)", zeroline: true },
        },
      };
    }
    const traces: unknown[] = analysis.root_locus.branches.map((br, i) =>
      line(br.re, br.im, `Branch ${i + 1}`, { line: { width: 2 } }),
    );
    traces.push({
      type: "scatter",
      mode: "markers",
      x: analysis.stability.poles.map((p) => p.re),
      y: analysis.stability.poles.map((p) => p.im),
      name: "Open-loop poles",
      marker: { color: "#ff6b6b", size: 9, symbol: "x" },
    });
    traces.push({
      type: "scatter",
      mode: "markers",
      x: analysis.stability.zeros.map((z) => z.re),
      y: analysis.stability.zeros.map((z) => z.im),
      name: "Zeros",
      marker: { color: "#6ea8ff", size: 9, symbol: "circle-open" },
    });
    return {
      data: traces,
      layout: {
        title: "Root locus",
        xaxis: { title: "Real", zeroline: true, scaleanchor: "y" },
        yaxis: { title: "Imag", zeroline: true },
      },
    };
  }, [analysis, tab, pid, custom, sf, icResult]);

  const st = analysis?.stability;
  const stepM = analysis?.step.metrics;
  const bode = analysis?.bode;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Control<span>Lens</span>
        </div>
        <div className="hint">SISO plant analysis · python-control backend</div>
        <div className="status">{status}</div>
      </header>

      <div className="workspace">
        <aside className="rail">
          <h2>System definition</h2>
          <label>Representation</label>
          <select value={form} onChange={(e) => setForm(e.target.value as FormKind)}>
            <option value="tf">Transfer function G(s)</option>
            <option value="ss">State-space (A, B, C, D)</option>
          </select>

          {form === "tf" ? (
            <>
              <label>Numerator (high order → low)</label>
              <input value={numText} onChange={(e) => setNumText(e.target.value)} 
              style={{
                    backgroundColor: "#2a2d3e", // Dark background matching your theme
                    color: "#ffffff",           // Crisp white text
                    border: "1px solid #4a4e69",  // Clear border for visibility
                    padding: "8px",
                    borderRadius: "4px"
                  }}/>
              <label>Denominator</label>
              <input value={denText} onChange={(e) => setDenText(e.target.value)} style={{
        backgroundColor: "#2a2d3e",
        color: "#ffffff",
        border: "1px solid #4a4e69",
        padding: "8px",
        borderRadius: "4px"
      }} />
            </>
          ) : (
            <>
              <label>A (rows with ;)</label>
              <textarea value={aText} onChange={(e) => setAText(e.target.value)} />
              <label>B</label>
              <textarea value={bText} onChange={(e) => setBText(e.target.value)} />
              <label>C</label>
              <textarea value={cText} onChange={(e) => setCText(e.target.value)} />
              <label>D</label>
              <input value={dText} onChange={(e) => setDText(e.target.value)} />
            </>
          )}

          <label>Simulation horizon t_final (s)</label>
          <input type="number" min={0.1} step={0.5} value={tFinal} onChange={(e) => setTFinal(Number(e.target.value))} />

          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={() => void runAnalyze()}>
              Analyze
            </button>
          </div>

          <h2 style={{ marginTop: 16 }}>Examples</h2>
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex.name} onClick={() => applyExample(ex.plant)}>
                {ex.name}
              </button>
            ))}
          </div>

          <h2>Arbitrary input</h2>
          <label>CSV lines: t, u</label>
          <textarea value={customCsv} onChange={(e) => setCustomCsv(e.target.value)} />
          <button onClick={() => void runCustom()}>Simulate u(t)</button>
          {error ? <div className="error">{error}</div> : null}
        </aside>

        <section className="center">
          <nav className="tabs">
            {(
              [
                ["step", "Step"],
                ["impulse", "Impulse"],
                ["custom", "Custom u(t)"],
                ["bode", "Bode"],
                ["nyquist", "Nyquist"],
                ["rlocus", "Root locus"],
                ["sf", "SF / LQR"],
                ["interconnect", "Interconnect"],
              ] as const
            ).map(([id, label]) => (
              <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "sf" ? (
            <div className="tool">
              <div className="row">
                <button className={sfMode === "ackermann" ? "primary" : ""} onClick={() => setSfMode("ackermann")}>
                  Ackermann
                </button>
                <button className={sfMode === "lqr" ? "primary" : ""} onClick={() => setSfMode("lqr")}>
                  LQR
                </button>
                {sfMode === "ackermann" ? (
                  <span className="hint">Desired poles come from the “Desired poles” field in the PID bar below.</span>
                ) : (
                  <>
                    <input
                      className="w-m"
                      value={qText}
                      title="Q diagonal entries"
                      placeholder="Q diag: 1, 1"
                      onChange={(e) => setQText(e.target.value)}
                    />
                    <input
                      className="w-s"
                      value={rText}
                      title="R input weight"
                      placeholder="R"
                      onChange={(e) => setRText(e.target.value)}
                    />
                  </>
                )}
                <button className="primary" onClick={() => void runSf()}>
                  Design
                </button>
              </div>
              {sfMsg ? <p className="reason">{sfMsg}</p> : null}
              {sf ? (
                <>
                  <div className="row">
                    <div className="metric">
                      <span>K</span>
                      <span>{(sf.K[0] ?? []).map((v) => fmt(v)).join(", ")}</span>
                    </div>
                    <div className="metric">
                      <span>N̄</span>
                      <span>{fmt(sf.nbar)}</span>
                    </div>
                    <div className="metric">
                      <span>ctrb rank</span>
                      <span>
                        {sf.controllability_rank}/{sf.order}
                      </span>
                    </div>
                  </div>
                  <p className="reason">Closed-loop poles: {sf.closed_loop_poles.map(fmtC).join(" · ")}</p>
                </>
              ) : null}
            </div>
          ) : null}
          {tab === "interconnect" ? (
            <div className="tool">
              <div>
                {blocks.map((row) => (
                  <div className="block-row" key={row.key}>
                    <input
                      className="w-id"
                      value={row.id}
                      title="Block id"
                      onChange={(e) => renameBlock(row.key, e.target.value)}
                    />
                    <select value={row.kind} onChange={(e) => setBlockField(row.key, "kind", e.target.value)}>
                      <option value="tf">G(s)</option>
                      <option value="ss">A,B,C,D</option>
                      <option value="pid">PID</option>
                      <option value="gain">gain</option>
                    </select>
                    {row.kind === "tf" ? (
                      <>
                        <input
                          className="w-m"
                          value={row.num}
                          placeholder="num"
                          onChange={(e) => setBlockField(row.key, "num", e.target.value)}
                        />
                        <input
                          className="w-m"
                          value={row.den}
                          placeholder="den"
                          onChange={(e) => setBlockField(row.key, "den", e.target.value)}
                        />
                      </>
                    ) : row.kind === "ss" ? (
                      <>
                        <input className="w-m" value={row.a} placeholder="A" onChange={(e) => setBlockField(row.key, "a", e.target.value)} />
                        <input className="w-s" value={row.b} placeholder="B" onChange={(e) => setBlockField(row.key, "b", e.target.value)} />
                        <input className="w-s" value={row.c} placeholder="C" onChange={(e) => setBlockField(row.key, "c", e.target.value)} />
                        <input className="w-s" value={row.d} placeholder="D" onChange={(e) => setBlockField(row.key, "d", e.target.value)} />
                      </>
                    ) : row.kind === "pid" ? (
                      <input
                        className="w-m"
                        value={row.gains}
                        placeholder="Kp, Ki, Kd"
                        onChange={(e) => setBlockField(row.key, "gains", e.target.value)}
                      />
                    ) : (
                      <input className="w-s" value={row.k} placeholder="k" onChange={(e) => setBlockField(row.key, "k", e.target.value)} />
                    )}
                    <button className="chip-btn" title="Remove block" onClick={() => removeBlock(row.key)}>
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <div className="row">
                <button onClick={addBlock} disabled={blocks.length >= 6}>
                  + Block
                </button>
                <span className="hint">{blocks.length}/6 blocks</span>
              </div>
              <div className="row" style={{ marginTop: 8, alignItems: "flex-start" }}>
                <div style={{ flex: 2, minWidth: 220 }}>
                  <ChainEditor
                    label="Forward path (series order)"
                    chain={fwdChain}
                    options={blockIds}
                    onAdd={(id) => setFwdChain([...fwdChain, id])}
                    onMove={(i, dir) => setFwdChain(moveItem(fwdChain, i, dir))}
                    onRemove={(i) => setFwdChain(fwdChain.filter((_, j) => j !== i))}
                  />
                </div>
                <div style={{ flex: 2, minWidth: 220 }}>
                  <ChainEditor
                    label="Parallel with (optional)"
                    chain={parChain}
                    options={blockIds}
                    onAdd={(id) => setParChain([...parChain, id])}
                    onMove={(i, dir) => setParChain(moveItem(parChain, i, dir))}
                    onRemove={(i) => setParChain(parChain.filter((_, j) => j !== i))}
                  />
                </div>
                <div style={{ flex: 1, minWidth: 140 }}>
                  <label>Feedback</label>
                  <select value={fbChoice} onChange={(e) => setFbChoice(e.target.value)}>
                    <option value="none">none (open)</option>
                    <option value="unity">unity (−1)</option>
                    {blocks.map((b) => (
                      <option key={b.id} value={b.id}>
                        H(s) = {b.id}
                      </option>
                    ))}
                  </select>
                </div>
                <button className="primary" onClick={() => void runInterconnect()}>
                  Compose &amp; analyze
                </button>
                {icResult ? <button onClick={() => void useComposite()}>Use as plant →</button> : null}
              </div>
              {icResult ? (
                <div className="row" style={{ marginTop: 6 }}>
                  <div className="metric">
                    <span>num</span>
                    <span>{fmtPoly(icResult.composite.num)}</span>
                  </div>
                  <div className="metric">
                    <span>den</span>
                    <span>{fmtPoly(icResult.composite.den)}</span>
                  </div>
                  <div className="metric">
                    <span>order</span>
                    <span>{icResult.plant.order}</span>
                  </div>
                </div>
              ) : null}
              {icMsg ? <p className="reason">{icMsg}</p> : null}
            </div>
          ) : null}
          <div className="plot-wrap">
            <PlotlyChart
              data={plot.data}
              layout={plot.layout}
              height={tab === "bode" ? 520 : tab === "sf" ? 420 : 400}
            />
          </div>
        </section>

        <aside className="rail right">
          <h2>Stability</h2>
          {st ? (
            <>
              <span className={`pill ${st.bibo_stable ? "ok" : "no"}`}>BIBO {st.bibo_stable ? "stable" : "unstable"}</span>
              <span className={`pill ${st.lyapunov_asymptotic ? "ok" : "no"}`}>
                Lyapunov {st.lyapunov_asymptotic ? "AS" : "not AS"}
              </span>
              <p className="reason">{st.bibo_reason}</p>
              <p className="reason">{st.lyapunov_reason}</p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Poles</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {st.poles.map((p, i) => (
                    <tr key={`p${i}`}>
                      <td>p{i + 1}</td>
                      <td>{fmtC(p)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table className="table">
                <thead>
                  <tr>
                    <th>Zeros</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {st.zeros.length ? (
                    st.zeros.map((z, i) => (
                      <tr key={`z${i}`}>
                        <td>z{i + 1}</td>
                        <td>{fmtC(z)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={2}>none</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          ) : (
            <p className="reason">Analyze a plant to see poles, zeros, and stability flags.</p>
          )}

          <h2>Time-domain</h2>
          <div className="metric">
            <span>Overshoot</span>
            <span>{fmt(stepM?.overshoot)} %</span>
          </div>
          <div className="metric">
            <span>Rise time</span>
            <span>{fmt(stepM?.rise_time)} s</span>
          </div>
          <div className="metric">
            <span>Settling time</span>
            <span>{fmt(stepM?.settling_time)} s</span>
          </div>
          <div className="metric">
            <span>Peak</span>
            <span>{fmt(stepM?.peak)}</span>
          </div>
          <div className="metric">
            <span>DC gain</span>
            <span>{fmt(analysis?.plant.dc_gain)}</span>
          </div>

          <h2>Margins</h2>
          <div className="metric">
            <span>Gm</span>
            <span>{fmt(bode?.gain_margin_db)} dB</span>
          </div>
          <div className="metric">
            <span>Pm</span>
            <span>{fmt(bode?.phase_margin_deg)} deg</span>
          </div>
          <div className="metric">
            <span>ωg (gain xover)</span>
            <span>{fmt(bode?.gain_crossover_omega)} rad/s</span>
          </div>
          <div className="metric">
            <span>ωp (phase xover)</span>
            <span>{fmt(bode?.phase_crossover_omega)} rad/s</span>
          </div>
          {pid ? (
            <>
              <h2>Loop margins (CG)</h2>
              <div className="metric">
                <span>Gm</span>
                <span>{fmt(pid.loop_bode.gain_margin_db)} dB</span>
              </div>
              <div className="metric">
                <span>Pm</span>
                <span>{fmt(pid.loop_bode.phase_margin_deg)} deg</span>
              </div>
            </>
          ) : null}
        </aside>
      </div>

      <footer className="pid-bar">
        <div className="pid-grid">
          <div className="sliders">
            <h2>PID controller</h2>
            <label>
              Kp {fmt(gains.Kp, 2)}
              <input
                type="range"
                min={0}
                max={20}
                step={0.05}
                value={gains.Kp}
                onChange={(e) => setGains({ ...gains, Kp: Number(e.target.value) })}
              />
            </label>
            <label>
              Ki {fmt(gains.Ki, 2)}
              <input
                type="range"
                min={0}
                max={20}
                step={0.05}
                value={gains.Ki}
                onChange={(e) => setGains({ ...gains, Ki: Number(e.target.value) })}
              />
            </label>
            <label>
              Kd {fmt(gains.Kd, 2)}
              <input
                type="range"
                min={0}
                max={8}
                step={0.02}
                value={gains.Kd}
                onChange={(e) => setGains({ ...gains, Kd: Number(e.target.value) })}
              />
            </label>
          </div>
          <div>
            <h2>Tuning</h2>
            <div className="row">
              <button onClick={() => void runTune("zn")}>Ziegler–Nichols</button>
              <button onClick={() => void runTune("pole_placement")}>Pole placement</button>
            </div>
            <label>Desired poles (state-feedback / 2nd-order PID map)</label>
            <input
              value={polesText}
              onChange={(e) => {
                setPolesText(e.target.value);
                setPolesTouched(true);
              }}
                style={{
                backgroundColor: "#2a2d3e",
                color: "#ffffff",
                border: "1px solid #4a4e69",
                padding: "8px",
                borderRadius: "4px"
              }}
            />
            {tuneMsg ? <p className="reason">{tuneMsg}</p> : null}
          </div>
          <div>
            <h2>Closed-loop step</h2>
            <div className="metric">
              <span>Overshoot</span>
              <span>{fmt(pid?.closed_loop_step.metrics.overshoot)} %</span>
            </div>
            <div className="metric">
              <span>Settling</span>
              <span>{fmt(pid?.closed_loop_step.metrics.settling_time)} s</span>
            </div>
            <div className="metric">
              <span>C(s) num</span>
              <span>{pid ? pid.controller_num.map((v) => fmt(v)).join(", ") : "—"}</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
