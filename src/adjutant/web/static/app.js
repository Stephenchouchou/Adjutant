/* Adjutant Web UI — Briefing Room Client */

const briefingText = document.getElementById("briefing-text");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnSend = document.getElementById("btn-send");
const btnCancel = document.getElementById("btn-cancel");
const statusText = document.getElementById("status-text");
const statusContent = statusText.parentElement;
const modeBar = document.getElementById("mode-bar");
const portrait = document.getElementById("adjutant-portrait");

let ws = null;
let streaming = false;
let currentContent = null;
let pendingImages = [];

const imageBar = document.getElementById("image-bar");

// ── WebSocket ────────────────────────────────────────

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("ONLINE", "online");
    };

    ws.onclose = () => {
        setStatus("DISCONNECTED", "error");
        setPortrait("idle");
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        setStatus("COMM ERROR", "error");
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case "init":
            renderModeBar(msg.sops);
            setStatus("AWAITING ORDERS", "online");
            break;

        case "stream_start":
            streaming = true;
            updateButtons();
            setPortrait("active");
            currentContent = addEntry("adjutant", "");
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
            setPortrait("idle");
            if (currentContent) {
                currentContent.classList.remove("streaming");
            }
            currentContent = null;
            setStatus("AWAITING ORDERS", "online");
            setSopDisabled(false);
            break;

        case "sop_start":
            addSystemMsg(`${msg.icon} ${msg.label}`);
            streaming = true;
            updateButtons();
            setPortrait("active");
            setStatus(`SOP: ${msg.label.toUpperCase()}`, "online");
            currentContent = addEntry("adjutant", "");
            currentContent.classList.add("streaming");
            break;

        case "sop_file_confirm":
            showFileConfirm(msg.path, msg.content);
            break;

        case "file_written":
            addSystemMsg(`FILE WRITTEN: ${msg.path}`);
            break;

        case "error":
            addError(msg.data);
            streaming = false;
            updateButtons();
            setPortrait("idle");
            setStatus("ERROR", "error");
            setSopDisabled(false);
            break;

        case "cancelled":
            streaming = false;
            updateButtons();
            setPortrait("idle");
            if (currentContent) {
                currentContent.classList.remove("streaming");
                currentContent.textContent += "\n\n[TRANSMISSION CANCELLED]";
            }
            currentContent = null;
            setStatus("AWAITING ORDERS", "online");
            setSopDisabled(false);
            break;
    }
}

// ── UI Helpers ───────────────────────────────────────

function setStatus(text, state) {
    statusText.textContent = text;
    statusContent.className = "status-content" + (state ? " " + state : "");
}

function setPortrait(state) {
    portrait.className = "adjutant-portrait " + state;
}

function updateButtons() {
    btnSend.style.display = streaming ? "none" : "";
    btnCancel.style.display = streaming ? "" : "none";
    chatInput.disabled = streaming;
}

function setSopDisabled(disabled) {
    modeBar.querySelectorAll(".mode-pill").forEach((btn) => {
        btn.disabled = disabled;
        if (!disabled) btn.classList.remove("running");
    });
}

function clearWelcome() {
    const welcome = briefingText.querySelector(".welcome");
    if (welcome) welcome.remove();
}

function addEntry(role, text, imagePaths) {
    clearWelcome();

    const entry = document.createElement("div");
    entry.className = "briefing-entry";

    const speaker = document.createElement("div");
    speaker.className = `briefing-speaker ${role}`;
    speaker.textContent = role === "user" ? "COMMANDER" : "ADJUTANT";

    const content = document.createElement("div");
    content.className = "briefing-content";
    content.textContent = text;

    entry.appendChild(speaker);

    if (imagePaths && imagePaths.length > 0) {
        const imgDiv = document.createElement("div");
        imgDiv.className = "briefing-images";
        for (const p of imagePaths) {
            const tag = document.createElement("span");
            tag.className = "briefing-image-tag";
            tag.textContent = p.split("/").pop();
            imgDiv.appendChild(tag);
        }
        entry.appendChild(imgDiv);
    }

    entry.appendChild(content);
    briefingText.appendChild(entry);
    scrollToBottom();

    return content;
}

function addSystemMsg(text) {
    clearWelcome();
    const div = document.createElement("div");
    div.className = "briefing-system";
    div.textContent = text;
    briefingText.appendChild(div);
    scrollToBottom();
}

function addError(text) {
    const div = document.createElement("div");
    div.className = "briefing-error";
    div.textContent = `ERROR: ${text}`;
    briefingText.appendChild(div);
    scrollToBottom();
}

function showFileConfirm(path, content) {
    const bar = document.createElement("div");
    bar.className = "file-confirm";
    bar.innerHTML = `
        <span>Write output to <strong>${path}</strong>?</span>
        <button class="cmd-btn transmit" id="fc-yes">Write</button>
        <button class="cmd-btn" id="fc-no">Skip</button>
    `;
    briefingText.appendChild(bar);
    scrollToBottom();

    bar.querySelector("#fc-yes").addEventListener("click", () => {
        ws.send(JSON.stringify({ type: "sop_file_write", path, content }));
        bar.remove();
    });
    bar.querySelector("#fc-no").addEventListener("click", () => {
        addSystemMsg("FILE WRITE SKIPPED");
        bar.remove();
    });
}

