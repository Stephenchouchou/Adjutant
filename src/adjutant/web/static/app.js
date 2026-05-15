/* Adjutant Command Center — Client v2 */

const feed = document.getElementById("briefing-text");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnSend = document.getElementById("btn-send");
const btnCancel = document.getElementById("btn-cancel");
const statusText = document.getElementById("status-text");
const statusDot = document.getElementById("status-dot");
const avatar = document.getElementById("adjutant-portrait");
const avatarStatusText = document.getElementById("avatar-status-text");
const indicator = document.getElementById("terminal-indicator");
const imageBar = document.getElementById("image-bar");
const clockEl = document.getElementById("clock");
const paletteOverlay = document.getElementById("command-palette");
const paletteSearch = document.getElementById("palette-search");
const paletteList = document.getElementById("palette-list");
const paletteHint = document.querySelector(".palette-hint");

// Stats elements
const statInbox = document.getElementById("stat-inbox");
const statTasks = document.getElementById("stat-tasks");

let ws = null;
let streaming = false;
let currentContent = null;
let currentSopCard = null;
let pendingImages = [];
let sopList = [];
let paletteSelectedIdx = 0;

// ── Clock ────────────────────────────────────────────

function updateClock() {
    clockEl.textContent = new Date().toTimeString().slice(0, 8);
}
setInterval(updateClock, 1000);
updateClock();

function timestamp() {
    return new Date().toTimeString().slice(0, 8);
}

// ── Stats HUD ────────────────────────────────────────

const popupInbox = document.getElementById("popup-inbox");
const popupTasks = document.getElementById("popup-tasks");

let currentStats = null;

function updateStats(stats) {
    if (!stats) return;
    currentStats = stats;

    statInbox.textContent = stats.inbox_count;
    statInbox.className = "stat-value" + (stats.inbox_count > 0 ? " warn" : "");

    statTasks.textContent = stats.task_count;
    statTasks.className = "stat-value" + (stats.task_count > 5 ? " warn" : "");

    // Build popup contents — pass source file path so items are clickable
    buildPopupList(popupInbox, "INBOX", stats.inbox_items, stats.inbox_file);
    buildPopupList(popupTasks, "OPEN TASKS", stats.task_items, stats.tasks_file);
}

function buildPopupList(popup, title, items, filePath) {
    if (!items || items.length === 0) {
        popup.innerHTML = `<div class="stat-popup-header">${title}</div><div class="stat-popup-empty">Empty</div>`;
        return;
    }
    let html = `<div class="stat-popup-header">${title} (${items.length})</div>`;
    for (const item of items.slice(0, 15)) {
        html += `<div class="stat-popup-item stat-popup-clickable" data-file="${escapeHtml(filePath || "")}">${escapeHtml(item)}</div>`;
    }
    if (items.length > 15) {
        html += `<div class="stat-popup-empty">+${items.length - 15} more...</div>`;
    }
    popup.innerHTML = html;

    // Make items clickable — open the source file in viewer
    if (filePath) {
        popup.querySelectorAll(".stat-popup-clickable").forEach(el => {
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                closeAllPopups();
                openFileViewer(el.dataset.file);
            });
        });
    }
}

// Stat block click to toggle popup
document.querySelectorAll(".stat-block[data-stat]").forEach(block => {
    block.addEventListener("click", (e) => {
        e.stopPropagation();
        const popup = block.querySelector(".stat-popup");
        if (!popup) return;
        const isOpen = popup.classList.contains("open");
        closeAllPopups();
        if (!isOpen) popup.classList.add("open");
    });
});

function closeAllPopups() {
    document.querySelectorAll(".stat-popup.open").forEach(p => p.classList.remove("open"));
}

// Close popups on click outside
document.addEventListener("click", () => closeAllPopups());

function refreshStats() {
    fetch("/api/stats").then(r => r.json()).then(updateStats).catch(() => {});
}

let indexBuilding = false;

async function buildIndex() {
    if (indexBuilding) return;
    indexBuilding = true;
    addSysMsg("INDEX BUILD STARTED — scanning notebook...");
    try {
        const r = await fetch("/api/index/build", { method: "POST" });
        const data = await r.json();
        if (r.ok) {
            addSysMsg(`INDEX BUILD COMPLETE — ${data.file_count} files, ${data.chunk_count} chunks`);
        } else {
            addErrorMsg(`INDEX BUILD FAILED: ${data.error}`);
        }
    } catch (e) {
        addErrorMsg(`INDEX BUILD ERROR: ${e.message}`);
    } finally {
        indexBuilding = false;
    }
}

// ── WebSocket ────────────────────────────────────────

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("ONLINE", "online");
        const savedSession = localStorage.getItem("adjutant_session_id");
        if (savedSession) {
            ws.send(JSON.stringify({ type: "resume_session", session_id: savedSession }));
        }
    };

    ws.onclose = () => {
        setStatus("OFFLINE", "error");
        setAvatar("idle");
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        setStatus("ERROR", "error");
    };

    ws.onmessage = (event) => {
        handleMessage(JSON.parse(event.data));
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case "init":
            sopList = msg.sops || [];
            updateStats(msg.stats);
            if (msg.session_id) {
                localStorage.setItem("adjutant_session_id", msg.session_id);
            }
            setStatus("READY", "online");
            setAvatar("idle");
            break;

        case "stream_start":
            streaming = true;
            updateButtons();
            setAvatar("responding");
            setIndicator("RECEIVING...");
            currentContent = addMessage("adjutant", "");
            currentContent.classList.add("streaming");
            break;

        case "stream_chunk":
            if (currentContent) {
                currentContent.textContent += msg.data;
                scrollToBottom();
            }
            break;

        case "stream_end":
            streaming = false;
            updateButtons();
            setAvatar("idle");
            setIndicator("");
            finishEntry();
            setStatus("READY", "online");
            refreshStats();
            break;

        case "sop_start":
            streaming = true;
            updateButtons();
            setAvatar("thinking");
            setStatus(`SOP: ${msg.label.toUpperCase()}`, "online");
            setIndicator("PROCESSING...");
            currentSopCard = addSopCard(msg.icon, msg.label);
            currentContent = currentSopCard.querySelector(".msg-body");
            currentContent.classList.add("streaming");
            break;

        case "sop_file_confirm":
            showFileConfirm(msg.path, msg.content, msg.existing || "");
            break;

        case "file_written":
            addSysMsg(`FILE WRITTEN: ${msg.path}`);
            refreshStats();
            break;

        case "error":
            addErrorMsg(msg.data);
            streaming = false;
            updateButtons();
            setAvatar("error");
            setIndicator("");
            setStatus("ERROR", "error");
            setTimeout(() => { setAvatar("idle"); setStatus("READY", "online"); }, 3000);
            break;

        case "cancelled":
            streaming = false;
            updateButtons();
            setAvatar("idle");
            setIndicator("");
            if (currentContent) {
                currentContent.textContent += "\n\n[TRANSMISSION ABORTED]";
            }
            finishEntry();
            setStatus("READY", "online");
            break;

        case "sop_input_request":
            showSopInputModal(msg);
            break;

        case "sop_step":
            addSysMsg(`── 步驟 ${msg.step}/${msg.total}: ${msg.name} ──`);
            break;

        case "session_loaded":
            feed.innerHTML = "";
            localStorage.setItem("adjutant_session_id", msg.id);
            addSysMsg(`SESSION RESUMED: ${msg.id}`);
            for (const m of msg.messages) {
                addMessage(m.role === "user" ? "user" : "adjutant", m.content, null, true);
            }
            addSysMsg("── 繼續對話 ──");
            break;

        case "session_resumed":
            localStorage.setItem("adjutant_session_id", msg.id);
            if (msg.messages && msg.messages.length > 0) {
                feed.innerHTML = "";
                for (const m of msg.messages) {
                    addMessage(m.role === "user" ? "user" : "adjutant", m.content, null, true);
                }
                addSysMsg("── session restored ──");
            }
            setStatus("READY", "online");
            break;

        case "bot_message":
            addBotFeedMessage(msg.role, msg.source, msg.text);
            break;
    }
}

function addBotFeedMessage(role, source, text) {
    clearWelcome();
    const tag = source === "telegram" ? "TG" : "BOT";

    if (role === "system") {
        addSysMsg(`[${tag}] ${text}`);
        refreshStats();
        return;
    }

    const isUser = role === "user";
    const msg_el = document.createElement("div");
    msg_el.className = `msg ${isUser ? "commander" : "adjutant"} bot-origin`;

    const header = document.createElement("div");
    header.className = "msg-header";

    const sender = document.createElement("span");
    sender.className = "msg-sender";
    sender.textContent = isUser ? `COMMANDER [${tag}]` : `ADJUTANT [${tag}]`;

    const time = document.createElement("span");
    time.className = "msg-time";
    time.textContent = `[${timestamp()}]`;

    header.appendChild(sender);
    header.appendChild(time);
    msg_el.appendChild(header);

    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = renderMarkdown(text);
    msg_el.appendChild(body);

    feed.appendChild(msg_el);
    scrollToBottom();
    refreshStats();
}

// ── UI State ─────────────────────────────────────────

function setStatus(text, state) {
    statusText.textContent = text;
    statusText.className = "status-value" + (state ? " " + state : "");
    statusDot.className = "status-dot" + (state ? " " + state : "");
}

function setAvatar(state) {
    avatar.className = "ai-avatar " + state;
    const labels = { idle: "STANDING BY", thinking: "PROCESSING", responding: "RESPONDING", error: "ERROR" };
    avatarStatusText.textContent = labels[state] || "";
}

function setIndicator(text) {
    indicator.textContent = text;
    indicator.className = "terminal-indicator" + (text ? " active" : "");
}

function updateButtons() {
    btnSend.style.display = streaming ? "none" : "";
    btnCancel.style.display = streaming ? "" : "none";
    chatInput.disabled = streaming;
}

// ── Terminal Feed ────────────────────────────────────

function clearWelcome() {
    const w = document.getElementById("welcome-screen");
    if (w) w.remove();
}

function addMessage(role, text, imagePaths, render) {
    clearWelcome();

    const isCmd = role === "user";
    const cls = isCmd ? "commander" : "adjutant";

    const msg = document.createElement("div");
    msg.className = `msg ${cls}`;

    const header = document.createElement("div");
    header.className = "msg-header";

    const sender = document.createElement("span");
    sender.className = "msg-sender";
    sender.textContent = isCmd ? "COMMANDER" : "ADJUTANT";

    const time = document.createElement("span");
    time.className = "msg-time";
    time.textContent = `[${timestamp()}]`;

    header.appendChild(sender);
    header.appendChild(time);
    msg.appendChild(header);

    if (imagePaths && imagePaths.length > 0) {
        const imgDiv = document.createElement("div");
        imgDiv.className = "msg-images";
        for (const p of imagePaths) {
            const tag = document.createElement("span");
            tag.className = "msg-image-tag";
            tag.textContent = p.split("/").pop();
            imgDiv.appendChild(tag);
        }
        msg.appendChild(imgDiv);
    }

    const body = document.createElement("div");
    body.className = "msg-body";
    if (render) {
        body.innerHTML = renderMarkdown(text);
    } else {
        body.textContent = text;
    }

    msg.appendChild(body);
    feed.appendChild(msg);
    scrollToBottom();

    return body;
}

function addSopCard(icon, label) {
    clearWelcome();

    const card = document.createElement("div");
    card.className = "sop-card";

    const header = document.createElement("div");
    header.className = "sop-card-header";
    header.innerHTML = `
        <span class="sop-card-icon">${icon}</span>
        <span class="sop-card-title">${escapeHtml(label.toUpperCase())}</span>
        <span class="sop-card-time">[${timestamp()}]</span>
    `;

    const bodyWrap = document.createElement("div");
    bodyWrap.className = "sop-card-body";

    const body = document.createElement("div");
    body.className = "msg-body";
    bodyWrap.appendChild(body);

    card.appendChild(header);
    card.appendChild(bodyWrap);
    feed.appendChild(card);
    scrollToBottom();

    return card;
}

