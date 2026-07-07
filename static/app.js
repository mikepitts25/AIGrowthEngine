/* AIGrowthEngine frontend — vanilla JS, no build step. */

const root = document.getElementById('view-root');
let currentView = 'dashboard';

// ------------------------------------------------------------ helpers

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `fixed bottom-5 right-5 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg ${isError ? 'bg-red-600' : 'bg-slate-900'}`;
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('hidden'), 3500);
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard'));
}

function scoreBadge(score) {
  const color = score >= 60 ? 'bg-emerald-100 text-emerald-800' : score >= 35 ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-600';
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${color}">${score}</span>`;
}

const STATUS_COLORS = {
  new: 'bg-blue-100 text-blue-800', contacted: 'bg-amber-100 text-amber-800',
  responded: 'bg-purple-100 text-purple-800', customer: 'bg-emerald-100 text-emerald-800',
  archived: 'bg-slate-200 text-slate-500',
};
const LEAD_STATUSES = ['new', 'contacted', 'responded', 'customer', 'archived'];
const PLATFORM_LABELS = { x: '𝕏 / Twitter', linkedin: 'LinkedIn', reddit: 'Reddit', instagram: 'Instagram' };

// ------------------------------------------------------------ navigation

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => show(btn.dataset.view));
});

function show(view) {
  currentView = view;
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  ({ dashboard: renderDashboard, discover: renderDiscover, agency: renderAgency, leads: renderLeads, content: renderContent, settings: renderSettings }[view])();
}

async function refreshAiBadge() {
  try {
    const { ai_enabled, llm } = await api('/api/settings');
    const label = llm?.providers?.[llm.provider]?.label || llm?.provider || 'AI';
    document.getElementById('ai-badge').innerHTML = ai_enabled
      ? `<span class="w-2 h-2 rounded-full bg-emerald-400"></span> AI: ${esc(label)}`
      : '<span class="w-2 h-2 rounded-full bg-amber-400"></span> AI: templates only <span class="text-slate-500">(configure in Settings)</span>';
  } catch {}
}

// ------------------------------------------------------------ dashboard

async function renderDashboard() {
  root.innerHTML = '<p class="text-slate-500">Loading…</p>';
  const d = await api('/api/dashboard');
  const lc = d.leads, pc = d.posts;
  const stat = (label, value, sub) => `
    <div class="bg-white rounded-xl shadow-sm p-5">
      <p class="text-sm text-slate-500">${label}</p>
      <p class="text-3xl font-bold mt-1">${value}</p>
      ${sub ? `<p class="text-xs text-slate-400 mt-1">${sub}</p>` : ''}
    </div>`;
  const miniLead = l => `
    <div class="py-2.5 flex items-start gap-3">
      ${scoreBadge(l.intent_score)}
      <div class="min-w-0 flex-1">
        <a href="${esc(l.source_url || '#')}" target="_blank" class="font-medium text-sm hover:text-emerald-600 line-clamp-1">${esc(l.title)}</a>
        <p class="text-xs text-slate-500">${esc(l.vertical || l.community || '')}${l.phone ? ' · 📞 ' + esc(l.phone) : ''}${l.next_action ? ' · ⏰ ' + esc(l.next_action) : ''}</p>
      </div>
    </div>`;
  const chips = (obj, color) => Object.entries(obj).map(([k, v]) =>
    `<span class="px-2 py-0.5 rounded-full text-xs ${color}">${esc(k)}: <b>${v}</b></span>`).join(' ');
  const totalLeads = Object.values(lc).reduce((a, b) => a + b, 0);
  const ap = d.autopilot || {};
  root.innerHTML = `
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold">Dashboard</h2>
      <a href="/callsheet" target="_blank" class="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm font-semibold">🖨 Today's call sheet</a>
    </div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      ${stat('Total leads', totalLeads, `${lc.new || 0} new · ${lc.contacted || 0} contacted`)}
      ${stat('Customers won', lc.customer || 0, `${lc.responded || 0} in conversation`)}
      ${stat('Outreach this week', d.outreach_7d ?? 0, `${d.contacted_7d ?? 0} marked contacted · ${d.outreach_drafts} drafts total`)}
      ${stat('Content posts', Object.values(pc).reduce((a, b) => a + b, 0), `${pc.draft || 0} drafts · ${pc.posted || 0} posted`)}
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 mb-6 flex items-center gap-3 flex-wrap text-sm">
      <span class="font-semibold">${ap.enabled ? '🤖 Autopilot ON' : '🤖 Autopilot off'}</span>
      ${ap.enabled ? `<span class="text-slate-500 text-xs">every ${ap.interval_hours}h</span>` : ''}
      ${ap.last_run ? `<span class="text-slate-500 text-xs">last run ${esc(ap.last_run.slice(0, 16).replace('T', ' '))} UTC — ${esc(ap.last_result || '')}</span>` : '<span class="text-slate-400 text-xs">never run</span>'}
      <button id="ap-run" class="ml-auto text-xs border px-3 py-1.5 rounded-lg hover:bg-slate-50">▶ Run now</button>
      <button class="text-xs text-emerald-600 hover:underline" onclick="show('settings')">configure</button>
    </div>
    <div class="grid lg:grid-cols-2 gap-6 mb-6">
      <div class="bg-white rounded-xl shadow-sm p-5">
        <div class="flex items-center justify-between mb-2">
          <h3 class="font-semibold">⏰ Follow-ups due</h3>
          <button class="text-sm text-emerald-600 hover:underline" onclick="renderLeads('contacted', '')">pipeline →</button>
        </div>
        ${d.followups_due.length === 0
          ? '<p class="text-sm text-slate-500">Nothing due. Set next-action dates on leads to build your follow-up queue.</p>'
          : `<div class="divide-y">${d.followups_due.map(miniLead).join('')}</div>`}
      </div>
      <div class="bg-white rounded-xl shadow-sm p-5">
        <div class="flex items-center justify-between mb-2">
          <h3 class="font-semibold">📞 Today's call targets</h3>
          <button class="text-sm text-emerald-600 hover:underline" onclick="renderLeads('new', 'business')">all →</button>
        </div>
        ${d.call_targets.length === 0
          ? `<p class="text-sm text-slate-500">No uncontacted businesses. <button class="text-emerald-600 underline" onclick="show('agency')">Find some →</button></p>`
          : `<div class="divide-y">${d.call_targets.map(miniLead).join('')}</div>`}
      </div>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-5 mb-6">
      <h3 class="font-semibold mb-2">📊 Pipeline breakdown</h3>
      <div class="flex flex-wrap gap-1.5 mb-2">${chips(d.by_vertical, 'bg-indigo-100 text-indigo-800') || '<span class="text-sm text-slate-500">no business leads yet</span>'}</div>
      <div class="flex flex-wrap gap-1.5">${chips(d.by_source, 'bg-slate-100 text-slate-700')}</div>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold">🔥 Hottest leads</h3>
        <button class="text-sm text-emerald-600 hover:underline" onclick="show('leads')">View all →</button>
      </div>
      ${d.top_leads.length === 0
        ? `<p class="text-sm text-slate-500">No leads yet. Head to <button class="text-emerald-600 underline" onclick="show('discover')">Find Leads</button> to discover potential customers.</p>`
        : `<div class="divide-y">${d.top_leads.map(miniLead).join('')}</div>`}
    </div>`;
  window.show = show;
  document.getElementById('ap-run').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = 'Running… (~1 min)';
    try {
      const r = await api('/api/autopilot/run', { method: 'POST' });
      toast('Autopilot: ' + r.result);
      renderDashboard();
    } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = '▶ Run now'; }
  });
}

