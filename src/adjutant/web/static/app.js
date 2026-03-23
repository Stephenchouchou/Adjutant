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
const statDaily = document.getElementById("stat-daily");
const statNotes = document.getElementById("stat-notes");

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
const popupDaily = document.getElementById("popup-daily");

let currentStats = null;

function updateStats(stats) {
    if (!stats) return;
    currentStats = stats;

    statInbox.textContent = stats.inbox_count;
    statInbox.className = "stat-value" + (stats.inbox_count > 0 ? " warn" : "");

    statTasks.textContent = stats.task_count;
    statTasks.className = "stat-value" + (stats.task_count > 5 ? " warn" : "");

    statDaily.textContent = stats.has_today_daily ? "DONE" : "NONE";
    statDaily.className = "stat-value" + (stats.has_today_daily ? " good" : " warn");

    statNotes.textContent = stats.total_notes;

    // Build popup contents
    buildPopupList(popupInbox, "INBOX", stats.inbox_items, null);
    buildPopupList(popupTasks, "OPEN TASKS", stats.task_items, null);
    buildDailyPopup(popupDaily, stats.daily_recent);
}

function buildPopupList(popup, title, items, onClick) {
    if (!items || items.length === 0) {
        popup.innerHTML = `<div class="stat-popup-header">${title}</div><div class="stat-popup-empty">Empty</div>`;
        return;
    }
    let html = `<div class="stat-popup-header">${title} (${items.length})</div>`;
    for (const item of items.slice(0, 15)) {
        html += `<div class="stat-popup-item">${escapeHtml(item)}</div>`;
    }
    if (items.length > 15) {
        html += `<div class="stat-popup-empty">+${items.length - 15} more...</div>`;
    }
    popup.innerHTML = html;
}

function buildDailyPopup(popup, dailies) {
    if (!dailies || dailies.length === 0) {
        popup.innerHTML = '<div class="stat-popup-header">DAILY NOTES</div><div class="stat-popup-empty">No daily notes found</div>';
        return;
    }
    let html = '<div class="stat-popup-header">RECENT DAILIES</div>';
    for (const d of dailies) {
        html += `<div class="stat-popup-item" data-path="${escapeHtml(d.path)}">${escapeHtml(d.name)}</div>`;
    }
    popup.innerHTML = html;

    // Click to open in file viewer
    popup.querySelectorAll("[data-path]").forEach(el => {
        el.addEventListener("click", (e) => {
            e.stopPropagation();
            closeAllPopups();
            openFileViewer(el.dataset.path);
        });
    });
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

// ── WebSocket ────────────────────────────────────────

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("ONLINE", "online");
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
            showFileConfirm(msg.path, msg.content);
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
    }
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

function showFileConfirm(path, content) {
    const bar = document.createElement("div");
    bar.className = "file-confirm";
    bar.innerHTML = `
        <span>Write output to <strong>${escapeHtml(path)}</strong>?</span>
        <button class="action-btn execute mini">WRITE</button>
        <button class="action-btn mini">SKIP</button>
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
        items.push({
            type: "sop", icon: sop.icon, label: sop.label,
            desc: sop.description, key: sop.key,
        });
    }

    items.push({ type: "action", icon: "📂", label: "Browse Files", desc: "Open notebook file browser", action: "browse" });
    items.push({ type: "action", icon: "🗂️", label: "History", desc: "Browse archived sessions", action: "history" });

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
}

function executePaletteItem(item) {
    closePalette();
    if (item.type === "sop") {
        runSop(item.key);
    } else if (item.action === "history") {
        openSessions();
    } else if (item.action === "browse") {
        openFileBrowser();
    }
}

paletteSearch.addEventListener("input", () => {
    paletteSelectedIdx = 0;
    renderPaletteItems(paletteSearch.value);
});

paletteSearch.addEventListener("keydown", (e) => {
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

function openFileBrowser(path) {
    const relPath = path || "";
    fileViewerModal.style.display = "flex";
    fileViewerTitle.textContent = relPath || "NOTEBOOK";
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = fileBrowserHistory.length > 0 ? "" : "none";

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

function openFileViewer(path) {
    fileViewerTitle.textContent = path.split("/").pop();
    fileViewerBody.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    fileViewerBack.style.display = "";

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
        fileViewerBody.innerHTML = `<div class="file-viewer-content">${renderMarkdown(result.content)}</div>`;
    }).catch(e => {
        fileViewerBody.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${escapeHtml(e.message)}</div>`;
    });
}

fileViewerBack.addEventListener("click", () => {
    if (fileBrowserHistory.length > 0) {
        const prev = fileBrowserHistory.pop();
        openFileBrowser(prev);
    }
});

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

function sendMessage(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!text.trim() && pendingImages.length === 0) return;

    const imagePaths = pendingImages.filter(i => i.path).map(i => i.path);
    addMessage("user", text, imagePaths);
    setStatus("PROCESSING", "online");
    setAvatar("thinking");
    setIndicator("TRANSMITTING...");

    ws.send(JSON.stringify({ type: "message", text, image_paths: imagePaths }));
    pendingImages = [];
    renderImageBar();
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
    }
    if (e.key === "Escape") {
        if (paletteOverlay.style.display !== "none") closePalette();
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

async function loadSessionDetail(sessionId) {
    try {
        const resp = await fetch(`/api/sessions/${sessionId}`);
        const session = await resp.json();
        modalSessions.style.display = "none";
        feed.innerHTML = "";
        addSysMsg(`ARCHIVE: ${session.name || "Unnamed"} -- ${new Date(session.created).toLocaleString()}`);
        for (const msg of session.messages) {
            addMessage(msg.role === "user" ? "user" : "adjutant", msg.content, null, true);
        }
        addSysMsg("-- END OF ARCHIVED SESSION --");
    } catch (e) {
        addErrorMsg(`Failed to load session: ${e.message}`);
    }
}

document.getElementById("modal-close-btn").addEventListener("click", () => {
    modalSessions.style.display = "none";
});

modalSessions.addEventListener("click", (e) => {
    if (e.target === modalSessions) modalSessions.style.display = "none";
});

// ── Init ─────────────────────────────────────────────

setAvatar("idle");
connect();