function addSysMsg(text) {
    clearWelcome();
    const div = document.createElement("div");
    div.className = "sys-msg";
    div.textContent = text;
    feed.appendChild(div);
    scrollToBottom();
}

function addErrorMsg(text) {
    clearWelcome();
    const div = document.createElement("div");
    div.className = "sys-msg error-msg";
    div.textContent = `ERROR: ${text}`;
    feed.appendChild(div);
    scrollToBottom();
}

function showFileConfirm(path, content, existing) {
    const bar = document.createElement("div");
    bar.className = "file-confirm";
    let diffHtml = "";
    if (existing) {
        diffHtml = `<div class="file-diff"><div class="file-diff-label">EXISTING FILE — ${escapeHtml(path)}</div><pre class="file-diff-content">${escapeHtml(existing.substring(0, 500))}${existing.length > 500 ? "\n..." : ""}</pre></div>`;
    } else {
        diffHtml = `<div class="file-diff"><div class="file-diff-label">NEW FILE</div></div>`;
    }
    bar.innerHTML = `
        ${diffHtml}
        <div class="file-confirm-actions">
            <span>Write output to <strong>${escapeHtml(path)}</strong>?</span>
            <button class="action-btn execute mini">WRITE</button>
            <button class="action-btn mini">SKIP</button>
        </div>
    `;
    feed.appendChild(bar);
    scrollToBottom();

    const btns = bar.querySelectorAll(".action-btn");
    btns[0].addEventListener("click", () => {
        ws.send(JSON.stringify({ type: "sop_file_write", path, content }));
        bar.remove();
    });
    btns[1].addEventListener("click", () => {
        addSysMsg("FILE WRITE SKIPPED");
        bar.remove();
    });
}

function scrollToBottom() {
    feed.scrollTop = feed.scrollHeight;
}

function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}

function finishEntry() {
    if (currentContent) {
        currentContent.classList.remove("streaming");
        const raw = currentContent.textContent;
        currentContent.innerHTML = renderMarkdown(raw);
    }
    currentContent = null;
    currentSopCard = null;
}

