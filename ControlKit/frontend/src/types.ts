export type FormKind = "tf" | "ss";

export type PlantSpec = {
  form: FormKind;
  num?: number[];
  den?: number[];
  A?: number[][];
  B?: number[][];
  C?: number[][];
  D?: number[][];
};

export type ComplexNumber = { re: number; im: number };

export type TimeSeries = {
  kind: string;
  t: number[];
  y: (number | null)[];
  u: (number | null)[] | null;
  metrics: {
    rise_time?: number | null;
    settling_time?: number | null;
    overshoot?: number | null;
    peak?: number | null;
    peak_time?: number | null;
    steady_state?: number | null;
  };
};

export type BodeData = {
  omega: number[];
  mag_db: (number | null)[];
  phase_deg: (number | null)[];
  gain_margin: number | null;
  gain_margin_db: number | null;
  phase_margin_deg: number | null;
  gain_crossover_omega: number | null;
  phase_crossover_omega: number | null;
};

export type NyquistData = {
  omega: number[];
  real: (number | null)[];
  imag: (number | null)[];
};

export type RootLocusData = {
  gains: (number | null)[];
  branches: { re: (number | null)[]; im: (number | null)[] }[];
  open_loop_poles: ComplexNumber[];
};

export type StabilityData = {
  poles: ComplexNumber[];
  zeros: ComplexNumber[];
  eigenvalues: ComplexNumber[];
  bibo_stable: boolean;
  bibo_reason: string;
  lyapunov_asymptotic: boolean;
  lyapunov_reason: string;
  max_real_pole: number | null;
  max_real_eig: number | null;
};

export type PlantNormalized = {
  num: (number | null)[];
  den: (number | null)[];
  A: (number | null)[][];
  B: (number | null)[][];
  C: (number | null)[][];
  D: (number | null)[][];
  poles: ComplexNumber[];
  zeros: ComplexNumber[];
  dc_gain: number | null;
  order: number;
};

export type AnalyzeResponse = {
  plant: PlantNormalized;
  stability: StabilityData;
  step: TimeSeries;
  impulse: TimeSeries;
  bode: BodeData;
  nyquist: NyquistData;
  root_locus: RootLocusData;
};

export type PidGains = { Kp: number; Ki: number; Kd: number; N?: number | null };

export type PidClosedLoop = {
  gains: PidGains;
  controller_num: (number | null)[];
  controller_den: (number | null)[];
  closed_loop_num: (number | null)[];
  closed_loop_den: (number | null)[];
  plant_step: TimeSeries;
  closed_loop_step: TimeSeries;
  loop_bode: BodeData;
  closed_loop_bode: BodeData;
};

export type PidTune = {
  method: string;
  variant?: string | null;
  fopdt?: { K: number; tau: number; theta: number } | null;
  Ku: number | null;
  Pu: number | null;
  gains: PidGains;
  K: (number | null)[][] | null;
  message: string;
  variants?: Record<string, PidGains> | null;
};

export type SfResponse = {
  method: string;
  K: (number | null)[][];
  S?: (number | null)[][] | null;
  Q?: number[] | null;
  R?: number | null;
  nbar: number | null;
  order: number;
  controllability_rank: number;
  open_loop_poles: ComplexNumber[];
  closed_loop_poles: ComplexNumber[];
  desired_poles: ComplexNumber[] | null;
  open_step: TimeSeries;
  closed_step: TimeSeries;
  message: string;
};

export type IcBlock = {
  id: string;
  kind: "tf" | "ss" | "pid" | "gain";
  num?: number[];
  den?: number[];
  A?: number[][];
  B?: number[][];
  C?: number[][];
  D?: number[][];
  gains?: PidGains;
  k?: number;
};

export type InterconnectResponse = AnalyzeResponse & {
  composite: { num: (number | null)[]; den: (number | null)[] };
  structure: { forward: string[]; parallel: string[] | null; feedback: string | string[] };
};
