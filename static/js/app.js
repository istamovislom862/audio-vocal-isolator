/**
 * Audio Vocal & Voice Isolator — Frontend Logic
 *
 * Handles: drag-and-drop upload, status polling, player rendering.
 */

const API = {
  separate: "/api/separate",
  status: (id) => `/api/status/${id}`,
  audio: (id, track) => `/api/audio/${id}/${track}`,
};

const MAX_SIZE_MB = 200;
const POLL_INTERVAL_MS = 2000;
const ALLOWED_EXTS = [".mp3", ".wav", ".ogg", ".m4a"];

// ── DOM refs ────────────────────────────────────────────────────────────
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const browseBtn = document.getElementById("browse-btn");
const statusSection = document.getElementById("status-section");
const statusText = document.getElementById("status-text");
const progressBar = document.getElementById("progress-bar");
const progressFill = document.getElementById("progress-fill");
const resultsSection = document.getElementById("results-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const newUploadBtn = document.getElementById("new-upload-btn");
const etaValue = document.getElementById("eta-value");
const progressPercent = document.getElementById("progress-percent");

// ── State ───────────────────────────────────────────────────────────────
let pollTimer = null;

// ── Helpers ─────────────────────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function validateFile(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_EXTS.includes(ext)) {
    return `Noto'g'ri format (${ext}). Ruxsat: ${ALLOWED_EXTS.join(", ")}`;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `Fayl hajmi ${MAX_SIZE_MB}MB dan oshmasligi kerak.`;
  }
  return null;
}

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

// ── Drag & Drop ─────────────────────────────────────────────────────────
["dragenter", "dragover"].forEach((e) =>
  dropZone.addEventListener(e, (ev) => {
    ev.preventDefault();
    dropZone.classList.add("drag-over");
  })
);

["dragleave", "drop"].forEach((e) =>
  dropZone.addEventListener(e, (ev) => {
    ev.preventDefault();
    dropZone.classList.remove("drag-over");
  })
);

dropZone.addEventListener("drop", (ev) => {
  const file = ev.dataTransfer.files[0];
  if (file) handleFile(file);
});

browseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

newUploadBtn.addEventListener("click", resetUI);

// ── Upload flow ─────────────────────────────────────────────────────────
async function handleFile(file) {
  const err = validateFile(file);
  if (err) return showError(err);

  // Show file info
  fileName.textContent = file.name;
  fileSize.textContent = formatSize(file.size);
  show(fileInfo);
  hide(errorSection);
  hide(resultsSection);

  // Show status
  show(statusSection);
  statusText.textContent = "Yuklanmoqda…";
  show(progressBar);
  progressFill.style.width = "0%";
  progressFill.classList.add("animate-pulse");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(API.separate, { method: "POST", body: formData });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Server xatosi (${res.status})`);
    }

    const data = await res.json();
    progressFill.style.width = "30%";
    statusText.textContent = "Navbatda…";
    startPolling(data.task_id);
  } catch (e) {
    showError(e.message);
    hide(statusSection);
  }
}

// ── Polling ─────────────────────────────────────────────────────────────
function startPolling(taskId) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(API.status(taskId));
      const data = await res.json();

      switch (data.status) {
        case "QUEUED":
          statusText.textContent = "Navbatda kutilmoqda…";
          progressFill.style.width = "5%";
          if (etaValue) etaValue.textContent = "Navbat kutilmoqda...";
          if (progressPercent) progressPercent.textContent = "0%";
          break;

        case "PROCESSING":
          statusText.textContent = "Audio ajratilmoqda… (Demucs GPU)";
          const pct = data.progress !== undefined ? data.progress : 15;
          progressFill.style.width = `${pct}%`;
          if (progressPercent) progressPercent.textContent = `${pct}%`;
          if (etaValue) etaValue.textContent = data.eta || "Hisoblanmoqda...";
          break;

        case "COMPLETED":
          clearInterval(pollTimer);
          pollTimer = null;
          progressFill.style.width = "100%";
          if (progressPercent) progressPercent.textContent = "100%";
          if (etaValue) etaValue.textContent = "0 soniya (Tayyor!)";
          progressFill.classList.remove("animate-pulse");
          statusText.textContent = "Tayyor! ✓";
          setTimeout(() => renderResults(taskId, data), 600);
          break;

        case "FAILED":
          clearInterval(pollTimer);
          pollTimer = null;
          hide(statusSection);
          showError(data.error || "Noma'lum xatolik yuz berdi.");
          break;
      }
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, POLL_INTERVAL_MS);
}

// ── Results ─────────────────────────────────────────────────────────────
function renderResults(taskId, data) {
  hide(statusSection);
  show(resultsSection);

  const tracks = [
    {
      id: "original",
      label: "🎵 Asl audio (Original)",
      url: API.audio(taskId, "original"),
      color: "from-blue-500 to-blue-600",
      iconBg: "bg-blue-500/10",
      iconColor: "text-blue-400",
    },
    {
      id: "vocals",
      label: "🎤 Ajratilgan ovoz (Vocals)",
      url: data.tracks.vocals,
      color: "from-emerald-500 to-emerald-600",
      iconBg: "bg-emerald-500/10",
      iconColor: "text-emerald-400",
    },
    {
      id: "no_vocals",
      label: "🎸 Fon musiqa (Instrumental)",
      url: data.tracks.no_vocals,
      color: "from-purple-500 to-purple-600",
      iconBg: "bg-purple-500/10",
      iconColor: "text-purple-400",
    },
  ];

  const container = document.getElementById("players-container");
  container.innerHTML = "";

  tracks.forEach((t) => {
    const card = document.createElement("div");
    card.className =
      "bg-gray-800/60 backdrop-blur rounded-2xl p-6 border border-gray-700/50 hover:border-gray-600/50 transition-all duration-300";
    card.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl ${t.iconBg} flex items-center justify-center">
            <span class="text-lg">${t.label.split(" ")[0]}</span>
          </div>
          <h3 class="text-white font-semibold">${t.label.slice(t.label.indexOf(" ") + 1)}</h3>
        </div>
        <a href="${t.url}?download=1" download
           class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r ${t.color} text-white text-sm font-medium hover:shadow-lg hover:scale-105 transition-all duration-200">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
          </svg>
          Yuklab olish
        </a>
      </div>
      <audio controls preload="metadata" class="w-full rounded-lg accent-player" src="${t.url}"></audio>
    `;
    container.appendChild(card);
  });
}

// ── Error ───────────────────────────────────────────────────────────────
function showError(msg) {
  show(errorSection);
  errorText.textContent = msg;
}

// ── Reset ───────────────────────────────────────────────────────────────
function resetUI() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  hide(statusSection);
  hide(resultsSection);
  hide(errorSection);
  hide(fileInfo);
  fileInput.value = "";
  progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
  if (etaValue) etaValue.textContent = "Hisoblanmoqda...";
  progressFill.classList.remove("animate-pulse");
}