function renderMarkdown(text) {
    let html = escapeHtml(text);

    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre class="md-code"><code>${code.trim()}</code></pre>`;
    });

    html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

    html = html.replace(/((?:^|\n)\|.+\|(?:\n\|.+\|)+)/g, (block) => {
        const rows = block.trim().split('\n').filter(r => r.trim());
        let table = '<table class="md-table">';
        rows.forEach((row, i) => {
            if (/^\|[\s\-:|]+\|$/.test(row.trim())) return;
            const cells = row.split('|').filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
            const tag = i === 0 ? 'th' : 'td';
            table += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
        });
        table += '</table>';
        return table;
    });

    html = html.replace(/^#### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>');

    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    html = html.replace(/^- \[x\] (.+)$/gm, '<li class="md-li md-check done">$1</li>');
    html = html.replace(/^- \[ \] (.+)$/gm, '<li class="md-li md-check">$1</li>');

    html = html.replace(/^- (.+)$/gm, '<li class="md-li">$1</li>');
    html = html.replace(/((?:<li class="md-li[^"]*">.*<\/li>\n?)+)/g, '<ul class="md-ul">$1</ul>');

    html = html.replace(/^\d+\. (.+)$/gm, '<li class="md-oli">$1</li>');
    html = html.replace(/((?:<li class="md-oli">.*<\/li>\n?)+)/g, '<ol class="md-ol">$1</ol>');

    html = html.replace(/^---$/gm, '<hr class="md-hr">');

    html = html.replace(/\n\n/g, '</p><p class="md-p">');
    html = '<p class="md-p">' + html + '</p>';
    html = html.replace(/<p class="md-p">\s*<\/p>/g, '');

    return html;
}

// ── Command Palette ─────────────────────────────────

function openPalette() {
    paletteOverlay.style.display = "flex";
    paletteSearch.value = "";
    paletteSelectedIdx = 0;
    renderPaletteItems("");
    setTimeout(() => paletteSearch.focus(), 50);
}

function closePalette() {
    paletteOverlay.style.display = "none";
    chatInput.focus();
}

function getPaletteItems(filter) {
    const items = [];

    for (const sop of sopList) {
        let desc = sop.description;
        if (sop.is_v2) {
            const badges = [];
            if (sop.tags && sop.tags.length) badges.push(sop.tags.join(", "));
            if (sop.is_multistep) badges.push("multi-step");
            if (sop.has_inputs) badges.push("inputs");
            if (badges.length) desc += ` [${badges.join(" · ")}]`;
        }
        items.push({
            type: "sop", icon: sop.icon, label: sop.label,
            desc, key: sop.key,
        });
    }

    items.push({ type: "action", icon: "📚", label: "Wiki", desc: "Knowledge base — graph view, pages, browse", action: "wiki" });
    items.push({ type: "action", icon: "🔍", label: "Search Notes", desc: "Semantic search across notebook (RAG)", action: "search" });
    items.push({ type: "action", icon: "🧠", label: "Build Index", desc: "Build/rebuild RAG vector index", action: "build-index" });
    items.push({ type: "action", icon: "📂", label: "Browse Files", desc: "Open notebook file browser", action: "browse" });
    items.push({ type: "action", icon: "🗂️", label: "History", desc: "Browse archived sessions", action: "history" });
    items.push({ type: "action", icon: "👤", label: "Persona", desc: "Edit adjutant personality and mission", action: "persona" });
    items.push({ type: "action", icon: "💾", label: "Memory", desc: "Manage vector and flat-file memory", action: "memory" });
    items.push({ type: "action", icon: "⚡", label: "Directives", desc: "Manage trigger-keyword prompt injection", action: "directives" });
    items.push({ type: "action", icon: "⚙️", label: "Model", desc: "Switch AI tool and model", action: "model" });
    items.push({ type: "action", icon: "🔧", label: "Settings", desc: "Configure paths, Ollama URL, bot settings", action: "settings" });
    items.push({ type: "action", icon: "🤖", label: "Telegram Bot", desc: "Setup and manage Telegram bot", action: "bot-setup" });

    if (!filter) return items;
    const q = filter.toLowerCase();
    return items.filter(i =>
        i.label.toLowerCase().includes(q) ||
        i.desc.toLowerCase().includes(q) ||
        (i.key && i.key.toLowerCase().includes(q))
    );
}

function renderPaletteItems(filter) {
    const items = getPaletteItems(filter);
    paletteSelectedIdx = Math.min(paletteSelectedIdx, Math.max(0, items.length - 1));

    paletteList.innerHTML = "";
    if (items.length === 0) {
        paletteList.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-lo);font-size:0.8em">No matching operations</div>';
        return;
    }

    items.forEach((item, i) => {
        const el = document.createElement("div");
        el.className = "palette-item" + (i === paletteSelectedIdx ? " selected" : "");
        el.innerHTML = `
            <span class="palette-item-icon">${item.icon}</span>
            <div class="palette-item-body">
                <div class="palette-item-label">${escapeHtml(item.label)}</div>
                <div class="palette-item-desc">${escapeHtml(item.desc)}</div>
            </div>
        `;
        el.addEventListener("click", () => executePaletteItem(item));
        el.addEventListener("mouseenter", () => {
            paletteSelectedIdx = i;
            paletteList.querySelectorAll(".palette-item").forEach((p, j) => {
                p.classList.toggle("selected", j === i);
            });
        });
        paletteList.appendChild(el);
    });

    // Scroll selected item into view
    const sel = paletteList.querySelector(".palette-item.selected");
    if (sel) sel.scrollIntoView({ block: "nearest" });
}

function executePaletteItem(item) {
    closePalette();
    if (item.type === "sop") {
        runSop(item.key);
    } else if (item.action === "wiki") {
        openWikiModal();
    } else if (item.action === "search") {
        openSearchModal();
    } else if (item.action === "build-index") {
        buildIndex();
    } else if (item.action === "history") {
        openSessions();
    } else if (item.action === "browse") {
        openFileBrowser();
    } else if (item.action === "persona") {
        openPersonaEditor();
    } else if (item.action === "memory") {
        openMemoryEditor();
    } else if (item.action === "directives") {
        openDirectives();
    } else if (item.action === "settings") {
        openSettings();
    } else if (item.action === "model") {
        openModelSelector();
    } else if (item.action === "bot-setup") {
        botSetupModal.style.display = "flex";
        fetchBotStatus();
    }
}

paletteSearch.addEventListener("input", () => {
    paletteSelectedIdx = 0;
    renderPaletteItems(paletteSearch.value);
});

paletteSearch.addEventListener("keydown", (e) => {
    // Arrow/Enter/Escape handled by global keydown; stop propagation to prevent double-fire
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(e.key)) {
        e.stopPropagation();
        // Let the global handler do the work — but we need to handle here too
        // since stopPropagation prevents global from seeing it
        const items = getPaletteItems(paletteSearch.value);
        if (e.key === "ArrowDown") {
            e.preventDefault();
            paletteSelectedIdx = Math.min(paletteSelectedIdx + 1, items.length - 1);
            renderPaletteItems(paletteSearch.value);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            paletteSelectedIdx = Math.max(paletteSelectedIdx - 1, 0);
            renderPaletteItems(paletteSearch.value);
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (items[paletteSelectedIdx]) executePaletteItem(items[paletteSelectedIdx]);
        } else if (e.key === "Escape") {
            closePalette();
        }
    }
});

paletteOverlay.addEventListener("click", (e) => {
    if (e.target === paletteOverlay) closePalette();
});

if (paletteHint) paletteHint.addEventListener("click", openPalette);

// ── File Browser ─────────────────────────────────────

const fileViewerModal = document.getElementById("modal-file-viewer");
const fileViewerTitle = document.getElementById("file-viewer-title");
const fileViewerBody = document.getElementById("file-viewer-body");
const fileViewerBack = document.getElementById("file-viewer-back");
const fileViewerClose = document.getElementById("file-viewer-close");

let fileBrowserHistory = [];

let fileBrowserCurrentDir = "";

function openFileBrowser(path) {
    const relPath = path || "";
    fileBrowserCurrentDir = relPath;
    fileViewerModal.style.display = "flex";
    fileViewerTitle.textContent = relPath || "NOTEBOOK";
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = fileBrowserHistory.length > 0 ? "" : "none";
    // Show NEW only in browser mode (not viewer/editor)
    const fileNewBtnEl = document.getElementById("file-viewer-new");
    if (fileNewBtnEl) fileNewBtnEl.style.display = "";

    fetch(`/api/files?path=${encodeURIComponent(relPath)}`).then(r => r.json()).then(items => {
        if (items.error) {
            fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">${escapeHtml(items.error)}</div>`;
            return;
        }
        if (items.length === 0) {
            fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Empty directory</div>';
            return;
        }
        fileViewerBody.innerHTML = "";
        for (const item of items) {
            const el = document.createElement("div");
            el.className = "file-item" + (item.type === "dir" ? " dir" : "");
            el.innerHTML = `
                <span class="file-item-icon">${item.type === "dir" ? "📁" : "📄"}</span>
                <span class="file-item-name">${escapeHtml(item.name)}</span>
            `;
            el.addEventListener("click", () => {
                if (item.type === "dir") {
                    fileBrowserHistory.push(relPath);
                    openFileBrowser(item.path);
                } else {
                    openFileViewer(item.path);
                }
            });
            fileViewerBody.appendChild(el);
        }
    }).catch(e => {
        fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${escapeHtml(e.message)}</div>`;
    });
}

// File editor state
const fileEditorTextarea = document.getElementById("file-editor-textarea");
const fileEditBtn = document.getElementById("file-viewer-edit");
const fileSaveBtn = document.getElementById("file-viewer-save");
const fileCancelEditBtn = document.getElementById("file-viewer-cancel-edit");
const fileViewerMsg = document.getElementById("file-viewer-msg");
let currentFilePath = null;
let currentFileContent = null;
let fileEditorMode = false;

function openFileViewer(path) {
    fileViewerModal.style.display = "flex";
    fileViewerTitle.textContent = path.split("/").pop();
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = "";
    currentFilePath = path;
    currentFileContent = null;
    fileEditorMode = false;
    fileEditorTextarea.style.display = "none";
    fileViewerBody.style.display = "";
    fileEditBtn.style.display = "none";
    fileSaveBtn.style.display = "none";
    fileCancelEditBtn.style.display = "none";
    fileViewerMsg.textContent = "";
    const fileNewBtnEl = document.getElementById("file-viewer-new");
    if (fileNewBtnEl) fileNewBtnEl.style.display = "none";

    // Push current browse state so back works
    const prevPath = fileBrowserHistory.length > 0 ? fileBrowserHistory[fileBrowserHistory.length - 1] : "";
    const dirPath = path.includes("/") ? path.substring(0, path.lastIndexOf("/")) : "";
    if (fileBrowserHistory[fileBrowserHistory.length - 1] !== dirPath) {
        fileBrowserHistory.push(dirPath);
    }

    fetch(`/api/files/read?path=${encodeURIComponent(path)}`).then(r => r.json()).then(result => {
        if (result.error) {
            fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">${escapeHtml(result.error)}</div>`;
            return;
        }
        currentFileContent = result.content;
        fileViewerBody.innerHTML = `<div class="file-viewer-content">${renderMarkdown(result.content)}</div>`;
        // Show edit button for .md files
        if (path.endsWith(".md")) {
            fileEditBtn.style.display = "";
        }
    }).catch(e => {
        fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${escapeHtml(e.message)}</div>`;
    });
}

fileEditBtn.addEventListener("click", () => {
    if (!currentFileContent && currentFileContent !== "") return;
    fileEditorMode = true;
    fileViewerBody.style.display = "none";
    fileEditorTextarea.style.display = "";
    fileEditorTextarea.value = currentFileContent;
    fileEditBtn.style.display = "none";
    fileSaveBtn.style.display = "";
    fileCancelEditBtn.style.display = "";
    fileEditorTextarea.focus();
});

fileCancelEditBtn.addEventListener("click", () => {
    fileEditorMode = false;
    fileEditorTextarea.style.display = "none";
    fileViewerBody.style.display = "";
    fileSaveBtn.style.display = "none";
    fileCancelEditBtn.style.display = "none";
    fileEditBtn.style.display = "";
    fileViewerMsg.textContent = "";
});

fileSaveBtn.addEventListener("click", async () => {
    if (!currentFilePath) return;
    fileSaveBtn.disabled = true;
    fileSaveBtn.textContent = "SAVING...";
    fileViewerMsg.textContent = "";
    try {
        const r = await fetch("/api/files/write", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: currentFilePath, content: fileEditorTextarea.value }),
        });
        const data = await r.json();
        if (data.ok) {
            currentFileContent = fileEditorTextarea.value;
            fileViewerBody.innerHTML = `<div class="file-viewer-content">${renderMarkdown(currentFileContent)}</div>`;
            fileEditorMode = false;
            fileEditorTextarea.style.display = "none";
            fileViewerBody.style.display = "";
            fileSaveBtn.style.display = "none";
            fileCancelEditBtn.style.display = "none";
            fileEditBtn.style.display = "";
            fileViewerMsg.textContent = "SAVED";
            fileViewerMsg.className = "editor-msg success";
            setTimeout(() => { fileViewerMsg.textContent = ""; }, 2000);
        } else {
            fileViewerMsg.textContent = data.error || "Save failed";
            fileViewerMsg.className = "editor-msg error";
        }
    } catch (e) {
        fileViewerMsg.textContent = "Error: " + e.message;
        fileViewerMsg.className = "editor-msg error";
    } finally {
        fileSaveBtn.disabled = false;
        fileSaveBtn.textContent = "SAVE";
    }
});

fileViewerBack.addEventListener("click", () => {
    if (fileBrowserHistory.length > 0) {
        const prev = fileBrowserHistory.pop();
        openFileBrowser(prev);
    }
});

// ── New File ─────────────────────────────────────────
const fileNewBtn = document.getElementById("file-viewer-new");
if (fileNewBtn) {
    fileNewBtn.addEventListener("click", async () => {
        const suggested = (fileBrowserCurrentDir ? fileBrowserCurrentDir + "/" : "") + "untitled.md";
        const relPath = prompt("新檔案路徑（相對 notebook root）：", suggested);
        if (!relPath || !relPath.trim()) return;
        const path = relPath.trim();
        try {
            const r = await fetch("/api/files/write", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path, content: "" }),
            });
            const data = await r.json();
            if (!data.ok) {
                alert("建立失敗：" + (data.error || "unknown"));
                return;
            }
            // Push current dir to history so BACK works
            fileBrowserHistory.push(fileBrowserCurrentDir);
            openFileViewer(path);
            // Auto-enter edit mode after viewer loads
            setTimeout(() => {
                if (currentFilePath === path && fileEditBtn.style.display !== "none") {
                    fileEditBtn.click();
                }
            }, 200);
        } catch (e) {
            alert("Error: " + e.message);
        }
    });
}

fileViewerClose.addEventListener("click", () => {
    fileViewerModal.style.display = "none";
    fileBrowserHistory = [];
});

fileViewerModal.addEventListener("click", (e) => {
    if (e.target === fileViewerModal) {
        fileViewerModal.style.display = "none";
        fileBrowserHistory = [];
    }
});

// ── Actions ──────────────────────────────────────────

let attachedFiles = [];

function sendMessage(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!text.trim() && pendingImages.length === 0) return;

    const imagePaths = pendingImages.filter(i => i.path).map(i => i.path);
    const filePaths = attachedFiles.slice();
    const allAttach = [...imagePaths, ...filePaths];
    addMessage("user", text, allAttach.length > 0 ? allAttach : null);
    setStatus("PROCESSING", "online");
    setAvatar("thinking");
    setIndicator("TRANSMITTING...");

    ws.send(JSON.stringify({ type: "message", text, image_paths: imagePaths, file_paths: filePaths }));
    pendingImages = [];
    attachedFiles = [];
    renderImageBar();
    renderFileAttachBar();
}

function runSop(key) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (streaming) return;
    ws.send(JSON.stringify({ type: "run_sop", key }));
}

function cancelStream() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "cancel" }));
}

// ── Image Handling ───────────────────────────────────

function renderImageBar() {
    if (pendingImages.length === 0) {
        imageBar.innerHTML = "";
        imageBar.classList.remove("active");
        return;
    }
    imageBar.classList.add("active");
    imageBar.innerHTML = pendingImages.map((img, i) =>
        `<span class="image-tag">${escapeHtml(img.name)} <span class="image-remove" data-idx="${i}">&times;</span></span>`
    ).join("");
    imageBar.querySelectorAll(".image-remove").forEach(el => {
        el.addEventListener("click", () => {
            pendingImages.splice(parseInt(el.dataset.idx), 1);
            renderImageBar();
        });
    });
}

async function uploadImage(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = async () => {
            try {
                const resp = await fetch("/api/upload", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ data: reader.result.split(",")[1], filename: file.name }),
                });
                const result = await resp.json();
                if (result.error) { addErrorMsg(result.error); reject(new Error(result.error)); }
                else resolve(result.path);
            } catch (e) { addErrorMsg(`Upload failed: ${e.message}`); reject(e); }
        };
        reader.readAsDataURL(file);
    });
}

function addImageFiles(files) {
    for (const file of files) {
        if (!file.type.startsWith("image/")) continue;
        const entry = { file, name: file.name || "screenshot.png", path: null };
        pendingImages.push(entry);
        renderImageBar();
        uploadImage(file).then(path => { entry.path = path; }).catch(() => {});
    }
}

// ── Event Listeners ──────────────────────────────────

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (streaming) return;
    const text = chatInput.value.trim();
    if (!text && pendingImages.length === 0) return;
    sendMessage(text);
    chatInput.value = "";
    chatInput.style.height = "auto";
});

btnCancel.addEventListener("click", cancelStream);

chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 80) + "px";
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
    if (e.key === "Escape" && pendingImages.length > 0) {
        pendingImages = [];
        renderImageBar();
    }
});

// Ctrl+K — Command Palette
document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        if (paletteOverlay.style.display === "none") openPalette();
        else closePalette();
        return;
    }
    // Palette navigation — handle globally so arrow keys work even if focus drifts
    if (paletteOverlay.style.display !== "none") {
        const items = getPaletteItems(paletteSearch.value);
        if (e.key === "ArrowDown") {
            e.preventDefault();
            paletteSelectedIdx = Math.min(paletteSelectedIdx + 1, items.length - 1);
            renderPaletteItems(paletteSearch.value);
            paletteSearch.focus();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            paletteSelectedIdx = Math.max(paletteSelectedIdx - 1, 0);
            renderPaletteItems(paletteSearch.value);
            paletteSearch.focus();
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (items[paletteSelectedIdx]) executePaletteItem(items[paletteSelectedIdx]);
        } else if (e.key === "Escape") {
            closePalette();
        }
    }
});

// Paste
document.addEventListener("paste", (e) => {
    if (paletteOverlay.style.display !== "none") return;
    if (fileViewerModal.style.display !== "none") return;
    const items = e.clipboardData?.items;
    if (!items) return;
    const files = [];
    for (const item of items) {
        if (item.type.startsWith("image/")) {
            const f = item.getAsFile();
            if (f) files.push(f);
        }
    }
    if (files.length > 0) {
        e.preventDefault();
        addImageFiles(files);
    }
});

// Drag & drop
const terminalPanel = document.querySelector(".terminal-panel");

terminalPanel.addEventListener("dragover", (e) => {
    e.preventDefault();
    terminalPanel.style.borderColor = "var(--primary)";
});

terminalPanel.addEventListener("dragleave", () => {
    terminalPanel.style.borderColor = "";
});

terminalPanel.addEventListener("drop", (e) => {
    e.preventDefault();
    terminalPanel.style.borderColor = "";
    const files = [...e.dataTransfer.files].filter(f => f.type.startsWith("image/"));
    if (files.length > 0) addImageFiles(files);
});

// ── Session History ──────────────────────────────────

const btnSessions = document.getElementById("btn-sessions");
const modalSessions = document.getElementById("modal-sessions");
const sessionsList = document.getElementById("sessions-list");

function openSessions() {
    modalSessions.style.display = "flex";
    sessionsList.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fetch("/api/sessions").then(r => r.json()).then(sessions => {
        if (sessions.length === 0) {
            sessionsList.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">No archived sessions</div>';
            return;
        }
        sessionsList.innerHTML = sessions.map(s => `
            <div class="session-item" data-id="${s.id}">
                <div class="session-name">${escapeHtml(s.name || "Unnamed")}</div>
                <div class="session-meta">${s.message_count} messages &middot; ${new Date(s.created).toLocaleString()}</div>
            </div>
        `).join("");
        sessionsList.querySelectorAll(".session-item").forEach(el => {
            el.addEventListener("click", () => loadSessionDetail(el.dataset.id));
        });
    }).catch(e => {
        sessionsList.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${e.message}</div>`;
    });
}

btnSessions.addEventListener("click", openSessions);

document.getElementById("modal-close-btn").addEventListener("click", () => {
    modalSessions.style.display = "none";
});

modalSessions.addEventListener("click", (e) => {
    if (e.target === modalSessions) modalSessions.style.display = "none";
});

// ── Persona Editor ───────────────────────────────────

const personaModal = document.getElementById("modal-persona");
const personaEditor = document.getElementById("persona-editor");
const personaSave = document.getElementById("persona-save");
const personaReset = document.getElementById("persona-reset");
const personaClose = document.getElementById("persona-close");
const personaMsg = document.getElementById("persona-msg");

function openPersonaEditor() {
    personaModal.style.display = "flex";
    personaMsg.textContent = "";
    personaMsg.className = "editor-msg";
    fetch("/api/persona").then(r => r.json()).then(data => {
        personaEditor.value = data.content;
    });
}