function scrollToBottom() {
    briefingText.scrollTop = briefingText.scrollHeight;
}

function renderModeBar(sops) {
    modeBar.innerHTML = "";
    for (const sop of sops) {
        const btn = document.createElement("button");
        btn.className = "mode-pill";
        btn.textContent = `${sop.icon} ${sop.label}`;
        btn.title = sop.description;
        btn.addEventListener("click", () => {
            if (streaming) return;
            btn.classList.add("running");
            setSopDisabled(true);
            btn.disabled = false; // Keep clicked one visible
            runSop(sop.key);
        });
        modeBar.appendChild(btn);
    }
}

// ── Image Handling ──────────────────────────────────

function renderImageBar() {
    if (pendingImages.length === 0) {
        imageBar.innerHTML = "";
        imageBar.classList.remove("active");
        return;
    }
    imageBar.classList.add("active");
    imageBar.innerHTML = pendingImages.map((img, i) => `
        <span class="image-tag">
            ${img.name}
            <span class="image-remove" data-idx="${i}">&times;</span>
        </span>
    `).join("");
    imageBar.querySelectorAll(".image-remove").forEach(el => {
        el.addEventListener("click", () => removeImage(parseInt(el.dataset.idx)));
    });
}

function removeImage(idx) {
    pendingImages.splice(idx, 1);
    renderImageBar();
}

async function uploadImage(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = async () => {
            const base64 = reader.result.split(",")[1];
            try {
                const resp = await fetch("/api/upload", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ data: base64, filename: file.name }),
                });
                const result = await resp.json();
                if (result.error) {
                    addError(result.error);
                    reject(new Error(result.error));
                } else {
                    resolve(result.path);
                }
            } catch (e) {
                addError(`Upload failed: ${e.message}`);
                reject(e);
            }
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

// ── Actions ──────────────────────────────────────────

function sendMessage(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!text.trim() && pendingImages.length === 0) return;

    const imagePaths = pendingImages.filter(i => i.path).map(i => i.path);
    addEntry("user", text, imagePaths);
    setStatus("PROCESSING...", "online");
    setPortrait("active");

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

// Auto-resize textarea
chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 60) + "px";
});

// Shift+Enter for newline, Enter to send
chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});

// ── Image Paste / Drop ──────────────────────────────

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

const briefingPanel = document.querySelector(".briefing-panel");

briefingPanel.addEventListener("dragover", (e) => {
    e.preventDefault();
    briefingPanel.classList.add("drag-over");
});

briefingPanel.addEventListener("dragleave", () => {
    briefingPanel.classList.remove("drag-over");
});

briefingPanel.addEventListener("drop", (e) => {
    e.preventDefault();
    briefingPanel.classList.remove("drag-over");
    const files = [...e.dataTransfer.files].filter(f => f.type.startsWith("image/"));
    if (files.length > 0) addImageFiles(files);
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && pendingImages.length > 0) {
        pendingImages = [];
        renderImageBar();
    }
});

// ── Session History ──────────────────────────────────

const btnSessions = document.getElementById("btn-sessions");
const modalSessions = document.getElementById("modal-sessions");
const sessionsList = document.getElementById("sessions-list");

btnSessions.addEventListener("click", async () => {
    modalSessions.style.display = "flex";
    sessionsList.innerHTML = '<div style="color:var(--text-dim)">Loading...</div>';
    try {
        const resp = await fetch("/api/sessions");
        const sessions = await resp.json();
        if (sessions.length === 0) {
            sessionsList.innerHTML = '<div style="color:var(--text-dim)">No saved sessions</div>';
            return;
        }
        sessionsList.innerHTML = sessions.map(s => `
            <div class="session-item" data-id="${s.id}">
                <div class="session-name">${s.name || "Unnamed"}</div>
                <div class="session-meta">${s.message_count} messages &middot; ${new Date(s.created).toLocaleString()}</div>
            </div>
        `).join("");

        sessionsList.querySelectorAll(".session-item").forEach(el => {
            el.addEventListener("click", () => loadSessionDetail(el.dataset.id));
        });
    } catch (e) {
        sessionsList.innerHTML = `<div style="color:var(--text-error)">Error: ${e.message}</div>`;
    }
});

async function loadSessionDetail(sessionId) {
    try {
        const resp = await fetch(`/api/sessions/${sessionId}`);
        const session = await resp.json();
        modalSessions.style.display = "none";

        // Render historical messages
        briefingText.innerHTML = "";
        addSystemMsg(`SESSION: ${session.name || "Unnamed"} — ${new Date(session.created).toLocaleString()}`);
        for (const msg of session.messages) {
            addEntry(msg.role === "user" ? "user" : "adjutant", msg.content);
        }
        addSystemMsg("— END OF HISTORICAL SESSION —");
    } catch (e) {
        addError(`Failed to load session: ${e.message}`);
    }
}

// Modal close handlers
document.querySelectorAll(".modal-close").forEach(btn => {
    btn.addEventListener("click", () => {
        const modal = document.getElementById(btn.dataset.modal);
        if (modal) modal.style.display = "none";
    });
});

document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.style.display = "none";
    });
});

// ── Init ─────────────────────────────────────────────

setPortrait("idle");
connect();
