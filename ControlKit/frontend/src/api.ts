import type {
  AnalyzeResponse,
  IcBlock,
  InterconnectResponse,
  PidClosedLoop,
  PidGains,
  PidTune,
  PlantSpec,
  SfResponse,
  TimeSeries,
} from "./types";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function analyzePlant(plant: PlantSpec, tFinal: number) {
  return post<AnalyzeResponse>("/api/analyze", { plant, t_final: tFinal, n_points: 500 });
}

export function simulateCustom(plant: PlantSpec, t: number[], u: number[]) {
  return post<TimeSeries>("/api/simulate", { plant, kind: "custom", t, u });
}

export function pidClosedLoop(plant: PlantSpec, gains: PidGains, tFinal: number) {
  return post<PidClosedLoop>("/api/pid/closed-loop", { plant, gains, t_final: tFinal, n_points: 500 });
}

export function pidTune(
  plant: PlantSpec,
  method: "zn" | "pole_placement",
  desiredPoles?: { re: number; im: number }[],
) {
  return post<PidTune>("/api/pid/tune", { plant, method, desired_poles: desiredPoles ?? null });
}

export function sfAckermann(plant: PlantSpec, desiredPoles: { re: number; im: number }[]) {
  return post<SfResponse>("/api/sf/ackermann", { plant, desired_poles: desiredPoles });
}

export function sfLqr(plant: PlantSpec, Q: number[], R: number) {
  return post<SfResponse>("/api/sf/lqr", { plant, Q, R });
}

export function interconnect(
  blocks: IcBlock[],
  forward: string[],
  parallel: string[] | null,
  feedback: string | string[],
) {
  return post<InterconnectResponse>("/api/interconnect", { blocks, forward, parallel, feedback });
}
