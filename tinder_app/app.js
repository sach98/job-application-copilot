/*
 * JobHunt Tinder review app: vanilla JS.
 *
 * Behaviour:
 * - Loads today's queue from `${API_BASE}/queue` (n8n webhook).
 * - If API unreachable (file:// open or n8n down), falls back to
 *   `test_fixtures/queue.json` and persists swipes to localStorage.
 * - Renders up to top 3 cards in a stack; swipe / arrow / button to act.
 * - 4 actions: skip / apply / save / edit (each POSTs to /swipe).
 * - Live IST clock.
 * - Side panel for full JD + tailored resume diff + CL preview.
 * - Push notifications: prompts permission once; new role hitting queue
 *   while app open triggers an in-app banner.
 *
 * Caveman style allowed in console.log; UI strings stay polished.
 */

(() => {
  // ----- Config / state -----
  const API_BASE = (location.origin && location.protocol.startsWith('http'))
    ? `${location.origin}/review/webhook/jobhunt/api`
    : null;  // file:// → fixture mode
  const FIXTURE_URL = 'test_fixtures/queue.json';
  const LS_KEY = 'jobhunt.swipes';
  const POLL_MS = 60_000;
  const STAGES = ["applied","screening","interview","offer","rejected","ghosted"];

  let state = {
    today_applied: 0,
    pending_review_count: 0,
    roles: [],
    swipes: loadSwipes(),
    activeIdx: 0,
    sidePanelRoleId: null,
  };

  // Roles dismissed via skip/save/edit are hidden from the stack for this
  // session only. They are NOT removed from the queue: they reappear on the
  // next load. Only an 'apply' permanently removes a role from the queue.
  const dismissedThisSession = new Set();

  // ----- Auth gate -----
  function authOk() {
    return true; // Bypassed for local/Tailscale access control
  }

  // ----- DOM refs -----
  const $ = id => document.getElementById(id);
  const stackEl = $('stack');
  const countLabel = $('countLabel');
  const clockEl = $('clock');
  const pendingBanner = $('pendingBanner');
  const pendingCount = $('pendingCount');
  const sidePanel = $('sidePanel');
  const settingsDrawer = $('settingsDrawer');
  const toast = $('toast');
  const apiBaseLabel = $('apiBaseLabel');
  const modeLabel = $('modeLabel');

  // ----- Storage helpers -----
  function loadSwipes() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
    catch { return {}; }
  }
  function saveSwipes() {
    localStorage.setItem(LS_KEY, JSON.stringify(state.swipes));
  }

  // ----- API -----
  async function fetchQueue() {
    if (!API_BASE) {
      const r = await fetch(FIXTURE_URL);
      return r.json();
    }
    try {
      const r = await fetch(`${API_BASE}/queue`, { credentials: 'include' });
      if (!r.ok) throw new Error(`queue ${r.status}`);
      return r.json();
    } catch (e) {
      console.warn('queue api down, fallback fixture', e);
      const r = await fetch(FIXTURE_URL);
      return r.json();
    }
  }

  async function postSwipe(roleId, action) {
    state.swipes[roleId] = { action, at: new Date().toISOString() };
    saveSwipes();
    if (!API_BASE) return { ok: true, offline: true };
    const role = state.roles.find(r => r.id === roleId) || {};
    try {
      const r = await fetch(`${API_BASE}/swipe`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role_id: roleId,
          action,
          company: role.company || '',
          role: role.role || '',
          jd_url: role.jd_url || roleId,
          team_members: role.team_members || '[]'
        }),
      });
      if (!r.ok) throw new Error(`swipe ${r.status}`);
      return r.json();
    } catch (e) {
      console.warn('swipe post failed, kept in localStorage', e);
      return { ok: false, error: String(e), offline: true };
    }
  }

  // ----- Rendering -----
  function refreshTopBar() {
    countLabel.innerHTML = `<strong>${state.today_applied}</strong> applied`;
    if (state.pending_review_count > 0) {
      pendingBanner.classList.add('show');
      pendingCount.textContent = state.pending_review_count;
    } else {
      pendingBanner.classList.remove('show');
    }
  }

  function tickClock() {
    const now = new Date();
    const ist = new Date(now.getTime() + (now.getTimezoneOffset() + 330) * 60_000);
    const hh = String(ist.getHours()).padStart(2, '0');
    const mm = String(ist.getMinutes()).padStart(2, '0');
    clockEl.textContent = `${hh}:${mm} IST`;
  }

  function relTime(iso) {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diffMin = Math.round((now - then) / 60_000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin} min ago`;
    if (diffMin < 1440) return `${Math.round(diffMin / 60)} h ago`;
    return `${Math.round(diffMin / 1440)} d ago`;
  }

  function fitClass(score) {
    if (score >= 0.75) return 'fit-green';
    if (score >= 0.5) return 'fit-amber';
    return 'fit-grey';
  }

  function renderCard(role, depth) {
    const card = document.createElement('article');
    card.className = 'card';
    card.dataset.depth = depth;
    card.dataset.roleId = role.id;

    const isFresh = role.posted_at && (Date.now() - new Date(role.posted_at).getTime() < 90 * 60_000);

    const logo = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(role.company_domain || '')}&sz=64`;
    const fitC = fitClass(role.fit_score || 0);
    const fitPct = Math.round((role.fit_score || 0) * 100);

    card.innerHTML = `
      <div class="head">
        <img class="logo" src="${logo}" alt="" onerror="this.style.visibility='hidden'"/>
        <div class="title">
          <div class="company">${escape(role.company)}</div>
          <div class="role">${escape(role.role)}</div>
        </div>
      </div>
      <div class="meta-row">
        <span class="chip salary">${escape(role.salary || '-')}</span>
        <span class="chip ${fitC}">fit ${fitPct}%</span>
        <span class="chip source">${escape(role.source || '')}</span>
        ${role.tier_a ? '<span class="chip tier-a">tier A</span>' : ''}
        ${role.referral_available ? '<span class="chip referral">referral</span>' : ''}
        <span class="chip ${isFresh ? 'posted-fresh' : ''}">${escape(role.location || '')} · ${relTime(role.posted_at)}</span>
      </div>
      <div class="summary">
        <h4>Why this role</h4>
        <ul>${(role.fit_summary_3_bullets || []).map(b => `<li>${escape(b)}</li>`).join('')}</ul>
      </div>
      <div class="hm-row">
        ${role.hiring_mgr && role.hiring_mgr.name
          ? `<div class="hm-text"><strong>${escape(role.hiring_mgr.name)}</strong> · ${escape(role.hiring_mgr.title || '')}</div>
             ${role.hiring_mgr.linkedin_url ? `<a href="${escape(normalizeLinkedinUrl(role.hiring_mgr.linkedin_url))}" target="_blank" rel="noopener">LinkedIn ↗</a>` : ''}`
          : `<div class="hm-text"><span style="opacity:0.6">No named contact, next best:</span></div>
             <div class="hm-links">
               ${role.referral_search_url ? `<a href="${escape(role.referral_search_url)}" target="_blank" rel="noopener">Referrals ↗</a>` : ''}
               ${role.hiring_search_url ? `<a href="${escape(role.hiring_search_url)}" target="_blank" rel="noopener">Hiring mgr ↗</a>` : ''}
             </div>`}
      </div>
      <div class="actions-inline">
        <button class="details-btn" data-action="details">Details</button>
      </div>
    `;

    if (depth === 0) {
      enableSwipe(card);
      card.querySelector('[data-action="details"]').addEventListener('click', e => {
        e.stopPropagation();
        openSidePanel(role);
      });
    }
    return card;
  }

  function renderEmpty() {
    const card = document.createElement('article');
    card.className = 'card';
    card.dataset.depth = 0;
    card.innerHTML = `
      <div class="empty-state">
        <h3>Queue clear ✓</h3>
        <div>${state.today_applied} applications submitted today.</div>
        <div style="font-size:13px; color:var(--text-mute); margin-top:8px;">No roles in the queue right now. New roles appear here after the next scrape + scoring run.</div>
      </div>
    `;
    return card;
  }

  function renderStack() {
    stackEl.innerHTML = '';
    const queued = state.roles.filter(
      r => state.swipes[r.id]?.action !== 'apply' && !dismissedThisSession.has(r.id)
    );
    if (queued.length === 0) {
      stackEl.appendChild(renderEmpty());
      return;
    }
    // Render top 3 cards, deepest first so DOM order matches z-index expectations.
    const visible = queued.slice(0, 3);
    for (let i = visible.length - 1; i >= 0; i--) {
      stackEl.appendChild(renderCard(visible[i], i));
    }
  }

  function normalizeLinkedinUrl(url) {
    if (!url || url === '#') return '#';
    url = String(url).trim();
    if (url.startsWith('/')) return 'https://www.linkedin.com' + url;
    // Only allow http(s): blocks javascript:/data: URLs from scraped data.
    return /^https?:\/\//i.test(url) ? url : '#';
  }

  function escape(s) {
    return String(s ?? '').replace(/[<>&"']/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // ----- Swipe input -----
  // Window-level move/end listeners are bound once in wire(). Each card only
  // registers its own start handler, so re-rendering the stack does not
  // accumulate window listeners.
  const SWIPE_THRESHOLD = 110;
  let swipeCtx = null;

  function enableSwipe(card) {
    card.addEventListener('mousedown', e => startSwipe(card, e));
    card.addEventListener('touchstart', e => startSwipe(card, e), { passive: true });
  }
  function startSwipe(card, e) {
    const p = e.touches ? e.touches[0] : e;
    swipeCtx = { card, startX: p.clientX, startY: p.clientY, dx: 0, dy: 0 };
    card.style.transition = 'none';
  }
  function moveSwipe(e) {
    if (!swipeCtx) return;
    const p = e.touches ? e.touches[0] : e;
    swipeCtx.dx = p.clientX - swipeCtx.startX;
    swipeCtx.dy = p.clientY - swipeCtx.startY;
    swipeCtx.card.style.transform =
      `translate(${swipeCtx.dx}px, ${swipeCtx.dy}px) rotate(${swipeCtx.dx / 18}deg)`;
  }
  function endSwipe() {
    if (!swipeCtx) return;
    const { card, dx, dy } = swipeCtx;
    swipeCtx = null;
    card.style.transition = '';
    const absX = Math.abs(dx), absY = Math.abs(dy);
    if (absX > SWIPE_THRESHOLD && absX > absY) {
      if (dx > 0) {
        // Right = apply → open the co-pilot flow. Snap card back; advance only
        // when the user resolves the modal.
        card.style.transform = '';
        openApplyFlow(currentTopRole());
      } else {
        doAction('skip');
      }
    } else if (absY > SWIPE_THRESHOLD) {
      doAction(dy < 0 ? 'save' : 'edit');
    } else {
      card.style.transform = '';
    }
  }

  // ----- Actions -----
  async function doAction(action) {
    const topCard = stackEl.querySelector('.card[data-depth="0"]');
    if (!topCard) return;
    const roleId = topCard.dataset.roleId;
    if (!roleId) return;
    const role = state.roles.find(r => r.id === roleId);
    if (!role) return;

    // Hide the card for this session. Persistent removal (across reloads) only
    // happens for 'apply', via the state.swipes[id].action === 'apply' check.
    dismissedThisSession.add(roleId);

    const flyClass = { skip: 'flying-left', apply: 'flying-right', save: 'flying-up', edit: 'flying-down' }[action];
    topCard.classList.add(flyClass);

    if (action === 'apply') {
      state.today_applied = state.today_applied + 1;
      showToast(`Applying to ${role.company} · ${role.role}…`);
    } else if (action === 'skip') showToast(`Skipped ${role.company}`);
    else if (action === 'save') showToast(`Saved for tomorrow`);
    else if (action === 'edit') {
      showToast(`Opening drafts to edit…`);
      // In production: open Google Docs URLs returned by API. Stub for now.
    }

    await postSwipe(roleId, action);

    setTimeout(() => {
      renderStack();
      refreshTopBar();
    }, 280);
  }

  // ----- Side panel -----
  function personRow(p, badge, company, roleTitle) {
    const url = p.linkedin_url ? normalizeLinkedinUrl(p.linkedin_url) : '';
    const link = url ? ` · <a href="${escape(url)}" target="_blank" rel="noopener">LinkedIn ↗</a>` : '';
    const tag = badge ? ` <span class="chip referral">${escape(badge)}</span>` : '';
    const reachBtn = url ? ` · <button class="reach-btn" data-url="${escape(url)}" data-name="${escape(p.name || '')}" data-company="${escape(company || '')}" data-role="${escape(roleTitle || '')}">Reach out</button>` : '';
    const sub = [p.title, p.location].filter(Boolean).map(escape).join(' · ');
    return `<div class="contact-row"><strong>${escape(p.name || '-')}</strong>${tag}${link}${reachBtn}${sub ? `<br/><span style="opacity:0.7">${sub}</span>` : ''}</div>`;
  }
  function renderContacts(role) {
    let team = [];
    try { team = JSON.parse(role.team_members || '[]'); } catch (e) { team = []; }
    const referrals = role.referrals || [];
    const parts = [];
    const company = role.company || '';
    const roleTitle = role.role || '';
    if (referrals.length) {
      parts.push('<div class="contact-group"><h4>Best referral path</h4>'
        + referrals.map(r => personRow(r, r.mutual_with_candidate, company, roleTitle)).join('') + '</div>');
    }
    if (team.length) {
      parts.push('<div class="contact-group"><h4>Same team</h4>'
        + team.map(t => personRow(t, '', company, roleTitle)).join('') + '</div>');
    }
    return parts.length ? parts.join('') : '<span style="color:var(--text-dim)">No team or referral contacts found yet.</span>';
  }
  function openSidePanel(role) {
    state.sidePanelRoleId = role.id;
    $('spRole').textContent = role.role;
    $('spCompany').textContent = `${role.company} · ${role.location || ''}`;
    $('spJd').textContent = role.jd_excerpt || 'Job description not yet fetched.';
    $('spResume').textContent = role.tailored_resume_diff_preview || 'Tailored resume not yet generated.';
    $('spCl').textContent = role.cl_preview || 'Cover letter not yet generated.';
    const hm = role.hiring_mgr || {};
    $('spHm').innerHTML = hm.name
      ? `<strong>${escape(hm.name)}</strong> · ${escape(hm.title || '')}<br/><a href="${escape(normalizeLinkedinUrl(hm.linkedin_url))}" target="_blank" rel="noopener">View LinkedIn ↗</a>`
      : '<span style="color:var(--text-dim)">No hiring manager identified yet.</span>';
    $('spContacts').innerHTML = renderContacts(role);
    wireReachButtons($('spContacts'));

    sidePanel.classList.add('open');
    sidePanel.setAttribute('aria-hidden', 'false');
  }
  function closeSidePanel() {
    sidePanel.classList.remove('open');
    sidePanel.setAttribute('aria-hidden', 'true');
  }

  // ----- Reach-out wiring (shared by side panel + apply modal) -----
  function wireReachButtons(container) {
    container.querySelectorAll('.reach-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        const url = btn.dataset.url;
        const firstName = (btn.dataset.name || '').trim().split(/\s+/)[0] || '';
        const draft = `Hi ${firstName}, I'm applying for the ${btn.dataset.role} role at ${btn.dataset.company} and noticed you're connected to the team. Would you be open to a quick chat or a referral? Thanks!`;
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(draft)
              .then(() => showToast('Draft copied, paste into LinkedIn'))
              .catch(err => console.error('Clipboard copy rejected:', err));
          }
        } catch (err) { console.error('Clipboard write error:', err); }
        if (url && url !== '#') window.open(url, '_blank', 'noopener');
      });
    });
  }

  // ----- Co-pilot apply flow -----
  // Right-swipe / Apply opens this modal instead of firing an apply immediately.
  // Nothing is auto-submitted: the modal only opens links + copies text. The job
  // is recorded + advanced only when the user picks a footer action.
  function currentTopRole() {
    const topCard = stackEl.querySelector('.card[data-depth="0"]');
    if (!topCard) return null;
    return state.roles.find(r => r.id === topCard.dataset.roleId) || null;
  }
  function renderCrib(crib) {
    const fields = (crib && crib.fields) || [];
    if (!fields.length) return '<span style="color:var(--text-dim)">No crib fields.</span>';
    return fields.map(f => {
      const warn = f.needs_confirm ? ' crib-warn' : '';
      const mark = f.needs_confirm ? '⚠ ' : '';
      return `<div class="crib-row${warn}">
        <div class="crib-head"><span class="crib-q">${mark}${escape(f.q)}</span>
        <button class="reach-btn crib-copy" data-copy="${escape(f.a)}">Copy</button></div>
        <div class="crib-a">${escape(f.a)}</div></div>`;
    }).join('');
  }
  function wireCopyButtons(container) {
    container.querySelectorAll('.crib-copy').forEach(btn => {
      btn.addEventListener('click', () => {
        const text = btn.dataset.copy || '';
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text)
              .then(() => showToast('Copied'))
              .catch(err => console.error('copy rejected', err));
          }
        } catch (err) { console.error('copy error', err); }
      });
    });
  }
  function setOpenLink(btnId, url) {
    const btn = $(btnId);
    if (!btn) return;
    if (url) {
      btn.style.display = '';
      btn.onclick = () => window.open(url, '_blank', 'noopener');
    } else {
      btn.style.display = 'none';
    }
  }
  function openApplyFlow(role) {
    if (!role) return;
    $('apCompany').textContent = role.company || '';
    $('apRole').textContent = role.role || '';
    setOpenLink('apOpenApp', role.apply_url || '');
    setOpenLink('apResume', (API_BASE && role.resume_pdf_url) ? `${API_BASE}/${role.resume_pdf_url}` : '');
    setOpenLink('apCl', (API_BASE && role.cover_letter_pdf_url) ? `${API_BASE}/${role.cover_letter_pdf_url}` : '');
    // Deep-link referral search: opens in the user's own LinkedIn session (no automation, no ban).
    setOpenLink('apRefSearch', role.referral_search_url || '');
    setOpenLink('apHmSearch', role.hiring_search_url || '');

    const contactsEl = $('apContacts');
    contactsEl.innerHTML = renderContacts(role);
    wireReachButtons(contactsEl);

    const cribEl = $('apCrib');
    if (API_BASE && role.crib_url) {
      cribEl.innerHTML = '<span style="color:var(--text-dim)">Loading crib…</span>';
      fetch(`${API_BASE}/${role.crib_url}`, { credentials: 'include' })
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(c => { cribEl.innerHTML = renderCrib(c); wireCopyButtons(cribEl); })
        .catch(() => { cribEl.innerHTML = '<span style="color:var(--text-dim)">Crib sheet available when served live.</span>'; });
    } else {
      cribEl.innerHTML = '<span style="color:var(--text-dim)">Crib sheet available when served live.</span>';
    }

    const modal = $('applyModal');
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }
  function closeApplyModal() {
    const modal = $('applyModal');
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }
  function applyModalOpen() {
    return $('applyModal').classList.contains('open');
  }

  // ----- Toast -----
  let toastTimer = null;
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  // ----- Push notifications -----
  function askPushPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
      Notification.requestPermission().then(p => {
        if (p === 'granted') showToast('Push notifications enabled');
      });
    }
  }
  function pushNew(role) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    new Notification(`New role · ${role.company}`, {
      body: `${role.role} · fit ${Math.round(role.fit_score * 100)}%`,
      tag: role.id,
    });
  }

  // ----- Tracker drawer -----
  async function openTracker() {
    const drawer = $('trackerDrawer');
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');

    if (!API_BASE) {
      $('trackerStats').innerHTML = '';
      $('trackerList').innerHTML = '<div style="text-align:center;color:var(--text-mute);margin-top:20px;">Tracker available when served live.</div>';
      return;
    }

    try {
      const r = await fetch(`${API_BASE}/outcomes`, { credentials: 'include' });
      if (!r.ok) throw new Error(`outcomes status ${r.status}`);
      const outcomes = await r.json();
      renderTracker(outcomes);
    } catch (e) {
      console.warn('outcomes fetch failed', e);
      $('trackerStats').innerHTML = '';
      $('trackerList').innerHTML = '<div style="text-align:center;color:var(--text-mute);margin-top:20px;">Failed to load outcomes.</div>';
    }
  }

  function closeTracker() {
    const drawer = $('trackerDrawer');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }

  function renderTracker(outcomes) {
    const outcomeList = Object.values(outcomes || {});
    outcomeList.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));

    const totalApplied = outcomeList.length;
    const interviewOrBeyond = outcomeList.filter(o => o.stage === 'interview' || o.stage === 'offer').length;
    const totalOffers = outcomeList.filter(o => o.stage === 'offer').length;
    const hitRate = totalApplied > 0 ? Math.round((interviewOrBeyond / totalApplied) * 100) : 0;

    $('trackerStats').innerHTML = `
      <div class="stat-chip">
        <div class="val">${totalApplied}</div>
        <div class="lbl">Applied</div>
      </div>
      <div class="stat-chip">
        <div class="val">${interviewOrBeyond}</div>
        <div class="lbl">Interviews</div>
      </div>
      <div class="stat-chip">
        <div class="val">${totalOffers}</div>
        <div class="lbl">Offers</div>
      </div>
      <div class="stat-chip">
        <div class="val">${hitRate}%</div>
        <div class="lbl">Hit Rate</div>
      </div>
    `;

    let listHtml = '';
    for (const outcome of outcomeList) {
      let selectHtml = `<select class="tracker-select" data-role-id="${outcome.role_id}">`;
      for (const st of STAGES) {
        const selected = outcome.stage === st ? 'selected' : '';
        selectHtml += `<option value="${st}" ${selected}>${st}</option>`;
      }
      selectHtml += `</select>`;
      
      listHtml += `
        <div class="tracker-row">
          <div class="tracker-info">
            <span class="tracker-company">${escape(outcome.company || '')}</span>
            <span class="tracker-role">${escape(outcome.role || '')}</span>
          </div>
          ${selectHtml}
        </div>
      `;
    }
    $('trackerList').innerHTML = listHtml || '<div style="text-align:center;color:var(--text-mute);margin-top:20px;">No applications tracked yet.</div>';

    // Attach listeners
    const selects = $('trackerList').querySelectorAll('.tracker-select');
    selects.forEach(select => {
      select.addEventListener('change', async (e) => {
        const roleId = select.dataset.roleId;
        const newStage = e.target.value;
        try {
          const res = await fetch(`${API_BASE}/outcome`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_id: roleId, stage: newStage })
          });
          if (!res.ok) throw new Error(`status ${res.status}`);
          const resData = await res.json();
          if (resData.ok) {
            showToast(`Updated to ${newStage}`);
            openTracker();
          } else {
            showToast(`Error: ${resData.error || 'unknown'}`);
          }
        } catch (err) {
          console.error('Failed to update outcome:', err);
          showToast('Failed to update stage');
        }
      });
    });
  }

  // ----- Settings drawer -----
  function toggleSettings() {
    settingsDrawer.classList.toggle('open');
  }
  function applyThemeChoice(forceLight) {
    document.documentElement.classList.toggle('theme-system', !forceLight);
    document.documentElement.style.colorScheme = forceLight ? 'light' : 'dark';
  }

  // ----- Polling for new roles -----
  let lastIds = new Set();
  async function poll() {
    try {
      const data = await fetchQueue();
      const incoming = data.roles || [];
      // detect newcomers (id not in lastIds)
      for (const r of incoming) {
        if (!lastIds.has(r.id) && !state.swipes[r.id]) pushNew(r);
      }
      lastIds = new Set(incoming.map(r => r.id));
      state.today_applied = data.today_applied ?? state.today_applied;
      state.pending_review_count = data.pending_review_count ?? 0;
      state.roles = incoming;
      renderStack();
      refreshTopBar();
    } catch (e) {
      console.warn('poll failed', e);
    }
  }

  // ----- Wire events -----
  function wire() {
    $('btnSkip').addEventListener('click', () => doAction('skip'));
    $('btnApply').addEventListener('click', () => openApplyFlow(currentTopRole()));
    $('btnSave').addEventListener('click', () => doAction('save'));
    $('btnEdit').addEventListener('click', () => doAction('edit'));
    $('sideClose').addEventListener('click', closeSidePanel);
    $('trackerBtn').addEventListener('click', openTracker);
    $('trackerClose').addEventListener('click', closeTracker);

    // Apply-flow modal: footer resolutions advance to the next job; close leaves card.
    $('apClose').addEventListener('click', closeApplyModal);
    $('applyModal').addEventListener('click', e => { if (e.target === $('applyModal')) closeApplyModal(); });
    $('apApplied').addEventListener('click', () => { closeApplyModal(); doAction('apply'); });
    $('apCouldnt').addEventListener('click', () => { closeApplyModal(); doAction('save'); });
    $('apSkip').addEventListener('click', () => { closeApplyModal(); doAction('skip'); });
    $('cogBtn').addEventListener('click', toggleSettings);
    $('pushToggle').addEventListener('change', e => {
      if (e.target.checked) askPushPermission();
    });
    $('themeToggle').addEventListener('change', e => applyThemeChoice(e.target.checked));
    pendingBanner.addEventListener('click', () => {
      // The deck IS the pending-review list: scroll it into view and nudge the top card.
      stackEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const topCard = stackEl.querySelector('.card[data-depth="0"]');
      if (topCard) {
        topCard.classList.add('nudge');
        setTimeout(() => topCard.classList.remove('nudge'), 400);
      }
    });
    $('signinBtn')?.addEventListener('click', () => {
      window.location.href = `${API_BASE}/auth/google`;
    });

    // swipe gesture: bound once, not per card
    window.addEventListener('mousemove', moveSwipe);
    window.addEventListener('mouseup', endSwipe);
    window.addEventListener('touchmove', moveSwipe, { passive: true });
    window.addEventListener('touchend', endSwipe);

    // keyboard
    window.addEventListener('keydown', e => {
      if (applyModalOpen()) { if (e.key === 'Escape') closeApplyModal(); return; }
      if ($('trackerDrawer').classList.contains('open') && e.key === 'Escape') { closeTracker(); return; }
      if (sidePanel.classList.contains('open') && e.key === 'Escape') { closeSidePanel(); return; }
      if (e.target && /input|textarea/i.test(e.target.tagName)) return;
      if (e.key === 'ArrowLeft') doAction('skip');
      else if (e.key === 'ArrowRight') openApplyFlow(currentTopRole());
      else if (e.key === 'ArrowUp') { e.preventDefault(); doAction('save'); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); doAction('edit'); }
    });

    // close settings on outside click
    document.addEventListener('click', e => {
      if (!settingsDrawer.contains(e.target) && !$('cogBtn').contains(e.target)) {
        settingsDrawer.classList.remove('open');
      }
    });
  }

  // ----- Boot -----
  async function boot() {
    apiBaseLabel.textContent = API_BASE || '(fixture mode)';
    modeLabel.textContent = API_BASE ? 'live' : 'offline-fixture';

    if (!authOk()) {
      $('authBlocker').hidden = false;
      return;
    } else {
      const blocker = $('authBlocker');
      if (blocker) blocker.style.setProperty('display', 'none', 'important');
    }

    wire();
    tickClock();
    setInterval(tickClock, 30_000);

    await poll();
    setInterval(poll, POLL_MS);
  }

  boot();
})();
