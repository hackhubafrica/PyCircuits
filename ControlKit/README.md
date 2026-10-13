# ControlKit

SISO control-systems workspace: Python (`python-control`, NumPy, SciPy) behind FastAPI, Plotly.js dashboard for time response, stability, Bode, Nyquist, root locus, and PID.

## Run

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies `/api` to the backend.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## API

| Endpoint | Role |
| --- | --- |
| `POST /api/analyze` | Plant normalize + step/impulse + stability + Bode/Nyquist/root locus |
| `POST /api/plant/normalize` | TF/SS canonical forms, poles, zeros, DC gain |
| `POST /api/simulate` | `step` / `impulse` / `custom` |
| `POST /api/stability` | BIBO (OLHP poles) and Lyapunov (eigenvalues of A) |
| `POST /api/bode` | Magnitude, phase, Gm/Pm, crossovers |
| `POST /api/nyquist` | G(jω) real/imag |
| `POST /api/root-locus` | Locus branches vs gain |
| `POST /api/pid/closed-loop` | Unity-feedback PID, overlay step + loop Bode |
| `POST /api/pid/tune` | `zn` (Ku, Pu from margins) or `pole_placement` |
| `POST /api/sf/ackermann` | Ackermann K for desired poles + N̄-tracked step comparison |
| `POST /api/sf/lqr` | LQR K, S, E from diagonal Q and scalar R + N̄-tracked step |
| `POST /api/interconnect` | Block algebra: series/parallel/feedback composition → full analysis |

Ziegler–Nichols tries the ultimate-gain method first (finite phase crossover → Ku, Pu from the Bode margins) and falls back to the open-loop reaction-curve method (FOPDT K, τ, θ fit from the unit-step response, gains from Kp=1.2τ/(Kθ), Ti=2θ, Td=0.5θ) when no finite Ku exists. Pole placement uses `place(A,B,poles)` when the plant is controllable; PID/PD coefficients are also filled when the plant is 2nd-order with 3 (PID) or 2 (PD) desired poles.

State-feedback design (`/api/sf/*`) covers Ackermann's formula (`ct.acker`, SISO, controllability-checked) and LQR (`ct.lqr` with diagonal Q, scalar R), both returning K plus open- vs closed-loop step responses with the N̄ reference pre-gain.

Interconnections (`/api/interconnect`) implement structured block algebra — an ordered forward chain (`ct.series`), an optional parallel chain (`ct.parallel`), and feedback as `none`/`unity`/block chain (`ct.feedback`, negative) over up to 6 blocks of kind `tf`/`ss`/`pid`/`gain` (composite order ≤ 20). The response is a full analysis payload plus the composite transfer function, which the UI can load back as the working plant. A free-form drag-and-drop canvas remains future work.

Desktop/APK packaging is out of scope; wrap this API later.