personaSave.addEventListener("click", async () => {
    try {
        const r = await fetch("/api/persona", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: personaEditor.value }),
        });
        if (r.ok) {
            personaMsg.textContent = "Persona saved";
            personaMsg.className = "editor-msg success";
        }
    } catch (e) {
        personaMsg.textContent = "Error: " + e.message;
        personaMsg.className = "editor-msg error";
    }
});

personaReset.addEventListener("click", async () => {
    try {
        const r = await fetch("/api/persona/reset", { method: "POST" });
        const data = await r.json();
        personaEditor.value = data.content;
        personaMsg.textContent = "Reset to default";
        personaMsg.className = "editor-msg success";
    } catch (e) {
        personaMsg.textContent = "Error: " + e.message;
        personaMsg.className = "editor-msg error";
    }
});

personaClose.addEventListener("click", () => { personaModal.style.display = "none"; });
personaModal.addEventListener("click", (e) => { if (e.target === personaModal) personaModal.style.display = "none"; });

// ── Memory Management ────────────────────────────────

const memoryModal = document.getElementById("modal-memory");
const memoryEditor = document.getElementById("memory-editor");
const memorySave = document.getElementById("memory-save");
const memoryClose = document.getElementById("memory-close");
const memoryMsg = document.getElementById("memory-msg");
const memoryVectorMsg = document.getElementById("memory-vector-msg");
const memoryAddInput = document.getElementById("memory-add-input");
const memoryAddCategory = document.getElementById("memory-add-category");
const memoryAddBtn = document.getElementById("memory-add-btn");
const memoryFilterCategory = document.getElementById("memory-filter-category");
const memoryEntriesList = document.getElementById("memory-entries-list");
const memoryCount = document.getElementById("memory-count");

// Tab switching
document.querySelectorAll(".memory-tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".memory-tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".memory-tab-content").forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById("memory-tab-" + tab.dataset.tab).classList.add("active");
        if (tab.dataset.tab === "flat") {
            loadFlatMemory();
        } else {
            loadVectorMemories();
        }
    });
});

function openMemoryEditor() {
    memoryModal.style.display = "flex";
    memoryVectorMsg.textContent = "";
    memoryVectorMsg.className = "editor-msg";
    memoryMsg.textContent = "";
    memoryMsg.className = "editor-msg";
    // Default to vector tab
    document.querySelectorAll(".memory-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === "vector"));
    document.querySelectorAll(".memory-tab-content").forEach(c => c.classList.remove("active"));
    document.getElementById("memory-tab-vector").classList.add("active");
    loadVectorMemories();
}

function loadFlatMemory() {
    fetch("/api/memory").then(r => r.json()).then(data => {
        memoryEditor.value = data.content;
    });
}

async function loadVectorMemories() {
    const cat = memoryFilterCategory.value;
    const url = cat ? `/api/memory/entries?category=${encodeURIComponent(cat)}` : "/api/memory/entries";
    memoryEntriesList.innerHTML = '<div class="memory-loading">Loading...</div>';
    try {
        const r = await fetch(url);
        const data = await r.json();
        if (data.error) {
            memoryEntriesList.innerHTML = `<div class="memory-empty">${escapeHtml(data.error)}</div>`;
            memoryCount.textContent = "Error";
            return;
        }
        memoryCount.textContent = `${data.count} memories`;
        if (data.entries.length === 0) {
            memoryEntriesList.innerHTML = '<div class="memory-empty">No memories stored</div>';
            return;
        }
        memoryEntriesList.innerHTML = "";
        for (const entry of data.entries) {
            const el = document.createElement("div");
            el.className = "memory-entry";
            el.innerHTML = `
                <div class="memory-entry-header">
                    <span class="memory-entry-category">${escapeHtml(entry.category)}</span>
                    <span class="memory-entry-date">${new Date(entry.created).toLocaleDateString()}</span>
                    <button class="memory-entry-delete" data-id="${escapeHtml(entry.id)}" title="Forget">&times;</button>
                </div>
                <div class="memory-entry-content">${escapeHtml(entry.content)}</div>
            `;
            el.querySelector(".memory-entry-delete").addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = e.target.dataset.id;
                try {
                    const resp = await fetch(`/api/memory/entries/${encodeURIComponent(id)}`, { method: "DELETE" });
                    if (resp.ok) {
                        el.remove();
                        memoryVectorMsg.textContent = "Memory forgotten";
                        memoryVectorMsg.className = "editor-msg success";
                        loadVectorMemories();
                    }
                } catch (err) {
                    memoryVectorMsg.textContent = "Error: " + err.message;
                    memoryVectorMsg.className = "editor-msg error";
                }
            });
            memoryEntriesList.appendChild(el);
        }
    } catch (e) {
        memoryEntriesList.innerHTML = `<div class="memory-empty">Unavailable — embedding provider not configured</div>`;
        memoryCount.textContent = "—";
    }
}

memoryAddBtn.addEventListener("click", async () => {
    const content = memoryAddInput.value.trim();
    if (!content) return;
    memoryAddBtn.disabled = true;
    memoryVectorMsg.textContent = "";
    try {
        const r = await fetch("/api/memory/entries", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content, category: memoryAddCategory.value }),
        });
        if (r.ok) {
            memoryAddInput.value = "";
            memoryVectorMsg.textContent = "Memory added";
            memoryVectorMsg.className = "editor-msg success";
            loadVectorMemories();
        } else {
            const data = await r.json();
            memoryVectorMsg.textContent = data.error || "Failed";
            memoryVectorMsg.className = "editor-msg error";
        }
    } catch (e) {
        memoryVectorMsg.textContent = "Error: " + e.message;
        memoryVectorMsg.className = "editor-msg error";
    } finally {
        memoryAddBtn.disabled = false;
    }
});

memoryFilterCategory.addEventListener("change", loadVectorMemories);

memoryAddInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); memoryAddBtn.click(); }
});

memorySave.addEventListener("click", async () => {
    try {
        const r = await fetch("/api/memory", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: memoryEditor.value }),
        });
        if (r.ok) {
            memoryMsg.textContent = "Memory saved";
            memoryMsg.className = "editor-msg success";
        }
    } catch (e) {
        memoryMsg.textContent = "Error: " + e.message;
        memoryMsg.className = "editor-msg error";
    }
});

memoryClose.addEventListener("click", () => { memoryModal.style.display = "none"; });
memoryModal.addEventListener("click", (e) => { if (e.target === memoryModal) memoryModal.style.display = "none"; });

// ── Search Modal ─────────────────────────────────────

const searchModal = document.getElementById("modal-search");
const searchQueryInput = document.getElementById("search-query-input");
const searchBtn = document.getElementById("search-btn");
const searchStatus = document.getElementById("search-status");
const searchResults = document.getElementById("search-results");
const searchClose = document.getElementById("search-close");

function openSearchModal() {
    searchModal.style.display = "flex";
    searchStatus.textContent = "";
    searchResults.innerHTML = "";
    setTimeout(() => searchQueryInput.focus(), 50);
}

