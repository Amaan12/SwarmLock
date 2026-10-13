// SwarmLock Dashboard Client Script
(function () {
  'use strict';

  let currentLocks = [];
  let sseSource = null;
  let statusPollTimer = null;
  let countdownTimer = null;

  // DOM Elements
  const locksTableBody = document.getElementById('locksTableBody');
  const emptyState = document.getElementById('emptyState');
  const statActiveLocks = document.getElementById('statActiveLocks');
  const statActiveAgents = document.getElementById('statActiveAgents');
  const statExpiringSoon = document.getElementById('statExpiringSoon');
  const statWorkspace = document.getElementById('statWorkspace');
  const statusLabel = document.getElementById('statusLabel');
  const statusDot = document.querySelector('.status-dot');
  const searchInput = document.getElementById('searchInput');
  const btnRefresh = document.getElementById('btnRefresh');
  const btnClearAll = document.getElementById('btnClearAll');
  const lastUpdated = document.getElementById('lastUpdated');
  const toastContainer = document.getElementById('toastContainer');

  // Modal Elements
  const manualLockModal = document.getElementById('manualLockModal');
  const btnManualLock = document.getElementById('btnManualLock');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const btnCancelModal = document.getElementById('btnCancelModal');
  const formManualLock = document.getElementById('formManualLock');

  // Format Helpers
  function formatSeconds(sec) {
    const s = Math.max(0, Math.round(sec));
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const remS = s % 60;
    if (m < 60) return remS > 0 ? `${m}m ${remS}s` : `${m}m`;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}h ${remM}m`;
  }

  function getAgentClass(agentName) {
    const norm = (agentName || '').toLowerCase().trim();
    if (norm.includes('claude')) return 'agent-claude';
    if (norm.includes('cursor')) return 'agent-cursor';
    if (norm.includes('antigravity') || norm.includes('gemini')) return 'agent-antigravity';
    if (norm.includes('codex') || norm.includes('gpt') || norm.includes('openai')) return 'agent-codex';
    if (norm.includes('human') || norm.includes('dev') || norm.includes('user')) return 'agent-human';
    return 'agent-default';
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  // Render Table
  function renderTable() {
    const filterText = (searchInput.value || '').toLowerCase().trim();
    const now = Date.now() / 1000;

    const filtered = currentLocks.filter(lock => {
      if (!filterText) return true;
      return (
        (lock.path || '').toLowerCase().includes(filterText) ||
        (lock.agent || '').toLowerCase().includes(filterText) ||
        (lock.reason || '').toLowerCase().includes(filterText)
      );
    });

    // Update Stats
    statActiveLocks.textContent = currentLocks.length;
    const uniqueAgents = new Set(currentLocks.map(l => (l.agent || '').toLowerCase()));
    statActiveAgents.textContent = uniqueAgents.size;

    let expiringSoonCount = 0;
    currentLocks.forEach(l => {
      const left = Math.max(0, l.expires_at - now);
      if (left > 0 && left < 300) expiringSoonCount++;
    });
    statExpiringSoon.textContent = expiringSoonCount;

    if (filtered.length === 0) {
      locksTableBody.innerHTML = '';
      emptyState.style.display = currentLocks.length === 0 ? 'flex' : 'none';
      if (currentLocks.length > 0 && filtered.length === 0) {
        locksTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">No locks match search filter "${filterText}"</td></tr>`;
      }
      return;
    }

    emptyState.style.display = 'none';

    // Build rows
    const rowsHtml = filtered.map(lock => {
      const elapsed = Math.max(0, now - lock.acquired_at);
      const left = Math.max(0, lock.expires_at - now);
      const totalTtl = lock.ttl_seconds || 1800;
      const pctRemaining = Math.max(0, Math.min(100, (left / totalTtl) * 100));

      let ttlColorClass = 'safe';
      if (pctRemaining < 15) ttlColorClass = 'danger';
      else if (pctRemaining < 35) ttlColorClass = 'warning';

      const agentClass = getAgentClass(lock.agent);
      const isDir = Boolean(lock.is_dir);

      const pathIcon = isDir
        ? `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`
        : `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>`;

      const reasonHtml = lock.reason
        ? `<span class="reason-text">${escapeHtml(lock.reason)}</span>`
        : `<span class="reason-empty">No reason specified</span>`;

      return `
        <tr data-norm-path="${escapeHtml(lock.norm_path)}">
          <td>
            <div class="path-cell">
              <span class="path-icon">${pathIcon}</span>
              <span class="path-text" title="${escapeHtml(lock.path)}">${escapeHtml(lock.path || '(Project Root)')}</span>
            </div>
          </td>
          <td>
            <span class="agent-badge ${agentClass}">
              ${escapeHtml(lock.agent)}
            </span>
          </td>
          <td>${reasonHtml}</td>
          <td>
            <div class="ttl-container">
              <div class="ttl-text">
                <span>${formatSeconds(elapsed)} ago</span>
                <span style="font-weight: 600;">${formatSeconds(left)} left</span>
              </div>
              <div class="ttl-bar-bg">
                <div class="ttl-bar-fill ${ttlColorClass}" style="width: ${pctRemaining}%;"></div>
              </div>
            </div>
          </td>
          <td style="text-align: right;">
            <button class="btn-unlock" onclick="window.forceUnlock('${escapeJs(lock.path)}')">
              Force Unlock
            </button>
          </td>
        </tr>
      `;
    }).join('');

    locksTableBody.innerHTML = rowsHtml;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[m]));
  }

  function escapeJs(str) {
    if (!str) return '';
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  }

  // Network Fetch API
  async function fetchLocks() {
    try {
      const res = await fetch('/api/locks');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      currentLocks = data.locks || [];
      renderTable();
      markOnline();
      lastUpdated.textContent = 'Updated just now';
    } catch (err) {
      markOffline();
    }
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        if (data.workspace) {
          const parts = data.workspace.split(/[\\/]/);
          statWorkspace.textContent = parts[parts.length - 1] || data.workspace;
          statWorkspace.title = data.workspace;
        }
      }
    } catch (_) {}
  }

  function markOnline() {
    statusDot.className = 'status-dot online';
    statusLabel.textContent = 'ONLINE :7890';
  }

  function markOffline() {
    statusDot.className = 'status-dot offline';
    statusLabel.textContent = 'CONNECTING...';
  }

  // Setup SSE
  function setupSSE() {
    if (sseSource) {
      sseSource.close();
    }

    sseSource = new EventSource('/api/events');

    sseSource.onopen = () => {
      markOnline();
    };

    sseSource.addEventListener('initial', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
      } catch (_) {}
    });

    sseSource.addEventListener('update', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
      } catch (_) {}
    });

    sseSource.addEventListener('acquire', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
        showToast('Lock acquired', 'info');
      } catch (_) {}
    });

    sseSource.addEventListener('release', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
      } catch (_) {}
    });

    sseSource.addEventListener('force-unlock', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
        showToast('Lock force-released', 'warning');
      } catch (_) {}
    });

    sseSource.addEventListener('sweep', (e) => {
      try {
        const data = JSON.parse(e.data);
        currentLocks = data.locks || [];
        renderTable();
      } catch (_) {}
    });

    sseSource.onerror = () => {
      markOffline();
    };
  }

  // Force Unlock Handler
  window.forceUnlock = async function (path) {
    if (!confirm(`Are you sure you want to force unlock:\n\n${path}`)) {
      return;
    }
    try {
      const res = await fetch('/api/force-unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, operator: 'GUI-User' })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`Unlocked '${path}'`, 'success');
        fetchLocks();
      } else {
        alert(data.message || 'Failed to unlock');
      }
    } catch (err) {
      alert(`Network error: ${err.message}`);
    }
  };

  // Event Listeners
  searchInput.addEventListener('input', renderTable);

  btnRefresh.addEventListener('click', () => {
    fetchLocks();
    showToast('Refreshed state', 'info');
  });

  btnClearAll.addEventListener('click', async () => {
    if (currentLocks.length === 0) return;
    if (!confirm(`Unlock ALL ${currentLocks.length} active locks?`)) return;

    try {
      const res = await fetch('/api/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (data.success) {
        showToast(`Cleared ${data.cleared_count} locks`, 'warning');
        fetchLocks();
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  });

  // Modal handlers
  btnManualLock.addEventListener('click', () => {
    manualLockModal.classList.add('open');
    document.getElementById('lockInputPath').focus();
  });

  function closeModal() {
    manualLockModal.classList.remove('open');
    formManualLock.reset();
  }

  btnCloseModal.addEventListener('click', closeModal);
  btnCancelModal.addEventListener('click', closeModal);
  manualLockModal.addEventListener('click', (e) => {
    if (e.target === manualLockModal) closeModal();
  });

  formManualLock.addEventListener('submit', async (e) => {
    e.preventDefault();
    const path = document.getElementById('lockInputPath').value.trim();
    const agent = document.getElementById('lockInputAgent').value.trim();
    const reason = document.getElementById('lockInputReason').value.trim();
    const ttl = parseInt(document.getElementById('lockInputTtl').value, 10) || 30;

    try {
      const res = await fetch('/api/acquire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, agent, reason, ttl })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`Locked '${path}' successfully`, 'success');
        closeModal();
        fetchLocks();
      } else {
        alert(data.message || 'Failed to acquire lock');
      }
    } catch (err) {
      alert(`Network error: ${err.message}`);
    }
  });

  // Countdown Interval (Updates times locally every 1 second without network requests)
  countdownTimer = setInterval(() => {
    if (currentLocks.length > 0) {
      renderTable();
    }
  }, 1000);

  // Fallback Polling Interval (every 4 seconds)
  statusPollTimer = setInterval(() => {
    fetchLocks();
  }, 4000);

  // Initialize
  fetchStatus();
  fetchLocks();
  setupSSE();
})();
