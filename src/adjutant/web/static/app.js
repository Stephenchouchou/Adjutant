/* Adjutant Command Center — Client */

const feed = document.getElementById("briefing-text");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnSend = document.getElementById("btn-send");
const btnCancel = document.getElementById("btn-cancel");
const statusText = document.getElementById("status-text");
const statusDot = document.getElementById("status-dot");
const uplinkStatus = document.getElementById("uplink-status");
const modeBar = document.getElementById("mode-bar");
const avatar = document.getElementById("adjutant-portrait");
const indicator = document.getElementById("terminal-indicator");
const imageBar = document.getElementById("image-bar");
const clockEl = document.getElementById("clock");

let ws = null;
let streaming = false;
let currentContent = null;
let pendingImages = [];

// ── Clock ────────────────────────────────────────────

function updateClock() {
    const now = new Date();
    clockEl.textContent = now.toTimeString().slice(0, 8);
}
setInterval(updateClock, 1000);
updateClock();

function timestamp() {
    return new Date().toTimeString().slice(0, 8);
}

// ── WebSocket ────────────────────────────────────────

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("ONLINE", "online");
        uplinkStatus.textContent = "ACTIVE";
        uplinkStatus.className = "status-value uplink online";
    };

    ws.onclose = () => {
        setStatus("DISCONNECTED", "error");
        setAvatar("idle");
        uplinkStatus.textContent = "LOST";
        uplinkStatus.className = "status-value uplink error";
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        setStatus("COMM ERROR", "error");
    };

    ws.onmessage = (event) => {
        handleMessage(JSON.parse(event.data));
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case "init":
            renderModules(msg.sops);
            setStatus("AWAITING ORDERS", "online");
            break;

        case "stream_start":
            streaming = true;
            updateButtons();
            setAvatar("active");
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
            if (currentContent) currentContent.classList.remove("streaming");
            currentContent = null;
            setStatus("AWAITING ORDERS", "online");
            setModulesDisabled(false);
            break;

        case "sop_start":
            addSysMsg(`EXECUTING: ${msg.label.toUpperCase()}`);
            streaming = true;
            updateButtons();
            setAvatar("active");
            setStatus(`SOP: ${msg.label.toUpperCase()}`, "online");
            setIndicator("PROCESSING...");
            currentContent = addMessage("adjutant", "");
            currentContent.classList.add("streaming");
            break;

        case "sop_file_confirm":
            showFileConfirm(msg.path, msg.content);
            break;

        case "file_written":
            addSysMsg(`FILE WRITTEN: ${msg.path}`);
            break;

        case "error":
            addErrorMsg(msg.data);
            streaming = false;
            updateButtons();
            setAvatar("idle");
            setIndicator("");
            setStatus("ERROR", "error");
            setModulesDisabled(false);
            break;

        case "cancelled":
            streaming = false;
            updateButtons();
            setAvatar("idle");
            setIndicator("");
            if (currentContent) {
                currentContent.classList.remove("streaming");
                currentContent.textContent += "\n\n[TRANSMISSION ABORTED]";
            }
            currentContent = null;
            setStatus("AWAITING ORDERS", "online");
            setModulesDisabled(false);
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
    avatar.className = "ai-avatar" + (state === "active" ? " active" : "");
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

function setModulesDisabled(disabled) {
    modeBar.querySelectorAll(".module-btn").forEach(btn => {
        btn.disabled = disabled;
        if (!disabled) btn.classList.remove("running");
    });
}

// ── Terminal Feed ────────────────────────────────────

function clearWelcome() {
    const w = feed.querySelector(".welcome-screen");
    if (w) w.remove();
}

function addMessage(role, text, imagePaths) {
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
    body.textContent = text;

    msg.appendChild(body);
    feed.appendChild(msg);
    scrollToBottom();

    return body;
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
        <button class="action-btn execute">WRITE</button>
        <button class="action-btn">SKIP</button>
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

// ── Left Panel Modules ───────────────────────────────

function renderModules(sops) {
    modeBar.innerHTML = "";
    for (const sop of sops) {
        const btn = document.createElement("button");
        btn.className = "module-btn";
        btn.innerHTML = `<span class="module-icon">${sop.icon}</span><span class="module-label">${escapeHtml(sop.label)}</span>`;
        btn.title = sop.description;
        btn.addEventListener("click", () => {
            if (streaming) return;
            btn.classList.add("running");
            setModulesDisabled(true);
            btn.disabled = false;
            runSop(sop.key);
        });
        modeBar.appendChild(btn);
    }
}

// ── Actions ──────────────────────────────────────────

function sendMessage(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!text.trim() && pendingImages.length === 0) return;

    const imagePaths = pendingImages.filter(i => i.path).map(i => i.path);
    addMessage("user", text, imagePaths);
    setStatus("PROCESSING...", "online");
    setAvatar("active");
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

// Paste
document.addEventListener("paste", (e) => {
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

btnSessions.addEventListener("click", async () => {
    modalSessions.style.display = "flex";
    sessionsList.innerHTML = '<div style="color:var(--text-lo);padding:20px;text-align:center">Loading...</div>';
    try {
        const resp = await fetch("/api/sessions");
        const sessions = await resp.json();
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
    } catch (e) {
        sessionsList.innerHTML = `<div style="color:var(--danger);padding:20px">Error: ${e.message}</div>`;
    }
});

async function loadSessionDetail(sessionId) {
    try {
        const resp = await fetch(`/api/sessions/${sessionId}`);
        const session = await resp.json();
        modalSessions.style.display = "none";
        feed.innerHTML = "";
        addSysMsg(`ARCHIVE: ${session.name || "Unnamed"} -- ${new Date(session.created).toLocaleString()}`);
        for (const msg of session.messages) {
            addMessage(msg.role === "user" ? "user" : "adjutant", msg.content);
        }
        addSysMsg("-- END OF ARCHIVED SESSION --");
    } catch (e) {
        addErrorMsg(`Failed to load session: ${e.message}`);
    }
}

// Modal close
document.getElementById("modal-close-btn").addEventListener("click", () => {
    modalSessions.style.display = "none";
});

modalSessions.addEventListener("click", (e) => {
    if (e.target === modalSessions) modalSessions.style.display = "none";
});

// ── Init ─────────────────────────────────────────────

setAvatar("idle");
connect();