async function executeSearch() {
    const q = searchQueryInput.value.trim();
    if (!q) return;
    searchBtn.disabled = true;
    searchStatus.textContent = "Searching...";
    searchStatus.className = "search-status";
    searchResults.innerHTML = "";
    try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&k=10`);
        const data = await r.json();
        if (data.error) {
            searchStatus.textContent = data.error;
            searchStatus.className = "search-status error";
            return;
        }
        const results = data.results || [];
        searchStatus.textContent = `${results.length} results`;
        searchStatus.className = "search-status";
        if (results.length === 0) {
            searchResults.innerHTML = `<div class="search-empty">No matching notes found<br><button class="action-btn mini" style="margin-top:12px" onclick="document.getElementById('modal-search').style.display='none';buildIndex()">BUILD INDEX</button></div>`;
            return;
        }
        searchResults.innerHTML = "";
        for (const res of results) {
            const el = document.createElement("div");
            el.className = "search-result-item";
            const scoreBar = Math.max(5, Math.min(100, (1 - res.score) * 100));
            el.innerHTML = `
                <div class="search-result-header">
                    <span class="search-result-source">${escapeHtml(res.source)}</span>
                    <span class="search-result-heading">${escapeHtml(res.heading || "")}</span>
                    <div class="search-result-score-bar"><div class="search-result-score-fill" style="width:${scoreBar}%"></div></div>
                </div>
                <div class="search-result-text">${escapeHtml(res.text.substring(0, 300))}${res.text.length > 300 ? "..." : ""}</div>
            `;
            el.addEventListener("click", () => {
                searchModal.style.display = "none";
                openFileViewer(res.source);
            });
            searchResults.appendChild(el);
        }
    } catch (e) {
        searchStatus.textContent = "Error: " + e.message;
        searchStatus.className = "search-status error";
    } finally {
        searchBtn.disabled = false;
    }
}

searchBtn.addEventListener("click", executeSearch);
searchQueryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); executeSearch(); }
    if (e.key === "Escape") { searchModal.style.display = "none"; }
});
searchClose.addEventListener("click", () => { searchModal.style.display = "none"; });
searchModal.addEventListener("click", (e) => { if (e.target === searchModal) searchModal.style.display = "none"; });

// ── Model Selector ───────────────────────────────────

const modelModal = document.getElementById("modal-model");
const modelToolSelect = document.getElementById("model-tool-select");
const modelModelSelect = document.getElementById("model-model-select");
const modelSave = document.getElementById("model-save");
const modelClose = document.getElementById("model-close");
const modelMsg = document.getElementById("model-msg");

let modelData = null;

function openModelSelector() {
    modelModal.style.display = "flex";
    modelMsg.textContent = "";
    modelMsg.className = "editor-msg";
    fetch("/api/models").then(r => r.json()).then(data => {
        modelData = data;
        // Populate tool select
        modelToolSelect.innerHTML = "";
        for (const tool of Object.keys(data.tools)) {
            const opt = document.createElement("option");
            opt.value = tool;
            opt.textContent = tool;
            if (tool === data.current_tool) opt.selected = true;
            modelToolSelect.appendChild(opt);
        }
        populateModelOptions(data.current_tool, data.current_model);
    });
}

function populateModelOptions(tool, currentModel) {
    modelModelSelect.innerHTML = "";
    if (!modelData || !modelData.tools[tool]) return;
    for (const m of modelData.tools[tool]) {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.label;
        if (m.id === currentModel) opt.selected = true;
        modelModelSelect.appendChild(opt);
    }
}

modelToolSelect.addEventListener("change", () => {
    populateModelOptions(modelToolSelect.value, "");
});

modelSave.addEventListener("click", async () => {
    try {
        const r = await fetch("/api/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ai_tool: modelToolSelect.value,
                ai_model: modelModelSelect.value,
            }),
        });
        const result = await r.json();
        if (r.ok) {
            modelMsg.textContent = `Switched to ${result.ai_tool} / ${result.ai_model || "(default)"}`;
            modelMsg.className = "editor-msg success";
        }
    } catch (e) {
        modelMsg.textContent = "Error: " + e.message;
        modelMsg.className = "editor-msg error";
    }
});

modelClose.addEventListener("click", () => { modelModal.style.display = "none"; });
modelModal.addEventListener("click", (e) => { if (e.target === modelModal) modelModal.style.display = "none"; });

// ── Bot Management ───────────────────────────────────

const botStatusBlock = document.getElementById("bot-status-block");
const botStatusDot = document.getElementById("bot-status-dot");
const botSetupModal = document.getElementById("modal-bot-setup");
const botTokenInput = document.getElementById("bot-token-input");
const botTokenSave = document.getElementById("bot-token-save");
const botSetupMsg = document.getElementById("bot-setup-msg");
const botSetupStatus = document.getElementById("bot-setup-status");
const botBtnStart = document.getElementById("bot-btn-start");
const botBtnStop = document.getElementById("bot-btn-stop");
const botSetupClose = document.getElementById("bot-setup-close");

let botState = { has_token: false, running: false };

function updateBotStatusDot() {
    botStatusDot.className = "bot-status-dot";
    if (botState.running) {
        botStatusDot.classList.add("connected");
    } else if (botState.has_token) {
        botStatusDot.classList.add("disconnected");
    } else {
        botStatusDot.classList.add("no-token");
    }
}

function updateBotSetupUI() {
    if (botState.running) {
        botSetupStatus.textContent = "CONNECTED";
        botSetupStatus.className = "bot-setup-status-value running";
        botBtnStart.style.display = "none";
        botBtnStop.style.display = "";
    } else if (botState.has_token) {
        botSetupStatus.textContent = "STOPPED";
        botSetupStatus.className = "bot-setup-status-value stopped";
        botBtnStart.style.display = "";
        botBtnStop.style.display = "none";
    } else {
        botSetupStatus.textContent = "NO TOKEN";
        botSetupStatus.className = "bot-setup-status-value no-token";
        botBtnStart.style.display = "none";
        botBtnStop.style.display = "none";
    }
}

async function fetchBotStatus() {
    try {
        const r = await fetch("/api/bot/status");
        botState = await r.json();
        updateBotStatusDot();
        updateBotSetupUI();
    } catch { /* ignore */ }
}

botStatusBlock.addEventListener("click", () => {
    botSetupModal.style.display = "flex";
    botSetupMsg.textContent = "";
    botSetupMsg.className = "bot-setup-msg";
    fetchBotStatus();
});

botSetupClose.addEventListener("click", () => { botSetupModal.style.display = "none"; });
botSetupModal.addEventListener("click", (e) => { if (e.target === botSetupModal) botSetupModal.style.display = "none"; });

botTokenSave.addEventListener("click", async () => {
    const token = botTokenInput.value.trim();
    if (!token) {
        botSetupMsg.textContent = "Please enter a token";
        botSetupMsg.className = "bot-setup-msg error";
        return;
    }
    botTokenSave.disabled = true;
    try {
        const r = await fetch("/api/bot/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
        });
        const result = await r.json();
        if (r.ok) {
            botSetupMsg.textContent = "Token saved successfully";
            botSetupMsg.className = "bot-setup-msg success";
            botTokenInput.value = "";
            await fetchBotStatus();
        } else {
            botSetupMsg.textContent = result.error || "Failed";
            botSetupMsg.className = "bot-setup-msg error";
        }
    } catch (e) {
        botSetupMsg.textContent = "Error: " + e.message;
        botSetupMsg.className = "bot-setup-msg error";
    } finally {
        botTokenSave.disabled = false;
    }
});

botBtnStart.addEventListener("click", async () => {
    botBtnStart.disabled = true;
    botSetupMsg.textContent = "";
    try {
        const r = await fetch("/api/bot/start", { method: "POST" });
        const result = await r.json();
        if (r.ok) {
            botSetupMsg.textContent = "Bot started";
            botSetupMsg.className = "bot-setup-msg success";
        } else {
            botSetupMsg.textContent = result.error || "Failed to start";
            botSetupMsg.className = "bot-setup-msg error";
        }
        await fetchBotStatus();
    } catch (e) {
        botSetupMsg.textContent = "Error: " + e.message;
        botSetupMsg.className = "bot-setup-msg error";
    } finally {
        botBtnStart.disabled = false;
    }
});

botBtnStop.addEventListener("click", async () => {
    botBtnStop.disabled = true;
    try {
        const r = await fetch("/api/bot/stop", { method: "POST" });
        const result = await r.json();
        if (r.ok) {
            botSetupMsg.textContent = "Bot stopped";
            botSetupMsg.className = "bot-setup-msg success";
        } else {
            botSetupMsg.textContent = result.error || "Failed to stop";
            botSetupMsg.className = "bot-setup-msg error";
        }
        await fetchBotStatus();
    } catch (e) {
        botSetupMsg.textContent = "Error: " + e.message;
        botSetupMsg.className = "bot-setup-msg error";
    } finally {
        botBtnStop.disabled = false;
    }
});

// Poll bot status every 10s
setInterval(fetchBotStatus, 10000);

// ── Reminders ────────────────────────────────────────

const reminderModal = document.getElementById("modal-reminders");
const reminderClose = document.getElementById("reminders-close");
const reminderTextInput = document.getElementById("reminder-text-input");
const reminderTimeInput = document.getElementById("reminder-time-input");
const reminderAddBtn = document.getElementById("reminder-add-btn");
const reminderMsg = document.getElementById("reminder-msg");
const reminderList = document.getElementById("reminder-list");
const reminderEmpty = document.getElementById("reminder-empty");
const statReminders = document.getElementById("stat-reminders");
const reminderBlock = document.getElementById("stat-reminder-block");

async function fetchReminders() {
    try {
        const r = await fetch("/api/reminders");
        const data = await r.json();
        const items = data.reminders || [];
        statReminders.textContent = items.length || "0";
        statReminders.className = "stat-value" + (items.length > 0 ? " warn" : "");
        return items;
    } catch {
        return [];
    }
}

function renderReminders(items) {
    reminderList.innerHTML = "";
    if (!items.length) {
        reminderEmpty.style.display = "";
        return;
    }
    reminderEmpty.style.display = "none";
    for (const r of items) {
        const el = document.createElement("div");
        el.className = "reminder-item";
        const fireAt = new Date(r.fire_at);
        const timeStr = fireAt.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
        el.innerHTML = `
            <span class="reminder-item-time">${timeStr}</span>
            <span class="reminder-item-text">${escapeHtml(r.text)}</span>
            <button class="reminder-item-cancel" data-id="${r.id}">CANCEL</button>
        `;
        el.querySelector(".reminder-item-cancel").addEventListener("click", async () => {
            await fetch(`/api/reminders/${r.id}`, { method: "DELETE" });
            openRemindersModal();
        });
        reminderList.appendChild(el);
    }
}

async function openRemindersModal() {
    reminderModal.style.display = "flex";
    reminderMsg.textContent = "";
    reminderMsg.className = "editor-msg";
    const items = await fetchReminders();
    renderReminders(items);
}

reminderBlock.addEventListener("click", (e) => {
    e.stopPropagation();
    openRemindersModal();
});

reminderClose.addEventListener("click", () => { reminderModal.style.display = "none"; });
reminderModal.addEventListener("click", (e) => { if (e.target === reminderModal) reminderModal.style.display = "none"; });

reminderAddBtn.addEventListener("click", async () => {
    const text = reminderTextInput.value.trim();
    const time = reminderTimeInput.value.trim();
    if (!text || !time) {
        reminderMsg.textContent = "Text and time are required";
        reminderMsg.className = "editor-msg error";
        return;
    }
    reminderAddBtn.disabled = true;
    try {
        const r = await fetch("/api/reminders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, fire_at: time }),
        });
        const result = await r.json();
        if (r.ok) {
            reminderMsg.textContent = "Reminder set";
            reminderMsg.className = "editor-msg success";
            reminderTextInput.value = "";
            reminderTimeInput.value = "";
            const items = await fetchReminders();
            renderReminders(items);
        } else {
            reminderMsg.textContent = result.error || "Failed";
            reminderMsg.className = "editor-msg error";
        }
    } catch (e) {
        reminderMsg.textContent = "Error: " + e.message;
        reminderMsg.className = "editor-msg error";
    } finally {
        reminderAddBtn.disabled = false;
    }
});

reminderTimeInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") reminderAddBtn.click();
});

// Poll reminders every 30s
fetchReminders();
setInterval(fetchReminders, 30000);

// ── Memory Search & Import ───────────────────────────

const memorySearchInput = document.getElementById("memory-search-input");
const memorySearchBtn = document.getElementById("memory-search-btn");
const memoryImportBtn = document.getElementById("memory-import-btn");

memorySearchBtn.addEventListener("click", async () => {
    const q = memorySearchInput.value.trim();
    if (!q) { loadVectorMemories(); return; }
    memoryEntriesList.innerHTML = '<div class="memory-loading">Searching...</div>';
    try {
        const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&k=10`);
        const data = await r.json();
        if (data.error) {
            memoryEntriesList.innerHTML = `<div class="memory-empty">${escapeHtml(data.error)}</div>`;
            return;
        }
        memoryCount.textContent = `${data.entries.length} results`;
        if (data.entries.length === 0) {
            memoryEntriesList.innerHTML = '<div class="memory-empty">No matching memories</div>';
            return;
        }
        memoryEntriesList.innerHTML = "";
        for (const entry of data.entries) {
            const el = document.createElement("div");
            el.className = "memory-entry";
            el.innerHTML = `
                <div class="memory-entry-header">
                    <span class="memory-entry-category">${escapeHtml(entry.category)}</span>
                    <span class="memory-entry-date">${new Date(entry.created).toLocaleDateString()}</span>
                    <button class="memory-entry-delete" data-id="${escapeHtml(entry.id)}" title="Forget">&times;</button>
                </div>
                <div class="memory-entry-content">${escapeHtml(entry.content)}</div>
            `;
            el.querySelector(".memory-entry-delete").addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = e.target.dataset.id;
                try {
                    await fetch(`/api/memory/entries/${encodeURIComponent(id)}`, { method: "DELETE" });
                    el.remove();
                } catch {}
            });
            memoryEntriesList.appendChild(el);
        }
    } catch (e) {
        memoryEntriesList.innerHTML = `<div class="memory-empty">Search failed: ${escapeHtml(e.message)}</div>`;
    }
});

memorySearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); memorySearchBtn.click(); }
});

memoryImportBtn.addEventListener("click", async () => {
    memoryImportBtn.disabled = true;
    memoryVectorMsg.textContent = "Importing...";
    memoryVectorMsg.className = "editor-msg";
    try {
        const r = await fetch("/api/memory/import", { method: "POST" });
        const data = await r.json();
        if (r.ok) {
            memoryVectorMsg.textContent = `Imported ${data.imported} memories from memory.md`;
            memoryVectorMsg.className = "editor-msg success";
            loadVectorMemories();
        } else {
            memoryVectorMsg.textContent = data.error || "Import failed";
            memoryVectorMsg.className = "editor-msg error";
        }
    } catch (e) {
        memoryVectorMsg.textContent = "Error: " + e.message;
        memoryVectorMsg.className = "editor-msg error";
    } finally {
        memoryImportBtn.disabled = false;
    }
});

// ── SOP Input Modal ──────────────────────────────────

const sopInputModal = document.getElementById("modal-sop-input");
const sopInputTitle = document.getElementById("sop-input-title");
const sopInputHint = document.getElementById("sop-input-hint");
const sopInputFields = document.getElementById("sop-input-fields");
const sopInputRun = document.getElementById("sop-input-run");
const sopInputClose = document.getElementById("sop-input-close");

let pendingSopKey = null;

function showSopInputModal(msg) {
    pendingSopKey = msg.key;
    sopInputTitle.textContent = `${msg.icon} ${msg.label} — PARAMETERS`;
    sopInputHint.textContent = `This SOP requires input parameters.`;
    sopInputFields.innerHTML = "";
    for (const inp of msg.inputs) {
        const row = document.createElement("div");
        row.className = "model-row";
        const label = inp.description || inp.name;
        const typeHint = inp.type !== "string" ? ` (${inp.type})` : "";
        row.innerHTML = `
            <label class="model-label">${escapeHtml(label)}${typeHint}</label>
            <input type="text" class="settings-input" data-input-name="${escapeHtml(inp.name)}"
                value="${escapeHtml(inp.default || "")}" placeholder="${escapeHtml(inp.name)}">
        `;
        sopInputFields.appendChild(row);
    }
    sopInputModal.style.display = "flex";
    const firstInput = sopInputFields.querySelector("input");
    if (firstInput) setTimeout(() => firstInput.focus(), 50);
}

sopInputRun.addEventListener("click", () => {
    if (!pendingSopKey) return;
    const inputs = {};
    sopInputFields.querySelectorAll("[data-input-name]").forEach(el => {
        inputs[el.dataset.inputName] = el.value;
    });
    sopInputModal.style.display = "none";
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "run_sop", key: pendingSopKey, inputs }));
    }
    pendingSopKey = null;
});

