<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Athens Traffic Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  /* ——— Palette: Greek road-signage daylight ———
     sign blue #0F4C9A · asphalt ink #23272B · paper #EDEFF1
     clear green #1E7A46 · works amber #DB9A0F · closed red #C0392B */
  :root{
    --blue:#0F4C9A; --blue-deep:#0B3B78; --ink:#23272B; --paper:#EDEFF1;
    --card:#FFFFFF; --line:#D6DADF; --mut:#6A7178;
    --ok:#1E7A46; --warn:#DB9A0F; --alert:#C0392B;
    --disp:"Barlow Semi Condensed",sans-serif; --body:"Barlow",system-ui,sans-serif;
  }
  *{box-sizing:border-box;margin:0}
  body{background:var(--paper);color:var(--ink);font-family:var(--body);
       font-size:16px;line-height:1.45;padding:16px;max-width:760px;margin:0 auto}

  /* Signature: header set as a Greek blue direction sign */
  .sign{background:var(--blue);color:#fff;border-radius:12px;
        border:3px solid #fff;outline:2px solid var(--blue-deep);
        padding:14px 18px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
  .sign h1{font-family:var(--disp);font-weight:700;font-size:1.5rem;
           letter-spacing:.02em;text-transform:uppercase}
  .sign .km{font-family:var(--disp);font-weight:600;opacity:.85;font-size:.95rem}

  .answer{margin:20px 0 6px;font-family:var(--disp);font-weight:700;
          font-size:2rem;line-height:1.1;display:flex;align-items:center;gap:12px}
  .lamp{width:18px;height:18px;border-radius:50%;flex:none;
        box-shadow:inset 0 -2px 3px rgba(0,0,0,.25)}
  .sub{color:var(--mut);font-size:.9rem;margin-bottom:20px}

  h2{font-family:var(--disp);font-weight:600;font-size:.85rem;text-transform:uppercase;
     letter-spacing:.09em;color:var(--mut);margin:26px 0 10px}

  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;
        padding:12px 14px;margin-bottom:10px}
  .card.new{border-left:5px solid var(--alert)}
  .card .src{font-family:var(--disp);font-weight:600;font-size:.78rem;color:var(--blue);
             text-transform:uppercase;letter-spacing:.06em}
  .card .t{font-weight:600;margin:2px 0}
  .card .d{color:var(--mut);font-size:.92rem;white-space:pre-line}
  .card a{color:var(--blue);text-decoration:none;font-size:.9rem}
  .badge{float:right;background:var(--alert);color:#fff;border-radius:5px;
         font-family:var(--disp);font-size:.72rem;font-weight:700;padding:2px 7px;
         text-transform:uppercase;letter-spacing:.05em}

  table{width:100%;border-collapse:collapse;background:var(--card);
        border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{padding:9px 12px;text-align:left;font-size:.92rem}
  th{font-family:var(--disp);font-weight:600;font-size:.75rem;text-transform:uppercase;
     letter-spacing:.07em;color:var(--mut);border-bottom:1px solid var(--line)}
  tr+tr td{border-top:1px solid var(--line)}
  td .lamp{width:11px;height:11px;display:inline-block;vertical-align:-1px;margin-right:7px}
  .num{font-variant-numeric:tabular-nums}

  .empty{background:var(--card);border:1px dashed var(--line);border-radius:10px;
         padding:18px;color:var(--mut);text-align:center}
  footer{margin:28px 0 8px;color:var(--mut);font-size:.8rem;text-align:center}
  @media (prefers-reduced-motion:no-preference){
    .card,.answer{animation:in .25s ease-out both}
    @keyframes in{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
  }
</style>
</head>
<body>
<header class="sign">
  <h1>Κέντρο Αθήνας</h1>
  <span class="km">traffic monitor</span>
</header>

<div class="answer" id="answer"><span class="lamp" style="background:var(--mut)"></span>Loading…</div>
<div class="sub" id="checked"></div>

<h2>Active now on the sources</h2>
<div id="events"></div>

<h2>Source health</h2>
<div id="health"></div>

<h2>Recent notifications</h2>
<div id="history"></div>

<footer id="foot"></footer>

<script>
const $ = id => document.getElementById(id);
const esc = s => (s||"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function ago(iso){
  if(!iso) return "never";
  const m = Math.round((Date.now()-new Date(iso))/60000);
  if(m<1) return "just now";
  if(m<60) return m+" min ago";
  const h = Math.round(m/60);
  if(h<48) return h+" h ago";
  return Math.round(h/24)+" days ago";
}
async function load(){
  let d;
  try{
    d = await (await fetch("data.json?t="+Date.now())).json();
  }catch(e){
    $("answer").innerHTML = '<span class="lamp" style="background:var(--warn)"></span>No data yet';
    $("checked").textContent = "data.json not found — has the monitor completed a run since Pages was enabled?";
    return;
  }
  const evs = d.active_events||[], srcs = d.sources||[];
  const failing = srcs.filter(s=>!s.ok).length;
  const fresh = evs.filter(e=>e.new_this_run).length;

  const col = evs.length ? "var(--alert)" : (failing ? "var(--warn)" : "var(--ok)");
  const txt = evs.length
      ? evs.length + " active event" + (evs.length>1?"s":"")
      : "Nothing active right now";
  $("answer").innerHTML = `<span class="lamp" style="background:${col}"></span>${txt}`;
  $("checked").textContent = "Last check " + ago(d.generated_at)
      + (fresh ? ` · ${fresh} new this run` : "")
      + (failing ? ` · ${failing} source(s) failing` : "");

  $("events").innerHTML = evs.length ? evs.map(e=>`
    <div class="card${e.new_this_run?" new":""}">
      ${e.new_this_run?'<span class="badge">new</span>':""}
      <div class="src">${esc(e.source)}</div>
      <div class="t">${esc(e.title)}</div>
      ${e.details?`<div class="d">${esc(e.details)}</div>`:""}
      <a href="${esc(e.url)}" target="_blank" rel="noopener">Open source page →</a>
    </div>`).join("")
    : '<div class="empty">All monitored pages are quiet — no recent traffic events detected.</div>';

  $("health").innerHTML = `<table><tr><th>Source</th><th>Last success</th><th class="num">Items</th></tr>`
    + srcs.map(s=>`<tr>
        <td><span class="lamp" style="background:${s.ok?"var(--ok)":(s.consecutive_failures>=6?"var(--alert)":"var(--warn)")}"></span>${esc(s.name)}</td>
        <td class="num">${ago(s.last_success)}${s.ok?"":" · failing ×"+s.consecutive_failures}</td>
        <td class="num">${s.items}</td></tr>`).join("") + "</table>";

  const hist = d.recent_notifications||[];
  $("history").innerHTML = hist.length ? hist.map(n=>`
    <div class="card">
      <div class="src">${esc(n.source)} · ${ago(n.time)}</div>
      <div class="t"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a></div>
    </div>`).join("")
    : '<div class="empty">No notifications sent yet.</div>';

  const runs = d.runs||[];
  $("foot").textContent = runs.length
    ? `${runs.length} runs recorded · refreshes automatically every 5 minutes`
    : "";
}
load();
setInterval(load, 5*60*1000);
</script>
</body>
</html>