// ------------------------------------------------------------ discover

async function renderDiscover() {
  const { profile, reddit_oauth_enabled, ai_enabled } = await api('/api/settings');
  root.innerHTML = `
    <h2 class="text-2xl font-bold mb-2">Find Leads <span class="text-slate-400 text-lg">— course buyers</span></h2>
    <p class="text-slate-500 mb-6 text-sm">Scan Bluesky, Hacker News, and Reddit for people actively asking about making money with AI. Results are scored for buying intent (0–100) and saved to your Leads pipeline.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 mb-6">
      <label class="block text-sm font-medium mb-1">Keywords <span class="text-slate-400 font-normal">(one per line — defaults from Settings)</span></label>
      <textarea id="kw" rows="4" class="w-full border rounded-lg px-3 py-2 text-sm">${esc((profile.keywords || []).join('\n'))}</textarea>
      <div class="flex flex-wrap items-center gap-4 mt-3">
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" id="src-bsky" checked class="rounded"> Bluesky <span class="text-slate-400">(free)</span></label>
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" id="src-hn" checked class="rounded"> Hacker News</label>
        <label class="flex items-center gap-2 text-sm ${reddit_oauth_enabled ? '' : 'opacity-60'}"><input type="checkbox" id="src-reddit" ${reddit_oauth_enabled ? 'checked' : ''} class="rounded"> Reddit ${reddit_oauth_enabled ? '' : '<span class="text-slate-400">(often 403s without REDDIT_CLIENT_ID)</span>'}</label>
        <label class="flex items-center gap-2 text-sm">Min score <input type="number" id="min-score" value="25" min="0" max="100" class="w-16 border rounded px-2 py-1"></label>
        <button id="run-discover" class="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-semibold">🔎 Discover leads</button>
      </div>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 mb-6 flex items-center gap-2 flex-wrap">
      <span class="text-sm font-medium mr-1">Power tools:</span>
      <button id="disc-draft-all" class="text-sm border px-3 py-1.5 rounded-lg hover:bg-slate-50">⚡ Draft replies for top 10</button>
      <span id="disc-tools-result" class="text-xs text-slate-500"></span>
    </div>
    <div id="discover-result"></div>`;

  document.getElementById('disc-draft-all').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '⚡ Drafting…';
    const out = document.getElementById('disc-tools-result');
    try {
      const r = await api('/api/leads/draft-batch', { method: 'POST', body: { channel: 'comment', kind: 'person', status: 'new', limit: 10 } });
      out.innerHTML = `✅ drafted ${r.drafted} replies — <button class="text-emerald-600 underline" onclick="renderLeads('new', 'person')">review →</button>`;
    } catch (err) { out.textContent = '❌ ' + err.message; }
    e.target.disabled = false; e.target.textContent = '⚡ Draft replies for top 10';
  });

  document.getElementById('run-discover').addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true; btn.textContent = 'Searching… (can take ~30s)';
    const out = document.getElementById('discover-result');
    out.innerHTML = '<p class="text-slate-500 text-sm">Scanning sources…</p>';
    try {
      const keywords = document.getElementById('kw').value.split('\n').map(s => s.trim()).filter(Boolean);
      const sources = [];
      if (document.getElementById('src-bsky').checked) sources.push('bluesky');
      if (document.getElementById('src-hn').checked) sources.push('hackernews');
      if (document.getElementById('src-reddit').checked) sources.push('reddit');
      const r = await api('/api/leads/discover', { method: 'POST', body: { keywords, sources, min_score: +document.getElementById('min-score').value } });
      out.innerHTML = `<div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm">
        ✅ Found <b>${r.found}</b> matching posts, added <b>${r.added}</b> new leads to your pipeline.
        <button class="text-emerald-700 underline ml-1" onclick="show('leads')">Review them →</button></div>`;
    } catch (err) {
      out.innerHTML = `<div class="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false; btn.textContent = '🔎 Discover leads';
    }
  });
}

// ------------------------------------------------------------ agency clients

const VERTICAL_LABELS = {
  hvac: 'HVAC', plumber: 'Plumbing', roofer: 'Roofing',
  electrician: 'Electrical', landscaping: 'Landscaping', cleaning: 'Cleaning',
};

async function renderAgency() {
  const { agency, google_places_enabled, yelp_enabled, ai_enabled } = await api('/api/settings');
  root.innerHTML = `
    <h2 class="text-2xl font-bold mb-2">Agency Clients</h2>
    <p class="text-slate-500 mb-6 text-sm">Find local home-service businesses that need <b>${esc(agency.agency_name || 'your agency')}</b>'s AI receptionist — scored for missed-call pain (no website, no evening/weekend hours, small review footprint). Then draft the cold email, SMS, or a call prep sheet.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 mb-6">
      <label class="block text-sm font-medium mb-1">Target cities <span class="text-slate-400 font-normal">(one per line — defaults from Settings)</span></label>
      <textarea id="ag-cities" rows="3" class="w-full border rounded-lg px-3 py-2 text-sm">${esc((agency.cities || []).join('\n'))}</textarea>
      <label class="block text-sm font-medium mt-3 mb-1.5">Trades</label>
      <div class="flex flex-wrap gap-3">
        ${Object.entries(VERTICAL_LABELS).map(([k, v]) => `
          <label class="flex items-center gap-2 text-sm"><input type="checkbox" class="ag-vertical rounded" value="${k}" ${(agency.verticals || []).includes(k) ? 'checked' : ''}> ${v}</label>`).join('')}
      </div>
      <div class="flex flex-wrap items-center gap-4 mt-4">
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" id="ag-src-osm" checked class="rounded"> OpenStreetMap <span class="text-slate-400">(free)</span></label>
        <label class="flex items-center gap-2 text-sm ${google_places_enabled ? '' : 'opacity-50'}">
          <input type="checkbox" id="ag-src-google" ${google_places_enabled ? 'checked' : 'disabled'} class="rounded"> Google Places
          ${google_places_enabled ? '' : '<span class="text-slate-400">(set GOOGLE_PLACES_API_KEY)</span>'}</label>
        <label class="flex items-center gap-2 text-sm ${yelp_enabled ? '' : 'opacity-50'}">
          <input type="checkbox" id="ag-src-yelp" ${yelp_enabled ? 'checked' : 'disabled'} class="rounded"> Yelp
          ${yelp_enabled ? '' : '<span class="text-slate-400">(set YELP_API_KEY)</span>'}</label>
        <label class="flex items-center gap-2 text-sm">Min score <input type="number" id="ag-min-score" value="30" min="0" max="100" class="w-16 border rounded px-2 py-1"></label>
        <button id="run-agency" class="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-semibold">🏢 Find businesses</button>
      </div>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 mb-6 flex items-center gap-2 flex-wrap">
      <span class="text-sm font-medium mr-1">Power tools:</span>
      <button id="ag-enrich" class="text-sm border px-3 py-1.5 rounded-lg hover:bg-slate-50">🔬 Enrich all new leads</button>
      <button id="ag-draft-all" class="text-sm border px-3 py-1.5 rounded-lg hover:bg-slate-50" ${ai_enabled ? '' : 'title="Works with templates too"'}>⚡ Draft emails for top 10</button>
      <a href="/callsheet" target="_blank" class="text-sm border px-3 py-1.5 rounded-lg hover:bg-slate-50">🖨 Call sheet</a>
      <span id="ag-tools-result" class="text-xs text-slate-500"></span>
    </div>
    <div id="agency-result"></div>`;

  document.getElementById('ag-enrich').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '🔬 Enriching… (~30s)';
    const out = document.getElementById('ag-tools-result');
    try {
      const r = await api('/api/leads/enrich', { method: 'POST', body: {} });
      out.textContent = `✅ checked ${r.checked}, enriched ${r.enriched}, found ${r.emails_found} emails`;
    } catch (err) { out.textContent = '❌ ' + err.message; }
    e.target.disabled = false; e.target.textContent = '🔬 Enrich all new leads';
  });
  document.getElementById('ag-draft-all').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '⚡ Drafting…';
    const out = document.getElementById('ag-tools-result');
    try {
      const r = await api('/api/leads/draft-batch', { method: 'POST', body: { channel: 'email', limit: 10 } });
      out.innerHTML = `✅ drafted ${r.drafted} emails — <button class="text-emerald-600 underline" onclick="renderLeads('new', 'business')">review →</button>`;
    } catch (err) { out.textContent = '❌ ' + err.message; }
    e.target.disabled = false; e.target.textContent = '⚡ Draft emails for top 10';
  });

  document.getElementById('run-agency').addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true; btn.textContent = 'Searching… (can take ~60s)';
    const out = document.getElementById('agency-result');
    out.innerHTML = '<p class="text-slate-500 text-sm">Geocoding cities and scanning business registries…</p>';
    try {
      const cities = document.getElementById('ag-cities').value.split('\n').map(s => s.trim()).filter(Boolean);
      const verticals = [...document.querySelectorAll('.ag-vertical:checked')].map(c => c.value);
      const sources = [];
      if (document.getElementById('ag-src-osm').checked) sources.push('osm');
      if (document.getElementById('ag-src-google').checked) sources.push('google');
      if (document.getElementById('ag-src-yelp').checked) sources.push('yelp');
      const r = await api('/api/agency/discover', { method: 'POST', body: { cities, verticals, sources, min_score: +document.getElementById('ag-min-score').value } });
      out.innerHTML = `<div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm">
        ✅ Found <b>${r.found}</b> businesses (via ${r.sources_used.join(' + ')}), added <b>${r.added}</b> new prospects.
        <button class="text-emerald-700 underline ml-1" onclick="renderLeads('', 'business')">Review them →</button></div>`;
    } catch (err) {
      out.innerHTML = `<div class="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false; btn.textContent = '🏢 Find businesses';
    }
  });
}