sopInputClose.addEventListener("click", () => { sopInputModal.style.display = "none"; pendingSopKey = null; });
sopInputModal.addEventListener("click", (e) => { if (e.target === sopInputModal) { sopInputModal.style.display = "none"; pendingSopKey = null; } });

// ── File Attachment ──────────────────────────────────

const btnAttach = document.getElementById("btn-attach");
const fileAttachBar = document.getElementById("file-attach-bar");

function renderFileAttachBar() {
    if (attachedFiles.length === 0) {
        fileAttachBar.innerHTML = "";
        fileAttachBar.classList.remove("active");
        return;
    }
    fileAttachBar.classList.add("active");
    fileAttachBar.innerHTML = attachedFiles.map((fp, i) =>
        `<span class="image-tag">📎 ${escapeHtml(fp)} <span class="image-remove" data-file-idx="${i}">&times;</span></span>`
    ).join("");
    fileAttachBar.querySelectorAll(".image-remove").forEach(el => {
        el.addEventListener("click", () => {
            attachedFiles.splice(parseInt(el.dataset.fileIdx), 1);
            renderFileAttachBar();
        });
    });
}

btnAttach.addEventListener("click", () => {
    // Open file browser in selection mode
    openFileBrowserForAttach();
});

function openFileBrowserForAttach(path) {
    const relPath = path || "";
    fileViewerModal.style.display = "flex";
    fileViewerTitle.textContent = "ATTACH FILE — " + (relPath || "NOTEBOOK");
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = fileBrowserHistory.length > 0 ? "" : "none";

    fetch(`/api/files?path=${encodeURIComponent(relPath)}`).then(r => r.json()).then(items => {
        if (items.error) {
            fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">${escapeHtml(items.error)}</div>`;
            return;
        }
        fileViewerBody.innerHTML = "";
        for (const item of items) {
            const el = document.createElement("div");
            el.className = "file-item" + (item.type === "dir" ? " dir" : "");
            el.innerHTML = `
                <span class="file-item-icon">${item.type === "dir" ? "📁" : "📄"}</span>
                <span class="file-item-name">${escapeHtml(item.name)}</span>
            `;
            el.addEventListener("click", () => {
                if (item.type === "dir") {
                    fileBrowserHistory.push(relPath);
                    openFileBrowserForAttach(item.path);
                } else {
                    // Attach file
                    if (!attachedFiles.includes(item.path)) {
                        attachedFiles.push(item.path);
                        renderFileAttachBar();
                    }
                    fileViewerModal.style.display = "none";
                    fileBrowserHistory = [];
                    chatInput.focus();
                }
            });
            fileViewerBody.appendChild(el);
        }
    }).catch(e => {
        fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${escapeHtml(e.message)}</div>`;
    });
}

// ── Directives Manager ───────────────────────────────

const directivesModal = document.getElementById("modal-directives");
const directiveList = document.getElementById("directive-list");
const directiveAddTrigger = document.getElementById("directive-add-trigger");
const directiveAddFilename = document.getElementById("directive-add-filename");
const directiveAddBody = document.getElementById("directive-add-body");
const directiveAddBtn = document.getElementById("directive-add-btn");
const directiveMsg = document.getElementById("directive-msg");
const directivesClose = document.getElementById("directives-close");

function openDirectives() {
    directivesModal.style.display = "flex";
    directiveMsg.textContent = "";
    loadDirectives();
}

async function loadDirectives() {
    directiveList.innerHTML = '<div class="memory-loading">Loading...</div>';
    try {
        const r = await fetch("/api/directives");
        const data = await r.json();
        directiveList.innerHTML = "";
        if (data.directives.length === 0) {
            directiveList.innerHTML = '<div class="memory-empty">No directives configured</div>';
            return;
        }
        for (const d of data.directives) {
            const el = document.createElement("div");
            el.className = "memory-entry";
            el.innerHTML = `
                <div class="memory-entry-header">
                    <span class="memory-entry-category">${escapeHtml(d.trigger)}</span>
                    <span class="memory-entry-date">${d.is_user ? "user" : "built-in"}</span>
                    ${d.is_user ? `<button class="memory-entry-delete" data-filename="${escapeHtml(d.filename)}" title="Delete">&times;</button>` : ""}
                </div>
                <div class="memory-entry-content">${escapeHtml(d.body.substring(0, 200))}${d.body.length > 200 ? "..." : ""}</div>
            `;
            if (d.is_user) {
                el.querySelector(".memory-entry-delete").addEventListener("click", async (e) => {
                    e.stopPropagation();
                    try {
                        await fetch(`/api/directives/${encodeURIComponent(e.target.dataset.filename)}`, { method: "DELETE" });
                        el.remove();
                        directiveMsg.textContent = "Directive deleted";
                        directiveMsg.className = "editor-msg success";
                    } catch (err) {
                        directiveMsg.textContent = "Error: " + err.message;
                        directiveMsg.className = "editor-msg error";
                    }
                });
            }
            directiveList.appendChild(el);
        }
    } catch (e) {
        directiveList.innerHTML = `<div class="memory-empty">Error: ${escapeHtml(e.message)}</div>`;
    }
}

directiveAddBtn.addEventListener("click", async () => {
    const trigger = directiveAddTrigger.value.trim();
    const filename = directiveAddFilename.value.trim() || trigger;
    const body = directiveAddBody.value.trim();
    if (!trigger || !body) {
        directiveMsg.textContent = "Trigger and body are required";
        directiveMsg.className = "editor-msg error";
        return;
    }
    directiveAddBtn.disabled = true;
    try {
        const r = await fetch("/api/directives", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename, trigger, body }),
        });
        if (r.ok) {
            directiveAddTrigger.value = "";
            directiveAddFilename.value = "";
            directiveAddBody.value = "";
            directiveMsg.textContent = "Directive created";
            directiveMsg.className = "editor-msg success";
            loadDirectives();
        } else {
            const data = await r.json();
            directiveMsg.textContent = data.error || "Failed";
            directiveMsg.className = "editor-msg error";
        }
    } catch (e) {
        directiveMsg.textContent = "Error: " + e.message;
        directiveMsg.className = "editor-msg error";
    } finally {
        directiveAddBtn.disabled = false;
    }
});

directivesClose.addEventListener("click", () => { directivesModal.style.display = "none"; });
directivesModal.addEventListener("click", (e) => { if (e.target === directivesModal) directivesModal.style.display = "none"; });

// ── Settings Panel ───────────────────────────────────

const settingsModal = document.getElementById("modal-settings");
const settingsClose = document.getElementById("settings-close");
const settingsSave = document.getElementById("settings-save");
const settingsMsg = document.getElementById("settings-msg");

function openSettings() {
    settingsModal.style.display = "flex";
    settingsMsg.textContent = "";
    document.getElementById("settings-bot-token").value = "";
    fetch("/api/settings").then(r => r.json()).then(data => {
        document.getElementById("settings-notebook-root").value = data.notebook_root || "";
        document.getElementById("settings-ollama-url").value = data.ollama_base_url || "";
        document.getElementById("settings-inbox").value = data.paths?.inbox || "";
        document.getElementById("settings-tasks").value = data.paths?.tasks || "";
        document.getElementById("settings-daily-dir").value = data.paths?.daily_dir || "";
        document.getElementById("settings-projects-dir").value = data.paths?.projects_dir || "";
        document.getElementById("settings-assets-dir").value = data.paths?.assets_dir || "";
        document.getElementById("settings-bot-ids").value = (data.bot?.allowed_chat_ids || []).join(", ");
        document.getElementById("settings-bot-token").placeholder = data.bot?.has_token ? "Token saved (paste new to replace)" : "Paste Telegram bot token";
    });
}

settingsSave.addEventListener("click", async () => {
    const idsStr = document.getElementById("settings-bot-ids").value.trim();
    const ids = idsStr ? idsStr.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [];
    const newToken = document.getElementById("settings-bot-token").value.trim();
    try {
        // Save bot token if provided
        if (newToken) {
            const tr = await fetch("/api/bot/setup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: newToken }),
            });
            if (!tr.ok) {
                const err = await tr.json();
                settingsMsg.textContent = "Token error: " + (err.error || "Failed");
                settingsMsg.className = "editor-msg error";
                return;
            }
        }
        const r = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ollama_base_url: document.getElementById("settings-ollama-url").value,
                inbox: document.getElementById("settings-inbox").value,
                tasks: document.getElementById("settings-tasks").value,
                daily_dir: document.getElementById("settings-daily-dir").value,
                projects_dir: document.getElementById("settings-projects-dir").value,
                assets_dir: document.getElementById("settings-assets-dir").value,
                bot_allowed_chat_ids: ids,
            }),
        });
        if (r.ok) {
            settingsMsg.textContent = newToken ? "Settings & token saved" : "Settings saved";
            settingsMsg.className = "editor-msg success";
            document.getElementById("settings-bot-token").value = "";
            if (newToken) await fetchBotStatus();
        }
    } catch (e) {
        settingsMsg.textContent = "Error: " + e.message;
        settingsMsg.className = "editor-msg error";
    }
});

settingsClose.addEventListener("click", () => { settingsModal.style.display = "none"; });
settingsModal.addEventListener("click", (e) => { if (e.target === settingsModal) settingsModal.style.display = "none"; });

// ── Session Resume ───────────────────────────────────

async function loadSessionDetail(sessionId) {
    try {
        // Send resume request over WebSocket
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "load_session", session_id: sessionId }));
            modalSessions.style.display = "none";
        }
    } catch (e) {
        addErrorMsg(`Failed to load session: ${e.message}`);
    }
}

// ── Wiki Knowledge Base ────────────────────────────────

const wikiModal = document.getElementById("modal-wiki");
const wikiCloseBtn = document.getElementById("wiki-close");
const wikiInitBtn = document.getElementById("wiki-init-btn");
const wikiGraphCanvas = document.getElementById("wiki-graph-canvas");
const wikiGraphEmpty = document.getElementById("wiki-graph-empty");
const wikiGraphLegend = document.getElementById("wiki-graph-legend");
const wikiPageList = document.getElementById("wiki-page-list");
const wikiStatusBar = document.getElementById("wiki-status-bar");
const wikiPageHeader = document.getElementById("wiki-page-header");
const wikiPageContent = document.getElementById("wiki-page-content");
const wikiGraphResetBtn = document.getElementById("wiki-graph-reset");
const statWikiBlock = document.getElementById("stat-wiki-block");

// Wiki tab switching
document.querySelectorAll(".wiki-tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".wiki-tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".wiki-tab-content").forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById("wiki-tab-" + tab.dataset.tab).classList.add("active");
        if (tab.dataset.tab === "graph") wikiRenderGraph();
    });
});

wikiCloseBtn.addEventListener("click", () => { wikiModal.style.display = "none"; });
wikiModal.addEventListener("click", (e) => { if (e.target === wikiModal) wikiModal.style.display = "none"; });

wikiInitBtn.addEventListener("click", async () => {
    wikiInitBtn.disabled = true;
    wikiInitBtn.textContent = "INIT...";
    try {
        await fetch("/api/wiki/init", { method: "POST" });
        openWikiModal();
    } finally {
        wikiInitBtn.disabled = false;
        wikiInitBtn.textContent = "INIT";
    }
});

// Wiki stat block click
statWikiBlock.addEventListener("click", () => openWikiModal());

async function refreshWikiStatus() {
    try {
        const r = await fetch("/api/wiki/status");
        const data = await r.json();
        const val = document.getElementById("stat-wiki");
        if (data.exists) {
            val.textContent = data.page_count;
        } else {
            val.textContent = "—";
        }
    } catch { }
}

async function openWikiModal() {
    wikiModal.style.display = "flex";
    // Check status
    const r = await fetch("/api/wiki/status");
    const status = await r.json();
    if (!status.exists) {
        wikiInitBtn.style.display = "";
        wikiGraphEmpty.style.display = "";
        wikiGraphEmpty.textContent = "Wiki 尚未初始化。點擊 INIT 開始。";
        wikiPageList.innerHTML = "";
        wikiStatusBar.textContent = "";
        return;
    }
    wikiInitBtn.style.display = "none";
    wikiGraphEmpty.style.display = "none";

    // Load pages
    const pr = await fetch("/api/wiki/pages");
    const pagesData = await pr.json();
    wikiRenderPageList(pagesData.pages || []);
    wikiStatusBar.textContent = `${(pagesData.pages || []).length} pages`;

    // Render graph
    wikiRenderGraph();
    refreshWikiStatus();
}

function wikiRenderPageList(pages) {
    wikiPageList.innerHTML = "";
    if (pages.length === 0) {
        wikiPageList.innerHTML = '<div style="color:var(--text-lo);text-align:center;padding:24px">No pages yet. Ingest sources with CLI.</div>';
        return;
    }
    const catIcons = { summaries: "📝", entities: "🏷️", concepts: "💡", comparisons: "⚖️", root: "📄" };
    for (const p of pages) {
        const cat = p.includes("/") ? p.split("/")[0] : "root";
        const name = p.split("/").pop().replace(".md", "").replace(/-/g, " ");
        const el = document.createElement("div");
        el.className = "wiki-page-item";
        el.innerHTML = `
            <span class="wiki-page-item-icon">${catIcons[cat] || "📄"}</span>
            <span class="wiki-page-item-name">${escapeHtml(name)}</span>
            <span class="wiki-page-item-cat">${escapeHtml(cat)}</span>
        `;
        el.addEventListener("click", () => wikiOpenPage(p));
        wikiPageList.appendChild(el);
    }
}

// ── Force-directed Graph ────────────────────────────

const WIKI_GRAPH_COLORS = {
    summaries: "#00E5FF",
    entities: "#FFB000",
    concepts: "#00FF88",
    comparisons: "#FF6B6B",
    root: "#7EB8C9",
    unknown: "#555",
};

let wikiGraphData = null;
let wikiGraphSim = null;
let wikiGraphTransform = { x: 0, y: 0, scale: 1 };
let wikiGraphDrag = null;
let wikiGraphHover = null;
let wikiGraphSelected = null;

async function wikiRenderGraph() {
    const canvas = wikiGraphCanvas;
    const ctx = canvas.getContext("2d");
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * devicePixelRatio;
    canvas.height = rect.height * devicePixelRatio;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    ctx.scale(devicePixelRatio, devicePixelRatio);

    // Remove old tooltip if any
    let tooltip = document.getElementById("wiki-graph-tooltip");
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "wiki-graph-tooltip";
        tooltip.className = "wiki-graph-tooltip";
        canvas.parentElement.appendChild(tooltip);
    }
    tooltip.style.display = "none";

    // Fetch graph data
    try {
        const r = await fetch("/api/wiki/graph");
        wikiGraphData = await r.json();
    } catch {
        wikiGraphEmpty.style.display = "";
        wikiGraphEmpty.textContent = "Failed to load graph data.";
        return;
    }

    const nodes = wikiGraphData.nodes;
    const links = wikiGraphData.links;

    if (nodes.length === 0) {
        wikiGraphEmpty.style.display = "";
        return;
    }
    wikiGraphEmpty.style.display = "none";

    // Compute degree (connection count) for each node
    const degree = {};
    for (const n of nodes) degree[n.id] = 0;
    for (const link of links) {
        degree[link.source] = (degree[link.source] || 0) + 1;
        degree[link.target] = (degree[link.target] || 0) + 1;
    }
    const maxDegree = Math.max(1, ...Object.values(degree));

    // Build adjacency sets for neighbor highlighting
    const neighbors = {};
    for (const n of nodes) neighbors[n.id] = new Set();
    for (const link of links) {
        neighbors[link.source].add(link.target);
        neighbors[link.target].add(link.source);
    }

    // Render legend
    const cats = [...new Set(nodes.map(n => n.category))];
    wikiGraphLegend.innerHTML = cats.map(c =>
        `<span class="wiki-graph-legend-item"><span class="wiki-graph-legend-dot" style="background:${WIKI_GRAPH_COLORS[c] || WIKI_GRAPH_COLORS.unknown}"></span>${c}</span>`
    ).join("");

    // Initialize positions (circular layout)
    const W = rect.width, H = rect.height;
    const cx = W / 2, cy = H / 2;
    nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length;
        const radius = Math.min(W, H) * 0.3;
        n.x = cx + radius * Math.cos(angle);
        n.y = cy + radius * Math.sin(angle);
        n.vx = 0;
        n.vy = 0;
    });

    // Build node lookup
    const nodeMap = {};
    nodes.forEach(n => nodeMap[n.id] = n);

    // Reset transform & selection
    wikiGraphTransform = { x: 0, y: 0, scale: 1 };
    wikiGraphSelected = null;

    // Node radius based on degree
    function nodeRadius(n) {
        const deg = degree[n.id] || 0;
        return 4 + (deg / maxDegree) * 10; // 4px min, 14px max
    }

    // Force simulation
    function simulate() {
        const alpha = 0.3;
        const repulsion = 2500;
        const attraction = 0.005;
        const centerPull = 0.01;
        const damping = 0.85;

        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = nodes[i], b = nodes[j];
                let dx = b.x - a.x, dy = b.y - a.y;
                let dist = Math.sqrt(dx * dx + dy * dy) || 1;
                let force = repulsion / (dist * dist);
                let fx = (dx / dist) * force;
                let fy = (dy / dist) * force;
                a.vx -= fx * alpha; a.vy -= fy * alpha;
                b.vx += fx * alpha; b.vy += fy * alpha;
            }
        }

        for (const link of links) {
            const a = nodeMap[link.source], b = nodeMap[link.target];
            if (!a || !b) continue;
            let dx = b.x - a.x, dy = b.y - a.y;
            let dist = Math.sqrt(dx * dx + dy * dy) || 1;
            let force = (dist - 140) * attraction;
            let fx = (dx / dist) * force;
            let fy = (dy / dist) * force;
            a.vx += fx; a.vy += fy;
            b.vx -= fx; b.vy -= fy;
        }

        for (const n of nodes) {
            n.vx += (cx - n.x) * centerPull;
            n.vy += (cy - n.y) * centerPull;
        }

        for (const n of nodes) {
            if (n === wikiGraphDrag) continue;
            n.vx *= damping; n.vy *= damping;
            n.x += n.vx; n.y += n.vy;
        }
    }

    function draw() {
        ctx.clearRect(0, 0, rect.width, rect.height);
        ctx.save();
        ctx.translate(wikiGraphTransform.x, wikiGraphTransform.y);
        ctx.scale(wikiGraphTransform.scale, wikiGraphTransform.scale);

        // Determine focus node (hover takes priority over selected)
        const focusNode = wikiGraphHover || wikiGraphSelected;
        const focusNeighbors = focusNode ? neighbors[focusNode.id] : null;

        // Draw links — two passes: dim first, then highlighted on top
        for (const link of links) {
            const a = nodeMap[link.source], b = nodeMap[link.target];
            if (!a || !b) continue;

            let isHighlighted = false;
            if (focusNode) {
                isHighlighted = (link.source === focusNode.id || link.target === focusNode.id);
            }

            if (focusNode && isHighlighted) continue; // draw highlighted links in second pass

            ctx.lineWidth = focusNode ? 0.3 : 0.8;
            ctx.strokeStyle = focusNode ? "rgba(0, 229, 255, 0.06)" : "rgba(0, 229, 255, 0.25)";
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
        }

        // Second pass: highlighted links
        if (focusNode) {
            for (const link of links) {
                const a = nodeMap[link.source], b = nodeMap[link.target];
                if (!a || !b) continue;
                if (link.source !== focusNode.id && link.target !== focusNode.id) continue;

                ctx.lineWidth = 1.5;
                ctx.strokeStyle = "rgba(0, 229, 255, 0.7)";
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.stroke();
            }
        }

        // Draw nodes
        for (const n of nodes) {
            const color = WIKI_GRAPH_COLORS[n.category] || WIKI_GRAPH_COLORS.unknown;
            const isHover = wikiGraphHover === n;
            const isSelected = wikiGraphSelected === n;
            const isFocused = isHover || isSelected;
            const isNeighbor = focusNode && focusNeighbors && focusNeighbors.has(n.id);
            const isDimmed = focusNode && !isFocused && !isNeighbor;
            const r = nodeRadius(n);
            const drawR = isFocused ? r + 3 : r;

            // Glow for focused/selected
            if (isFocused) {
                ctx.shadowColor = color;
                ctx.shadowBlur = 20;
            }

            ctx.globalAlpha = isDimmed ? 0.15 : 1;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x, n.y, drawR, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowBlur = 0;

            // Selection ring
            if (isSelected) {
                ctx.strokeStyle = "#fff";
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.arc(n.x, n.y, drawR + 3, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Label
            const labelAlpha = isFocused ? 1 : isNeighbor ? 0.8 : isDimmed ? 0.1 : 0.6;
            ctx.globalAlpha = labelAlpha;
            ctx.fillStyle = isFocused ? "#fff" : "rgba(224, 247, 250, 0.9)";
            ctx.font = `${isFocused ? "12" : isNeighbor ? "10" : "9"}px Rajdhani`;
            ctx.textAlign = "center";
            ctx.fillText(n.label, n.x, n.y + drawR + 14);

            ctx.globalAlpha = 1;
        }

        ctx.restore();
    }

    // Animation loop
    let animFrame;
    function tick() {
        simulate();
        draw();
        animFrame = requestAnimationFrame(tick);
    }

    if (wikiGraphSim) cancelAnimationFrame(wikiGraphSim);
    wikiGraphSim = null;
    tick();
    wikiGraphSim = animFrame;

    // Mouse interactions
    function getMousePos(e) {
        const br = canvas.getBoundingClientRect();
        return {
            x: (e.clientX - br.left - wikiGraphTransform.x) / wikiGraphTransform.scale,
            y: (e.clientY - br.top - wikiGraphTransform.y) / wikiGraphTransform.scale,
        };
    }

    function findNodeAt(mx, my) {
        // Check larger nodes first (they're on top visually)
        const sorted = [...nodes].sort((a, b) => nodeRadius(b) - nodeRadius(a));
        for (const n of sorted) {
            const dx = n.x - mx, dy = n.y - my;
            const r = nodeRadius(n) + 4; // generous hit area
            if (dx * dx + dy * dy < r * r) return n;
        }
        return null;
    }

    function showTooltip(node, e) {
        const deg = degree[node.id] || 0;
        const cat = node.category;
        const nbs = neighbors[node.id];
        const nbList = [...nbs].slice(0, 5).map(id => {
            const n = nodeMap[id];
            return n ? n.label : id.replace(".md", "");
        });
        let html = `<div class="wiki-tooltip-title">${escapeHtml(node.label)}</div>`;
        html += `<div class="wiki-tooltip-cat">${escapeHtml(cat)} · ${deg} connection${deg !== 1 ? "s" : ""}</div>`;
        if (nbList.length > 0) {
            html += `<div class="wiki-tooltip-links">${nbList.map(l => `<span>${escapeHtml(l)}</span>`).join("")}</div>`;
        }
        html += `<div class="wiki-tooltip-hint">click to open</div>`;
        tooltip.innerHTML = html;
        tooltip.style.display = "";

        const br = canvas.getBoundingClientRect();
        const tx = e.clientX - br.left + 15;
        const ty = e.clientY - br.top - 10;
        tooltip.style.left = tx + "px";
        tooltip.style.top = ty + "px";

        // Keep tooltip in bounds
        requestAnimationFrame(() => {
            const tr = tooltip.getBoundingClientRect();
            if (tx + tr.width > rect.width - 10) {
                tooltip.style.left = (tx - tr.width - 30) + "px";
            }
            if (ty + tr.height > rect.height - 10) {
                tooltip.style.top = (ty - tr.height) + "px";
            }
        });
    }

    let dragMoved = false;

    canvas.onmousedown = (e) => {
        const { x, y } = getMousePos(e);
        const node = findNodeAt(x, y);
        dragMoved = false;
        if (node) {
            wikiGraphDrag = node;
            canvas.style.cursor = "grabbing";
        } else {
            wikiGraphDrag = null;
            canvas._panStart = { x: e.clientX - wikiGraphTransform.x, y: e.clientY - wikiGraphTransform.y };
        }
    };

    canvas.onmousemove = (e) => {
        const { x, y } = getMousePos(e);
        if (wikiGraphDrag) {
            dragMoved = true;
            wikiGraphDrag.x = x;
            wikiGraphDrag.y = y;
            wikiGraphDrag.vx = 0;
            wikiGraphDrag.vy = 0;
        } else if (canvas._panStart) {
            dragMoved = true;
            wikiGraphTransform.x = e.clientX - canvas._panStart.x;
            wikiGraphTransform.y = e.clientY - canvas._panStart.y;
        } else {
            const node = findNodeAt(x, y);
            wikiGraphHover = node;
            canvas.style.cursor = node ? "pointer" : "grab";
            if (node) {
                showTooltip(node, e);
            } else {
                tooltip.style.display = "none";
            }
        }
    };

    canvas.onmouseup = (e) => {
        const wasDrag = wikiGraphDrag;
        if (wikiGraphDrag) {
            canvas.style.cursor = "grab";
            // Single click on node (no drag movement) → open page
            if (!dragMoved) {
                wikiGraphSelected = wikiGraphDrag;
                wikiOpenPage(wikiGraphDrag.id);
            }
            wikiGraphDrag = null;
        } else if (canvas._panStart) {
            canvas._panStart = null;
            // Click on empty space → deselect
            if (!dragMoved) {
                wikiGraphSelected = null;
            }
        }
    };

    canvas.ondblclick = null; // single click handles navigation now

    canvas.onmouseleave = () => {
        wikiGraphHover = null;
        tooltip.style.display = "none";
    };

    canvas.onwheel = (e) => {
        e.preventDefault();
        const br = canvas.getBoundingClientRect();
        const mx = e.clientX - br.left, my = e.clientY - br.top;
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.max(0.2, Math.min(5, wikiGraphTransform.scale * delta));
        wikiGraphTransform.x = mx - (mx - wikiGraphTransform.x) * (newScale / wikiGraphTransform.scale);
        wikiGraphTransform.y = my - (my - wikiGraphTransform.y) * (newScale / wikiGraphTransform.scale);
        wikiGraphTransform.scale = newScale;
    };

    // Reset button
    wikiGraphResetBtn.onclick = () => {
        wikiGraphTransform = { x: 0, y: 0, scale: 1 };
        wikiGraphSelected = null;
    };

    // Stop animation when modal closes
    const obs = new MutationObserver(() => {
        if (wikiModal.style.display === "none" && wikiGraphSim) {
            cancelAnimationFrame(wikiGraphSim);
            wikiGraphSim = null;
        }
    });
    obs.observe(wikiModal, { attributes: true, attributeFilter: ["style"] });
}

// ── Wiki Ingest / Lint / Page Edit ─────────────────────

const wikiIngestBtn = document.getElementById("wiki-ingest-btn");
const wikiLintBtn = document.getElementById("wiki-lint-btn");
const wikiPageEditor = document.getElementById("wiki-page-editor");
const wikiPageEditActions = document.getElementById("wiki-page-edit-actions");
const wikiPageSaveBtn = document.getElementById("wiki-page-save");
const wikiPageCancelEditBtn = document.getElementById("wiki-page-cancel-edit");
const wikiPageMsg = document.getElementById("wiki-page-msg");
let currentWikiPagePath = null;
let currentWikiPageContent = null;

// Ingest: open file browser to select a source file
wikiIngestBtn.addEventListener("click", () => {
    wikiModal.style.display = "none";
    wikiIngestFileBrowser("");
});

function wikiIngestFileBrowser(path) {
    const relPath = path || "";
    fileViewerModal.style.display = "flex";
    fileViewerTitle.textContent = "SELECT SOURCE TO INGEST";
    fileViewerBody.style.display = "";
    fileEditorTextarea.style.display = "none";
    fileEditBtn.style.display = "none";
    fileSaveBtn.style.display = "none";
    fileCancelEditBtn.style.display = "none";
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = path ? "" : "none";

    fetch(`/api/files?path=${encodeURIComponent(relPath)}`).then(r => r.json()).then(items => {
        if (items.error) {
            fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">${escapeHtml(items.error)}</div>`;
            return;
        }
        fileViewerBody.innerHTML = "";
        for (const item of items) {
            const el = document.createElement("div");
            el.className = "file-item" + (item.type === "dir" ? " dir" : "");
            el.innerHTML = `
                <span class="file-item-icon">${item.type === "dir" ? "📁" : "📄"}</span>
                <span class="file-item-name">${escapeHtml(item.name)}</span>
            `;
            el.addEventListener("click", () => {
                if (item.type === "dir") {
                    wikiIngestFileBrowser(item.path);
                } else {
                    // Selected a file to ingest
                    fileViewerModal.style.display = "none";
                    doWikiIngest(item.path);
                }
            });
            fileViewerBody.appendChild(el);
        }
    });

    // Override back/close for ingest mode
    fileViewerBack.onclick = (e) => {
        e.stopImmediatePropagation();
        const parts = relPath.split("/");
        parts.pop();
        wikiIngestFileBrowser(parts.join("/"));
    };
    fileViewerClose.onclick = (e) => {
        e.stopImmediatePropagation();
        fileViewerModal.style.display = "none";
        wikiModal.style.display = "flex";
        // Restore original handlers
        fileViewerClose.onclick = null;
        fileViewerBack.onclick = null;
    };
}

