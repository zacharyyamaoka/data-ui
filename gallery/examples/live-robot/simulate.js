/* A robot arm that does not exist, so the live tier has something to stream (gallery case live-robot; loaded by the
   case page through site.json). SIMULATED: every row is made here, in the page; nothing talks to a robot.

   Three joints follow smooth periodic motions at 500 samples a second each; the motor current comes from the motion
   (inertia, friction, gravity on the shoulder and elbow) plus noise; each motor's temperature follows a first-order
   model of the current's heating, twice a second; five health checks report twice a second; about every 30 s the elbow
   hits something (a 150 ms current spike, an error in the log, its check red for 1.5 s) and the CAN bus drops frames
   (its check stale for a second). The rows go in through the dashboard's live datasets (dataset.append), the push API
   a host such as RobotDx uses (docs/peps/0012-live-data.md §7.1). */

const RATE = 500;          // samples a second per joint
const JOINTS = [
  { name: 'shoulder', a: 0.9, f: 0.11, phase: 0.0, inertia: 0.42, gravity: 1.1, board: 'moteus/1' },
  { name: 'elbow', a: 1.2, f: 0.17, phase: 1.3, inertia: 0.25, gravity: 0.6, board: 'moteus/2' },
  { name: 'wrist', a: 1.6, f: 0.29, phase: 2.1, inertia: 0.06, gravity: 0.0, board: 'moteus/3' },
];
const FAULT_EVERY = 30;    // s between elbow collisions
const TAU = 120;           // s: the motors' thermal time constant (sped up so a minute shows a trend)

let seed = 1;
const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
const noise = (s) => (rand() + rand() + rand() - 1.5) * s;

function motion(j, t) {
  const w = 2 * Math.PI * j.f;
  const q = j.a * Math.sin(w * t + j.phase) + 0.25 * j.a * Math.sin(3 * w * t + 2 * j.phase);
  const qd = j.a * w * Math.cos(w * t + j.phase) + 0.75 * j.a * w * Math.cos(3 * w * t + 2 * j.phase);
  const qdd = -j.a * w * w * Math.sin(w * t + j.phase) - 2.25 * j.a * w * w * Math.sin(3 * w * t + 2 * j.phase);
  return { q, qd, qdd };
}

function start(sets) {
  const { joints, thermal, checks, log } = sets;
  if (!joints || !thermal || !checks || !log) return;
  for (const d of [joints, thermal, checks, log]) d.setStatus('live', 'simulated');
  const t0 = Date.now() / 1000;
  let last = t0, nextSlow = t0, nextFault = t0 + 8, fault = null, can = null, beat = t0;
  const temp = Object.fromEntries(JOINTS.map((j, i) => [j.name, 34 + 2 * i]));
  const heat = Object.fromEntries(JOINTS.map((j) => [j.name, 0]));
  log.append([{ t: t0, source: 'sim', severity: 'info', message: 'simulated arm started: 3 joints at 500 Hz' }]);

  setInterval(() => {
    const now = Date.now() / 1000;
    const n = Math.max(1, Math.round((now - last) * RATE));
    const rows = [];
    for (let i = 1; i <= n; i++) {
      const t = last + ((now - last) * i) / n;
      for (const j of JOINTS) {
        const { q, qd, qdd } = motion(j, t - t0);
        let current = j.inertia * qdd + 0.35 * Math.sign(qd) + 0.08 * qd + j.gravity * Math.cos(q) + noise(0.06);
        // the collision: a short spike on the elbow, and the joint stalls a little
        if (fault && j.name === 'elbow' && t >= fault.at && t < fault.at + 0.15) current += 4.6 * Math.sin(Math.PI * (t - fault.at) / 0.15);
        rows.push({ t, joint: j.name, position: q + noise(0.002), current });
        heat[j.name] += current * current / RATE;
      }
    }
    joints.append(rows);
    if (now >= nextFault) {
      fault = { at: now };
      can = { at: now + 7, until: now + 8 };
      nextFault = now + FAULT_EVERY;
      log.append([{ t: now, source: 'moteus/2', severity: 'error', message: 'elbow: current limit hit (5.1 A); motion held for 150 ms' }]);
    }
    if (now >= nextSlow) {
      nextSlow = now + 0.5;
      const out = [], levels = [];
      for (const j of JOINTS) {
        // first-order heating: P ~ i², cooling toward 30 °C
        const p = heat[j.name] / 0.5;
        heat[j.name] = 0;
        temp[j.name] += ((30 + 9 * p - temp[j.name]) * 0.5) / TAU + noise(0.02);
        out.push({ t: now, joint: j.name, temp_c: Math.round(temp[j.name] * 100) / 100 });
        const hot = temp[j.name] > 44 ? 'warn' : 'ok';
        const hit = fault && j.name === 'elbow' && now - fault.at < 1.5;
        levels.push({ t: now, name: `${j.name} motor`, level: hit ? 'error' : hot, message: hit ? 'current limit hit' : hot === 'warn' ? `temperature ${temp[j.name].toFixed(1)} °C over 44` : `ok · ${temp[j.name].toFixed(1)} °C` });
        if (hot === 'warn' && rand() < 0.08) log.append([{ t: now, source: j.board, severity: 'warn', message: `${j.name}: temperature ${temp[j.name].toFixed(1)} °C over 44` }]);
      }
      const dropped = can && now >= can.at && now < can.until;
      levels.push({ t: now, name: 'CAN bus', level: dropped ? 'stale' : 'ok', message: dropped ? 'no frames for 0.5 s' : 'ok · 1 Mbps' });
      if (dropped && rand() < 0.5) log.append([{ t: now, source: 'fdcanusb', severity: 'warn', message: 'CAN bus: 3 frames dropped' }]);
      const fps = 30 - (rand() < 0.04 ? 6 : 0);
      levels.push({ t: now, name: 'camera', level: fps < 30 ? 'warn' : 'ok', message: `${fps} fps` });
      thermal.append(out);
      checks.append(levels);
    }
    if (now - beat >= 5) {
      beat = now;
      log.append(JOINTS.map((j) => ({ t: now, source: j.board, severity: 'info', message: `${j.name}: heartbeat ok, ${temp[j.name].toFixed(1)} °C` })));
    }
    last = now;
  }, 20);
}

// the dashboard makes its live datasets once its .base is read; it says so with data-dashboard-live
function attach(dash) {
  const sets = dash.datasets || {};
  if (sets.joints && sets.joints.live) { start(sets); return; }
  dash.addEventListener('data-dashboard-live', (e) => start(e.detail.datasets), { once: true });
}

const found = document.querySelector('data-dashboard');
if (found) attach(found);
else customElements.whenDefined('data-dashboard').then(() => { const d = document.querySelector('data-dashboard'); if (d) attach(d); });