// ------------------------------------------------------------ leads

async function renderLeads(filter = '', kind = '') {
  window._leadFilter = filter; window._leadKind = kind;
  const params = new URLSearchParams();
  if (filter) params.set('status', filter);
  if (kind) params.set('kind', kind);
  const qs = params.toString();
  const leads = await api('/api/leads' + (qs ? `?${qs}` : ''));
  const tabs = ['', ...LEAD_STATUSES].map(s => `
    <button class="px-3 py-1.5 rounded-full text-xs font-medium ${s === filter ? 'bg-slate-900 text-white' : 'bg-white hover:bg-slate-200'}"
      onclick="renderLeads('${s}', '${kind}')">${s || 'all'}</button>`).join('');
  const kindTabs = [['', 'All'], ['person', '👤 Course leads'], ['business', '🏢 Agency clients']].map(([k, label]) => `
    <button class="px-3 py-1.5 rounded-full text-xs font-medium ${k === kind ? 'bg-emerald-600 text-white' : 'bg-white hover:bg-slate-200'}"
      onclick="renderLeads('${filter}', '${k}')">${label}</button>`).join('');

  root.innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-2xl font-bold">Leads <span class="text-slate-400 text-lg">(${leads.length})</span></h2>
      <div class="flex gap-2">
        <a href="/api/leads/export.csv" class="bg-white border px-3 py-1.5 rounded-lg text-sm hover:bg-slate-50">⬇ Export CSV</a>
        <button id="add-lead" class="bg-slate-900 text-white px-3 py-1.5 rounded-lg text-sm">+ Add manually</button>
      </div>
    </div>
    <div class="flex gap-2 mb-2 flex-wrap">${kindTabs}</div>
    <div class="flex gap-2 mb-4 flex-wrap">${tabs}</div>
    <div id="lead-list" class="space-y-3"></div>
    <div id="lead-form" class="hidden"></div>`;

  window.renderLeads = renderLeads;

  const list = document.getElementById('lead-list');
  if (leads.length === 0) {
    list.innerHTML = '<p class="text-sm text-slate-500 bg-white rounded-xl p-5">No leads here yet. Use <b>Find Leads</b> to discover some, or add one manually.</p>';
  } else {
    list.innerHTML = leads.map(leadCard).join('');
    leads.forEach(wireLeadCard);
  }

  document.getElementById('add-lead').addEventListener('click', () => {
    const f = document.getElementById('lead-form');
    f.classList.remove('hidden');
    f.innerHTML = `
      <div class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" id="modal-bg">
        <div class="bg-white rounded-xl p-6 w-full max-w-md shadow-xl" onclick="event.stopPropagation()">
          <h3 class="font-semibold mb-3">Add lead</h3>
          <input id="ml-title" placeholder="Name / post title *" class="w-full border rounded-lg px-3 py-2 text-sm mb-2">
          <input id="ml-url" placeholder="URL (profile, post, website)" class="w-full border rounded-lg px-3 py-2 text-sm mb-2">
          <input id="ml-community" placeholder="Where found (community, event…)" class="w-full border rounded-lg px-3 py-2 text-sm mb-2">
          <textarea id="ml-notes" placeholder="Notes / context" rows="3" class="w-full border rounded-lg px-3 py-2 text-sm mb-3"></textarea>
          <div class="flex justify-end gap-2">
            <button class="px-4 py-2 text-sm rounded-lg border" onclick="document.getElementById('lead-form').classList.add('hidden')">Cancel</button>
            <button class="px-4 py-2 text-sm rounded-lg bg-slate-900 text-white" id="ml-save">Save</button>
          </div>
        </div>
      </div>`;
    document.getElementById('modal-bg').addEventListener('click', () => f.classList.add('hidden'));
    document.getElementById('ml-save').addEventListener('click', async () => {
      const title = document.getElementById('ml-title').value.trim();
      if (!title) return toast('Title is required', true);
      await api('/api/leads', { method: 'POST', body: {
        title, source_url: document.getElementById('ml-url').value.trim() || null,
        community: document.getElementById('ml-community').value.trim(),
        notes: document.getElementById('ml-notes').value.trim(),
        snippet: '',
      }});
      toast('Lead added');
      renderLeads(filter, kind);
    });
  });
}

function leadCard(l) {
  const isBiz = l.kind === 'business';
  let meta = {};
  try { meta = JSON.parse(l.meta || '{}'); } catch {}
  const reasons = meta.score_reasons || [];
  const qual = meta.ai_qualification || null;
  const enr = meta.enrichment || null;
  const bizChips = isBiz ? `
    <div class="flex flex-wrap gap-1.5 mt-1.5">
      ${l.vertical ? `<span class="px-2 py-0.5 rounded-full text-xs bg-indigo-100 text-indigo-800">${esc(VERTICAL_LABELS[l.vertical] || l.vertical)}</span>` : ''}
      ${l.phone ? `<span class="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-700">📞 ${esc(l.phone)}</span>` : ''}
      ${l.email ? `<span class="px-2 py-0.5 rounded-full text-xs bg-sky-100 text-sky-800">✉️ ${esc(l.email)}</span>` : ''}
      ${l.website ? `<a href="${esc(l.website)}" target="_blank" class="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-700 hover:bg-slate-200">🌐 site</a>`
                  : '<span class="px-2 py-0.5 rounded-full text-xs bg-rose-100 text-rose-700">no website</span>'}
      ${meta.rating ? `<span class="px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-800">⭐ ${meta.rating} (${meta.review_count ?? '?'})</span>` : ''}
      ${enr ? `<span class="px-2 py-0.5 rounded-full text-xs ${enr.has_booking ? 'bg-slate-200 text-slate-600' : 'bg-rose-100 text-rose-700'}">${enr.has_booking ? 'has booking' : enr.reachable ? 'no online booking' : 'site unreachable'}</span>` : ''}
      ${qual ? `<span class="px-2 py-0.5 rounded-full text-xs bg-violet-100 text-violet-800" title="${esc(qual.rationale || '')}">🧠 fit ${qual.fit_score}</span>` : ''}
    </div>
    ${reasons.length ? `<p class="text-xs text-slate-500 mt-1.5">🎯 ${reasons.map(esc).join(' · ')}</p>` : ''}
    ${qual && qual.opener_angle ? `<p class="text-xs text-violet-700 mt-1">💡 ${esc(qual.opener_angle)}</p>` : ''}` : '';
  // course leads get the AI fit chip + opener angle too
  const personQual = (!isBiz && qual) ? `
    <div class="flex flex-wrap gap-1.5 mt-1.5">
      <span class="px-2 py-0.5 rounded-full text-xs bg-violet-100 text-violet-800" title="${esc(qual.rationale || '')}">🧠 fit ${qual.fit_score}</span>
    </div>
    ${qual.opener_angle ? `<p class="text-xs text-violet-700 mt-1">💡 ${esc(qual.opener_angle)}</p>` : ''}` : '';
  const nextChip = l.next_action_at
    ? `<p class="text-xs text-amber-700 mt-1.5">⏰ ${esc(l.next_action || 'follow up')} — ${esc(l.next_action_at)}</p>` : '';
  const draftBtns = isBiz ? `
      <button class="draft-btn text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded-lg" data-id="${l.id}" data-channel="email">✉️ Email</button>
      <button class="draft-btn text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded-lg" data-id="${l.id}" data-channel="sms">💬 SMS</button>
      <button class="draft-btn text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded-lg" data-id="${l.id}" data-channel="callprep">📞 Call prep</button>
      <button class="draft-btn text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded-lg" data-id="${l.id}" data-channel="sequence">📧 Sequence</button>
      <button class="enrich-btn text-xs border px-2 py-1 rounded-lg hover:bg-slate-50" data-id="${l.id}" title="Probe website: emails, online booking, dead-site check">🔬</button>
      <button class="qualify-btn text-xs border px-2 py-1 rounded-lg hover:bg-slate-50" data-id="${l.id}" title="AI fit score">🧠</button>`
    : `<button class="draft-btn text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1 rounded-lg" data-id="${l.id}">✨ Draft outreach</button>
       <button class="qualify-btn text-xs border px-2 py-1 rounded-lg hover:bg-slate-50" data-id="${l.id}" title="AI fit score">🧠</button>`;
  return `
  <div class="bg-white rounded-xl shadow-sm p-4" id="lead-${l.id}">
    <div class="flex items-start gap-3">
      ${scoreBadge(l.intent_score)}
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          ${l.source_url ? `<a href="${esc(l.source_url)}" target="_blank" class="font-medium text-sm hover:text-emerald-600">${esc(l.title)}</a>`
                         : `<span class="font-medium text-sm">${esc(l.title)}</span>`}
          <span class="px-2 py-0.5 rounded-full text-xs ${STATUS_COLORS[l.status] || ''}">${l.status}</span>
        </div>
        <p class="text-xs text-slate-500 mt-0.5">${esc(l.community)}${l.author ? ' · ' + esc(l.author) : ''} · via ${esc(l.source)}</p>
        ${bizChips}${personQual}
        ${l.snippet ? `<p class="text-xs text-slate-600 mt-1.5 line-clamp-2">${esc(l.snippet)}</p>` : ''}
        ${nextChip}
        ${l.notes ? `<p class="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 mt-1.5">📝 ${esc(l.notes)}</p>` : ''}
      </div>
      <div class="flex flex-col items-end gap-1.5 shrink-0">
        <select class="lead-status border rounded-lg px-2 py-1 text-xs" data-id="${l.id}">
          ${LEAD_STATUSES.map(s => `<option value="${s}" ${s === l.status ? 'selected' : ''}>${s}</option>`).join('')}
        </select>
        <div class="flex gap-1 flex-wrap justify-end">
          ${draftBtns}
          <button class="na-btn text-xs border px-2 py-1 rounded-lg hover:bg-slate-50" data-id="${l.id}" title="Schedule next action">⏰</button>
          <button class="del-btn text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded-lg" data-id="${l.id}">🗑</button>
        </div>
      </div>
    </div>
    <div class="na-row mt-2 hidden items-center gap-2">
      <input class="na-text border rounded-lg px-2 py-1 text-xs flex-1" placeholder="next action (e.g. follow-up email #2)" value="${esc(l.next_action || '')}">
      <input type="date" class="na-date border rounded-lg px-2 py-1 text-xs" value="${esc(l.next_action_at || '')}">
      <button class="na-save text-xs bg-slate-900 text-white px-3 py-1 rounded-lg">Save</button>
    </div>
    <div class="outreach-area mt-3 hidden" data-id="${l.id}"></div>
  </div>`;
}

function wireLeadCard(l) {
  const card = document.getElementById(`lead-${l.id}`);
  card.querySelector('.lead-status').addEventListener('change', async (e) => {
    await api(`/api/leads/${l.id}`, { method: 'PATCH', body: { status: e.target.value } });
    toast(`Marked ${e.target.value}`);
  });
  card.querySelector('.na-btn').addEventListener('click', () => {
    const row = card.querySelector('.na-row');
    row.classList.toggle('hidden');
    row.classList.toggle('flex', !row.classList.contains('hidden'));
  });
  card.querySelector('.na-save').addEventListener('click', async () => {
    await api(`/api/leads/${l.id}`, { method: 'PATCH', body: {
      next_action: card.querySelector('.na-text').value.trim(),
      next_action_at: card.querySelector('.na-date').value,
    }});
    toast('Next action saved ⏰');
  });
  const enrichBtn = card.querySelector('.enrich-btn');
  if (enrichBtn) enrichBtn.addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '…';
    try {
      const r = await api('/api/leads/enrich', { method: 'POST', body: { ids: [l.id] } });
      toast(r.enriched ? `Enriched — ${r.emails_found ? 'email found!' : 'signals updated'}` : 'Nothing to probe');
      renderLeads(window._leadFilter || '', window._leadKind || '');
    } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = '🔬'; }
  });
  const qualifyBtn = card.querySelector('.qualify-btn');
  if (qualifyBtn) qualifyBtn.addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '…';
    try {
      const r = await api(`/api/leads/${l.id}/qualify`, { method: 'POST' });
      toast(`AI fit: ${r.fit_score} — ${r.rationale.slice(0, 80)}`);
      renderLeads(window._leadFilter || '', window._leadKind || '');
    } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = '🧠'; }
  });
  card.querySelector('.del-btn').addEventListener('click', async () => {
    if (!confirm('Delete this lead?')) return;
    await api(`/api/leads/${l.id}`, { method: 'DELETE' });
    card.remove();
  });
  card.querySelectorAll('.draft-btn').forEach(btn => btn.addEventListener('click', async (e) => {
    const area = card.querySelector('.outreach-area');
    area.classList.remove('hidden');
    area.innerHTML = '<p class="text-xs text-slate-500">✨ Drafting personalized outreach…</p>';
    e.target.disabled = true;
    try {
      const channel = e.target.dataset.channel || (l.source === 'manual' ? 'dm' : 'comment');
      const d = await api(`/api/leads/${l.id}/draft`, { method: 'POST', body: { channel } });
      const rows = (channel === 'callprep' || channel === 'sequence') ? 18 : channel === 'sms' ? 3 : 8;
      area.innerHTML = `
        <div class="bg-slate-50 border rounded-lg p-3">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-semibold text-slate-500">Draft ${channel} ${d.generated_by === 'ai' ? '· 🤖 Claude' : '· 📋 template'}</span>
            <button class="text-xs text-emerald-600 hover:underline copy-draft">Copy</button>
          </div>
          <textarea rows="${rows}" class="w-full text-sm border rounded-lg px-3 py-2 draft-text ${channel === 'callprep' ? 'font-mono text-xs' : ''}">${esc(d.content)}</textarea>
          <p class="text-[11px] text-slate-400 mt-1.5">Review, personalize, and send it yourself — authentic beats automated. Sending marks the lead as contacted.</p>
          <button class="mt-1 text-xs bg-slate-900 text-white px-3 py-1.5 rounded-lg mark-contacted">✓ I sent it — mark contacted</button>
        </div>`;
      area.querySelector('.copy-draft').addEventListener('click', () => copyText(area.querySelector('.draft-text').value));
      area.querySelector('.mark-contacted').addEventListener('click', async () => {
        await api(`/api/leads/${l.id}`, { method: 'PATCH', body: { status: 'contacted' } });
        card.querySelector('.lead-status').value = 'contacted';
        toast('Marked contacted 🎉');
      });
    } catch (err) {
      area.innerHTML = `<p class="text-xs text-red-600">${esc(err.message)}</p>`;
    } finally {
      e.target.disabled = false;
    }
  }));
}

// ------------------------------------------------------------ content

async function renderContent() {
  const posts = await api('/api/posts');
  root.innerHTML = `
    <h2 class="text-2xl font-bold mb-2">Content Studio <span class="text-slate-400 text-lg">— grow your audience</span></h2>
    <p class="text-slate-500 mb-6 text-sm">Generate platform-tailored posts from a topic, plan a whole week at once, or get fresh topic ideas. Track them through draft → scheduled → posted.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 mb-4">
      <div class="flex items-center gap-2 mb-1">
        <label class="block text-sm font-medium flex-1">Topic or idea</label>
        <button id="topic-ideas" class="text-xs text-emerald-600 hover:underline">💡 Suggest topics</button>
      </div>
      <input id="topic" placeholder="e.g. 3 realistic ways beginners earn their first $100 with AI" class="w-full border rounded-lg px-3 py-2 text-sm mb-1">
      <div id="topic-chips" class="flex flex-wrap gap-1.5 mb-3"></div>
      <div class="flex flex-wrap items-center gap-4">
        ${Object.entries(PLATFORM_LABELS).map(([k, v]) => `
          <label class="flex items-center gap-2 text-sm"><input type="checkbox" class="platform rounded" value="${k}" ${k === 'x' || k === 'linkedin' ? 'checked' : ''}> ${v}</label>`).join('')}
        <button id="gen" class="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-semibold">✨ Generate posts</button>
      </div>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 mb-6 flex items-center gap-3 flex-wrap">
      <span class="text-sm font-medium">📅 Content calendar:</span>
      <label class="flex items-center gap-2 text-sm">
        <input type="number" id="cal-days" value="7" min="1" max="14" class="w-14 border rounded px-2 py-1"> days, auto-scheduled daily</label>
      <button id="gen-cal" class="text-sm border px-3 py-1.5 rounded-lg hover:bg-slate-50">🗓 Plan my week</button>
      <span id="cal-result" class="text-xs text-slate-500"></span>
    </div>
    <div id="post-list" class="space-y-3">${posts.map(postCard).join('') || '<p class="text-sm text-slate-500 bg-white rounded-xl p-5">No posts yet — generate your first batch above.</p>'}</div>`;

  posts.forEach(wirePostCard);

  document.getElementById('topic-ideas').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '💡 thinking…';
    try {
      const r = await api('/api/content/topics', { method: 'POST' });
      document.getElementById('topic-chips').innerHTML = r.topics.map(t =>
        `<button class="topic-pick text-xs bg-slate-100 hover:bg-emerald-100 px-2 py-1 rounded-full text-left">${esc(t)}</button>`).join('');
      document.querySelectorAll('.topic-pick').forEach(b =>
        b.addEventListener('click', () => { document.getElementById('topic').value = b.textContent; }));
    } catch (err) { toast(err.message, true); }
    e.target.disabled = false; e.target.textContent = '💡 Suggest topics';
  });

  document.getElementById('gen-cal').addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = '🗓 Planning…';
    const out = document.getElementById('cal-result');
    try {
      const days = +document.getElementById('cal-days').value || 7;
      const r = await api('/api/content/calendar', { method: 'POST', body: { days } });
      out.textContent = `✅ ${r.count} posts scheduled over ${days} days`;
      toast(`Planned ${r.count} posts`);
      renderContent();
    } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = '🗓 Plan my week'; }
  });

  document.getElementById('gen').addEventListener('click', async (e) => {
    const topic = document.getElementById('topic').value.trim();
    if (!topic) return toast('Enter a topic first', true);
    const platforms = [...document.querySelectorAll('.platform:checked')].map(c => c.value);
    if (platforms.length === 0) return toast('Pick at least one platform', true);
    e.target.disabled = true; e.target.textContent = '✨ Generating…';
    try {
      await api('/api/content/generate', { method: 'POST', body: { topic, platforms } });
      toast('Posts generated');
      renderContent();
    } catch (err) {
      toast(err.message, true);
      e.target.disabled = false; e.target.textContent = '✨ Generate posts';
    }
  });
}

function postCard(p) {
  const statusColor = { draft: 'bg-slate-200 text-slate-600', scheduled: 'bg-blue-100 text-blue-800', posted: 'bg-emerald-100 text-emerald-800' }[p.status];
  return `
  <div class="bg-white rounded-xl shadow-sm p-4" id="post-${p.id}">
    <div class="flex items-center gap-2 mb-2 flex-wrap">
      <span class="font-semibold text-sm">${PLATFORM_LABELS[p.platform] || esc(p.platform)}</span>
      <span class="px-2 py-0.5 rounded-full text-xs ${statusColor}">${p.status}</span>
      ${p.generated_by === 'ai' ? '<span class="text-xs text-slate-400">🤖 Claude</span>' : '<span class="text-xs text-slate-400">📋 template</span>'}
      <span class="text-xs text-slate-400 ml-auto">${esc(p.topic)}</span>
    </div>
    <textarea rows="5" class="w-full text-sm border rounded-lg px-3 py-2 post-text">${esc(p.content)}${p.hashtags ? '\n\n' + esc(p.hashtags) : ''}</textarea>
    <div class="flex items-center gap-2 mt-2 flex-wrap">
      <button class="copy-post text-xs bg-slate-900 text-white px-3 py-1.5 rounded-lg">Copy</button>
      <button class="save-post text-xs border px-3 py-1.5 rounded-lg hover:bg-slate-50">Save edits</button>
      <input type="datetime-local" class="sched-time text-xs border rounded-lg px-2 py-1.5" value="${p.scheduled_for ? esc(p.scheduled_for).slice(0, 16) : ''}">
      <button class="sched-post text-xs border px-3 py-1.5 rounded-lg hover:bg-slate-50">📅 Schedule</button>
      <button class="mark-posted text-xs border px-3 py-1.5 rounded-lg hover:bg-slate-50">✓ Mark posted</button>
      <button class="del-post text-xs text-red-500 px-2 py-1.5 rounded-lg hover:bg-red-50 ml-auto">🗑</button>
    </div>
  </div>`;
}

function wirePostCard(p) {
  const card = document.getElementById(`post-${p.id}`);
  const text = () => card.querySelector('.post-text').value;
  card.querySelector('.copy-post').addEventListener('click', () => copyText(text()));
  card.querySelector('.save-post').addEventListener('click', async () => {
    await api(`/api/posts/${p.id}`, { method: 'PATCH', body: { content: text() } });
    toast('Saved');
  });
  card.querySelector('.sched-post').addEventListener('click', async () => {
    const t = card.querySelector('.sched-time').value;
    if (!t) return toast('Pick a date/time first', true);
    await api(`/api/posts/${p.id}`, { method: 'PATCH', body: { status: 'scheduled', scheduled_for: t } });
    toast('Scheduled — reminder: post it manually at that time');
    renderContent();
  });
  card.querySelector('.mark-posted').addEventListener('click', async () => {
    await api(`/api/posts/${p.id}`, { method: 'PATCH', body: { status: 'posted' } });
    toast('Nice! Marked posted 🎉');
    renderContent();
  });
  card.querySelector('.del-post').addEventListener('click', async () => {
    await api(`/api/posts/${p.id}`, { method: 'DELETE' });
    card.remove();
  });
}

// ------------------------------------------------------------ settings

async function renderSettings() {
  const settings = await api('/api/settings');
  const { profile, agency, secrets } = settings;
  let llm = settings.llm;
  root.innerHTML = `
    <h2 class="text-2xl font-bold mb-2">Settings</h2>
    <p class="text-slate-500 mb-6 text-sm">This business profile powers lead scoring, outreach drafting, and content generation.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 space-y-4 max-w-2xl">
      ${[['business_name', 'Business name'], ['website', 'Website']].map(([k, label]) => `
        <div><label class="block text-sm font-medium mb-1">${label}</label>
        <input id="pf-${k}" class="w-full border rounded-lg px-3 py-2 text-sm" value="${esc(profile[k] || '')}"></div>`).join('')}
      ${[['description', 'What do you sell?'], ['audience', 'Who is it for?'], ['tone', 'Voice & tone']].map(([k, label]) => `
        <div><label class="block text-sm font-medium mb-1">${label}</label>
        <textarea id="pf-${k}" rows="2" class="w-full border rounded-lg px-3 py-2 text-sm">${esc(profile[k] || '')}</textarea></div>`).join('')}
      <div><label class="block text-sm font-medium mb-1">Lead-finder keywords <span class="text-slate-400 font-normal">(one per line)</span></label>
        <textarea id="pf-keywords" rows="5" class="w-full border rounded-lg px-3 py-2 text-sm">${esc((profile.keywords || []).join('\n'))}</textarea></div>
      <div><label class="block text-sm font-medium mb-1">Subreddits to watch <span class="text-slate-400 font-normal">(one per line, no r/)</span></label>
        <textarea id="pf-subreddits" rows="4" class="w-full border rounded-lg px-3 py-2 text-sm">${esc((profile.subreddits || []).join('\n'))}</textarea></div>
      <button id="save-profile" class="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm font-semibold">Save profile</button>
    </div>

    <h3 class="text-lg font-bold mt-8 mb-2">🏢 Agency profile</h3>
    <p class="text-slate-500 mb-4 text-sm">Powers Agency Clients discovery and cold outreach drafting (email, SMS, call prep).</p>
    <div class="bg-white rounded-xl shadow-sm p-5 space-y-4 max-w-2xl">
      ${[['agency_name', 'Agency name'], ['website', 'Website'], ['founders', 'Founders / who calls'], ['pricing', 'Pricing (as said on a call)']].map(([k, label]) => `
        <div><label class="block text-sm font-medium mb-1">${label}</label>
        <input id="ag-${k}" class="w-full border rounded-lg px-3 py-2 text-sm" value="${esc(agency[k] || '')}"></div>`).join('')}
      ${[['service', 'What you sell (one plain sentence)'], ['tone', 'Voice & tone']].map(([k, label]) => `
        <div><label class="block text-sm font-medium mb-1">${label}</label>
        <textarea id="ag-${k}" rows="2" class="w-full border rounded-lg px-3 py-2 text-sm">${esc(agency[k] || '')}</textarea></div>`).join('')}
      <div><label class="block text-sm font-medium mb-1">Target cities <span class="text-slate-400 font-normal">(one per line, e.g. "Austin, TX")</span></label>
        <textarea id="ag-cities-set" rows="3" class="w-full border rounded-lg px-3 py-2 text-sm">${esc((agency.cities || []).join('\n'))}</textarea></div>
      <div><label class="block text-sm font-medium mb-1.5">Trades to target</label>
        <div class="flex flex-wrap gap-3">
          ${Object.entries(VERTICAL_LABELS).map(([k, v]) => `
            <label class="flex items-center gap-2 text-sm"><input type="checkbox" class="ag-vertical-set rounded" value="${k}" ${(agency.verticals || []).includes(k) ? 'checked' : ''}> ${v}</label>`).join('')}
        </div></div>
      <button id="save-agency" class="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm font-semibold">Save agency profile</button>
    </div>

    <h3 class="text-lg font-bold mt-8 mb-2">🔑 Data Sources</h3>
    <p class="text-slate-500 mb-4 text-sm">Optional API keys that unlock extra lead sources. Everything works without them (OpenStreetMap, Bluesky, and Hacker News need no keys) — these just add coverage. Stored locally; blank leaves a saved key untouched.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 space-y-4 max-w-2xl">
      ${[
        ['GOOGLE_PLACES_API_KEY', 'Google Places API key', 'Best business data (ratings, hours) — console.cloud.google.com'],
        ['YELP_API_KEY', 'Yelp Fusion API key', 'Extra business source — free tier at yelp.com/developers'],
        ['REDDIT_CLIENT_ID', 'Reddit client ID', 'Adds Reddit to course-lead search — create a "script" app at reddit.com/prefs/apps'],
        ['REDDIT_CLIENT_SECRET', 'Reddit client secret', 'The secret from the same Reddit app'],
      ].map(([k, label, hint]) => {
        const st = secrets[k] || {};
        return `<div>
          <label class="block text-sm font-medium mb-1">${label}
            ${st.set ? `<span class="text-emerald-600 text-xs font-normal">✓ set${st.from_env ? ' (from environment)' : ''}</span>` : '<span class="text-slate-400 text-xs font-normal">not set</span>'}</label>
          <input id="sec-${k}" type="password" class="w-full border rounded-lg px-3 py-2 text-sm ${st.from_env ? 'bg-slate-100' : ''}"
            ${st.from_env ? 'disabled placeholder="set via environment variable — takes precedence"' : `placeholder="${st.set ? '••••••••  (saved — leave blank to keep)' : 'paste key'}"`}>
          <p class="text-xs text-slate-400 mt-0.5">${hint}</p>
        </div>`;
      }).join('')}
      <button id="save-secrets" class="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm font-semibold">Save keys</button>
    </div>

    <h3 class="text-lg font-bold mt-8 mb-2">🛸 Autopilot</h3>
    <p class="text-slate-500 mb-4 text-sm">Hands-free growth: automatically re-run business discovery and enrichment on a schedule while the server is up.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 space-y-4 max-w-2xl" id="autopilot-card">
      <p class="text-sm text-slate-500">Loading…</p>
    </div>

    <h3 class="text-lg font-bold mt-8 mb-2">🤖 AI Provider</h3>
    <p class="text-slate-500 mb-4 text-sm">Any LLM works — pick a provider, set a model and key, and hit Test. With nothing configured the app falls back to templates. Ollama runs free on your own machine.</p>
    <div class="bg-white rounded-xl shadow-sm p-5 space-y-4 max-w-2xl">
      <div><label class="block text-sm font-medium mb-1">Provider</label>
        <select id="llm-provider" class="w-full border rounded-lg px-3 py-2 text-sm bg-white">
          ${Object.entries(llm.providers).map(([k, v]) => `
            <option value="${k}" ${k === llm.provider ? 'selected' : ''}>${esc(v.label)}</option>`).join('')}
        </select></div>
      <div><label class="block text-sm font-medium mb-1">Model <span class="text-slate-400 font-normal" id="llm-model-hint"></span></label>
        <input id="llm-model" class="w-full border rounded-lg px-3 py-2 text-sm" value="${esc(llm.model || '')}"></div>
      <div><label class="block text-sm font-medium mb-1">API key</label>
        <input id="llm-key" type="password" class="w-full border rounded-lg px-3 py-2 text-sm"
          placeholder="${llm.api_key_set ? '••••••••  (saved — leave blank to keep)' : 'paste your API key'}"></div>
      <div id="llm-base-row"><label class="block text-sm font-medium mb-1">Base URL <span class="text-slate-400 font-normal">(only for Ollama / custom endpoints)</span></label>
        <input id="llm-base" class="w-full border rounded-lg px-3 py-2 text-sm" value="${esc(llm.base_url || '')}" placeholder=""></div>
      <div class="flex items-center gap-2">
        <button id="save-llm" class="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm font-semibold">Save provider</button>
        <button id="test-llm" class="border px-5 py-2 rounded-lg text-sm font-semibold hover:bg-slate-50">🔌 Test connection</button>
        <span id="llm-test-result" class="text-sm"></span>
      </div>
      <div id="llm-test-detail" class="hidden text-xs bg-slate-50 border rounded-lg p-3 whitespace-pre-wrap"></div>
    </div>`;

  document.getElementById('save-profile').addEventListener('click', async () => {
    const lines = id => document.getElementById(id).value.split('\n').map(s => s.trim()).filter(Boolean);
    await api('/api/settings', { method: 'PUT', body: {
      business_name: document.getElementById('pf-business_name').value,
      website: document.getElementById('pf-website').value,
      description: document.getElementById('pf-description').value,
      audience: document.getElementById('pf-audience').value,
      tone: document.getElementById('pf-tone').value,
      keywords: lines('pf-keywords'),
      subreddits: lines('pf-subreddits'),
    }});
    toast('Profile saved');
  });

  // --- Data sources / secrets card ---
  document.getElementById('save-secrets').addEventListener('click', async () => {
    const body = {};
    for (const k of ['GOOGLE_PLACES_API_KEY', 'YELP_API_KEY', 'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET']) {
      const el = document.getElementById('sec-' + k);
      if (el && !el.disabled) body[k] = el.value.trim();
    }
    await api('/api/settings/secrets', { method: 'PUT', body });
    toast('Source keys saved 🔑');
    renderSettings();
  });

  // --- Autopilot card ---
  (async () => {
    const ap = await api('/api/autopilot');
    const card = document.getElementById('autopilot-card');
    card.innerHTML = `
      <label class="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" id="ap-enabled" class="rounded" ${ap.enabled ? 'checked' : ''}> Enable autopilot</label>
      <div class="flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2 text-sm">Every
          <input type="number" id="ap-interval" value="${ap.interval_hours}" min="1" max="168" class="w-16 border rounded px-2 py-1"> hours</label>
        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" id="ap-enrich" class="rounded" ${ap.enrich ? 'checked' : ''}> Auto-enrich new leads</label>
      </div>
      <p class="text-xs text-slate-400">Sources: OSM always; Google/Yelp join automatically when their API keys are set. ${ap.last_run ? `Last run: ${esc(ap.last_run.slice(0, 16).replace('T', ' '))} UTC — ${esc(ap.last_result || '')}` : 'Never run yet.'}</p>
      <button id="ap-save" class="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm font-semibold">Save autopilot</button>`;
    document.getElementById('ap-save').addEventListener('click', async () => {
      await api('/api/autopilot', { method: 'PUT', body: {
        enabled: document.getElementById('ap-enabled').checked,
        interval_hours: +document.getElementById('ap-interval').value || 24,
        enrich: document.getElementById('ap-enrich').checked,
        sources: ['osm', 'google', 'yelp'],
      }});
      toast('Autopilot saved 🛸');
    });
  })();

  // --- AI provider card ---
  const provSel = document.getElementById('llm-provider');
  const modelInput = document.getElementById('llm-model');
  const baseInput = document.getElementById('llm-base');
  const syncProviderHints = (resetFields) => {
    const spec = llm.providers[provSel.value] || {};
    document.getElementById('llm-model-hint').textContent = spec.default_model ? `(default: ${spec.default_model})` : '';
    modelInput.placeholder = spec.default_model || 'model id';
    baseInput.placeholder = spec.default_base_url || 'https://your-endpoint/v1';
    if (resetFields) { modelInput.value = ''; baseInput.value = ''; }
  };
  syncProviderHints(false);
  provSel.addEventListener('change', () => syncProviderHints(true));

  document.getElementById('save-llm').addEventListener('click', async () => {
    const r = await api('/api/settings/llm', { method: 'PUT', body: {
      provider: provSel.value,
      model: modelInput.value.trim(),
      api_key: document.getElementById('llm-key').value.trim(),
      base_url: baseInput.value.trim(),
    }});
    toast('AI provider saved');
    llm = r.llm;
    document.getElementById('llm-key').value = '';
    document.getElementById('llm-key').placeholder = llm.api_key_set ? '••••••••  (saved — leave blank to keep)' : 'paste your API key';
    refreshAiBadge();
  });

  document.getElementById('test-llm').addEventListener('click', async (e) => {
    const out = document.getElementById('llm-test-result');
    const detail = document.getElementById('llm-test-detail');
    e.target.disabled = true;
    out.textContent = 'Testing…'; out.className = 'text-sm text-slate-500';
    detail.classList.add('hidden');
    try {
      const r = await api('/api/llm/test', { method: 'POST' });
      out.textContent = r.ok ? `✅ ${r.provider} / ${r.model} works` : `❌ failed`;
      out.className = `text-sm ${r.ok ? 'text-emerald-700' : 'text-red-600'}`;
      detail.textContent = r.detail;
      detail.classList.remove('hidden');
    } catch (err) {
      out.textContent = `❌ ${err.message}`; out.className = 'text-sm text-red-600';
    } finally {
      e.target.disabled = false;
    }
  });

  document.getElementById('save-agency').addEventListener('click', async () => {
    await api('/api/settings/agency', { method: 'PUT', body: {
      agency_name: document.getElementById('ag-agency_name').value,
      website: document.getElementById('ag-website').value,
      founders: document.getElementById('ag-founders').value,
      pricing: document.getElementById('ag-pricing').value,
      service: document.getElementById('ag-service').value,
      tone: document.getElementById('ag-tone').value,
      cities: document.getElementById('ag-cities-set').value.split('\n').map(s => s.trim()).filter(Boolean),
      verticals: [...document.querySelectorAll('.ag-vertical-set:checked')].map(c => c.value),
    }});
    toast('Agency profile saved');
  });
}

// ------------------------------------------------------------ boot

window.show = show;            // used by inline onclick handlers
window.renderLeads = renderLeads;

refreshAiBadge();
show('dashboard');