async function doWikiIngest(sourcePath) {
    wikiModal.style.display = "flex";
    addSysMsg(`Wiki ingest: ${sourcePath}...`);
    wikiIngestBtn.disabled = true;
    wikiIngestBtn.textContent = "INGESTING...";

    try {
        const r = await fetch("/api/wiki/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_path: sourcePath }),
        });
        const data = await r.json();
        if (data.ok !== false) {
            let msg = `Wiki ingest 完成: ${sourcePath}`;
            if (data.pages_created && data.pages_created.length > 0) {
                msg += `\n\n建立 ${data.pages_created.length} 頁: ${data.pages_created.join(", ")}`;
            }
            if (data.pages_updated && data.pages_updated.length > 0) {
                msg += `\n\n更新 ${data.pages_updated.length} 頁: ${data.pages_updated.join(", ")}`;
            }
            addSysMsg(msg);
            // Refresh wiki modal
            openWikiModal();
        } else {
            addErrorMsg(`Wiki ingest 失敗: ${(data.errors || []).join(", ")}`);
        }
    } catch (e) {
        addErrorMsg(`Wiki ingest error: ${e.message}`);
    } finally {
        wikiIngestBtn.disabled = false;
        wikiIngestBtn.textContent = "INGEST";
    }
}

// Lint
wikiLintBtn.addEventListener("click", async () => {
    wikiModal.style.display = "none";
    addSysMsg("Running wiki lint...");
    wikiLintBtn.disabled = true;
    wikiLintBtn.textContent = "RUNNING...";
    setAvatar("thinking");

    try {
        const r = await fetch("/api/wiki/lint", { method: "POST" });
        const data = await r.json();
        if (data.report) {
            addMessage("adjutant", data.report);
        } else {
            addErrorMsg("Wiki lint returned no report.");
        }
    } catch (e) {
        addErrorMsg(`Wiki lint error: ${e.message}`);
    } finally {
        wikiLintBtn.disabled = false;
        wikiLintBtn.textContent = "LINT";
        setAvatar("idle");
    }
});

// Wiki page editing
async function wikiOpenPage(path) {
    // Switch to page-view tab
    document.querySelectorAll(".wiki-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".wiki-tab-content").forEach(c => c.classList.remove("active"));
    document.querySelector('.wiki-tab[data-tab="page-view"]').classList.add("active");
    document.getElementById("wiki-tab-page-view").classList.add("active");

    currentWikiPagePath = path;
    currentWikiPageContent = null;
    wikiPageEditor.style.display = "none";
    wikiPageEditActions.style.display = "none";
    wikiPageMsg.textContent = "";

    const name = path.split("/").pop().replace(".md", "").replace(/-/g, " ");
    wikiPageHeader.innerHTML = `<span class="wiki-page-header-back" id="wiki-page-back">← PAGES</span> / ${escapeHtml(path)} <button class="action-btn mini" id="wiki-page-edit-btn" style="margin-left:auto">EDIT</button>`;
    wikiPageContent.innerHTML = '<div style="color:var(--text-lo);text-align:center;padding:40px">Loading...</div>';

    // Wire up back button
    document.getElementById("wiki-page-back").addEventListener("click", () => {
        document.querySelector('.wiki-tab[data-tab="pages"]').click();
    });

    try {
        const r = await fetch(`/api/wiki/page?path=${encodeURIComponent(path)}`);
        const data = await r.json();
        if (data.ok) {
            currentWikiPageContent = data.content;
            let html = renderMarkdown(data.content);
            // Make wiki links clickable
            html = html.replace(/href="([^"]*\.md)"/g, (match, href) => {
                return `href="#" onclick="wikiOpenPage('${href.replace(/'/g, "\\'")}');return false;"`;
            });
            wikiPageContent.innerHTML = `<div class="file-viewer-content">${html}</div>`;

            // Wire up edit button
            document.getElementById("wiki-page-edit-btn").addEventListener("click", () => {
                wikiPageContent.style.display = "none";
                wikiPageEditor.style.display = "";
                wikiPageEditActions.style.display = "flex";
                wikiPageEditor.value = currentWikiPageContent;
                wikiPageEditor.focus();
                document.getElementById("wiki-page-edit-btn").style.display = "none";
            });
        } else {
            wikiPageContent.innerHTML = `<div style="color:var(--danger);padding:20px">${escapeHtml(data.error)}</div>`;
        }
    } catch (e) {
        wikiPageContent.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${escapeHtml(e.message)}</div>`;
    }
}

wikiPageCancelEditBtn.addEventListener("click", () => {
    wikiPageEditor.style.display = "none";
    wikiPageEditActions.style.display = "none";
    wikiPageContent.style.display = "";
    wikiPageMsg.textContent = "";
    const editBtn = document.getElementById("wiki-page-edit-btn");
    if (editBtn) editBtn.style.display = "";
});

wikiPageSaveBtn.addEventListener("click", async () => {
    if (!currentWikiPagePath) return;
    wikiPageSaveBtn.disabled = true;
    wikiPageSaveBtn.textContent = "SAVING...";
    wikiPageMsg.textContent = "";
    try {
        const r = await fetch("/api/wiki/page", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: currentWikiPagePath, content: wikiPageEditor.value }),
        });
        const data = await r.json();
        if (data.ok) {
            currentWikiPageContent = wikiPageEditor.value;
            let html = renderMarkdown(currentWikiPageContent);
            html = html.replace(/href="([^"]*\.md)"/g, (match, href) => {
                return `href="#" onclick="wikiOpenPage('${href.replace(/'/g, "\\'")}');return false;"`;
            });
            wikiPageContent.innerHTML = `<div class="file-viewer-content">${html}</div>`;
            wikiPageEditor.style.display = "none";
            wikiPageEditActions.style.display = "none";
            wikiPageContent.style.display = "";
            wikiPageMsg.textContent = "SAVED";
            wikiPageMsg.className = "editor-msg success";
            setTimeout(() => { wikiPageMsg.textContent = ""; }, 2000);
            const editBtn = document.getElementById("wiki-page-edit-btn");
            if (editBtn) editBtn.style.display = "";
        } else {
            wikiPageMsg.textContent = data.error || "Save failed";
            wikiPageMsg.className = "editor-msg error";
        }
    } catch (e) {
        wikiPageMsg.textContent = "Error: " + e.message;
        wikiPageMsg.className = "editor-msg error";
    } finally {
        wikiPageSaveBtn.disabled = false;
        wikiPageSaveBtn.textContent = "SAVE";
    }
});

// ── Init ─────────────────────────────────────────────

setAvatar("idle");
connect();
fetchBotStatus();
refreshWikiStatus();
