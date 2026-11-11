/* Rang — frontend. Vanilla JS, no build step, no framework. */
(() => {
  "use strict";

  const API = "";
  const TOKEN_KEY = "rang.token";
  const USER_KEY = "rang.user";

  const $ = (id) => document.getElementById(id);
  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
    items: [],
    total: 0,
    offset: 0,
    limit: 24,
    favouriteOnly: false,
    query: "",
    active: null,
  };

  /* ── tiny helpers ─────────────────────────────────────── */
  function toast(msg, isError = false) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.toggle("err", isError);
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 3600);
  }

  function showError(msg) {
    const el = $("authError");
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function clearError() {
    $("authError").classList.add("hidden");
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (state.token) headers.Authorization = `Bearer ${state.token}`;

    const res = await fetch(API + path, { ...options, headers });

    if (res.status === 401 && state.token) {
      signOut();
      throw new Error("Session expired — please sign in again.");
    }
    if (res.status === 204) return null;

    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = { detail: text }; }
    }
    if (!res.ok) {
      const detail = data && data.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg || d.detail || "invalid input").join(", ")
        : detail || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }

  /* ── auth ─────────────────────────────────────────────── */
  function setSession(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function signOut() {
    state.token = "";
    state.user = null;
    state.items = [];
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    $("app").classList.add("hidden");
    $("authScreen").classList.remove("hidden");
  }

  function enterApp() {
    $("authScreen").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("userName").textContent = state.user ? state.user.display_name : "";
    loadGallery(true);
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      const which = tab.dataset.tab;
      $("loginForm").classList.toggle("hidden", which !== "login");
      $("registerForm").classList.toggle("hidden", which !== "register");
      clearError();
    });
  });

  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: fd.get("email"),
          password: fd.get("password"),
        }),
      });
      setSession(data.access_token, null);
      const me = await api("/api/auth/me");
      setSession(data.access_token, me);
      enterApp();
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const data = await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: fd.get("email"),
          display_name: fd.get("display_name"),
          password: fd.get("password"),
        }),
      });
      setSession(data.access_token, null);
      const me = await api("/api/auth/me");
      setSession(data.access_token, me);
      enterApp();
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("logoutBtn").addEventListener("click", signOut);

  /* ── composer ─────────────────────────────────────────── */
  const promptEl = $("prompt");
  const countEl = $("promptCount");

  promptEl.addEventListener("input", () => {
    countEl.textContent = promptEl.value.length;
    schedulePreview();
  });

  let previewTimer = null;
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(runPreview, 420);
  }

  async function runPreview() {
    const prompt = promptEl.value.trim();
    const box = $("previewBox");
    if (prompt.length < 3) {
      box.classList.add("hidden");
      return;
    }
    try {
      const data = await api("/api/preview", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          negative_prompt: $("negative").value,
          style: $("style").value,
          aspect_ratio: $("ratio").value,
          seed: $("seed").value ? Number($("seed").value) : null,
        }),
      });
      const chips = [
        ["palette", data.palette],
        ["subject", data.subject],
        ["style", data.style],
        ["mood", data.mood],
        ["size", data.size],
        ["seed", data.seed],
      ];
      $("previewChips").innerHTML = chips
        .map(([k, v]) => `<span class="chip">${k} <b>${escapeHtml(String(v))}</b></span>`)
        .join("");
      box.classList.remove("hidden");
    } catch {
      box.classList.add("hidden");
    }
  }

  $("genForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("genBtn");
    const label = btn.querySelector(".btn-label");
    const spinner = btn.querySelector(".spinner");
    btn.disabled = true;
    label.textContent = "Rendering…";
    spinner.classList.remove("hidden");

    try {
      const payload = {
        prompt: promptEl.value.trim(),
        negative_prompt: $("negative").value.trim(),
        style: $("style").value,
        aspect_ratio: $("ratio").value,
        seed: $("seed").value ? Number($("seed").value) : null,
      };
      const gen = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.items.unshift(gen);
      state.total += 1;
      renderGallery();
      toast(`Rendered in ${gen.render_ms} ms`);
      openLightbox(gen);
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      label.textContent = "Generate";
      spinner.classList.add("hidden");
    }
  });

  /* ── gallery ──────────────────────────────────────────── */
  async function loadGallery(reset = false) {
    if (reset) {
      state.offset = 0;
      state.items = [];
    }
    const params = new URLSearchParams({
      limit: String(state.limit),
      offset: String(state.offset),
      favourite_only: String(state.favouriteOnly),
    });
    if (state.query) params.set("q", state.query);

    try {
      const data = await api(`/api/generations?${params}`);
      state.items = reset ? data.items : state.items.concat(data.items);
      state.total = data.total;
      state.offset = state.items.length;
      renderGallery();
    } catch (err) {
      toast(err.message, true);
    }
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderGallery() {
    const grid = $("gallery");
    $("galleryCount").textContent = state.total ? `· ${state.total}` : "";
    $("emptyState").classList.toggle("hidden", state.items.length > 0);
    $("loadMoreWrap").classList.toggle("hidden", state.items.length >= state.total);

    grid.innerHTML = state.items
      .map(
        (g) => `
      <article class="card" data-id="${g.id}" tabindex="0" role="button"
               aria-label="${escapeHtml(g.prompt.slice(0, 60))}">
        <img src="${g.thumb_url}" alt="${escapeHtml(g.prompt.slice(0, 90))}" loading="lazy" />
        <button class="card-fav ${g.is_favourite ? "on" : ""}" data-fav="${g.id}"
                aria-label="Toggle favourite">★</button>
        <div class="card-overlay">
          <p class="card-prompt">${escapeHtml(g.prompt)}</p>
        </div>
      </article>`
      )
      .join("");

    grid.querySelectorAll(".card").forEach((card) => {
      const id = Number(card.dataset.id);
      card.addEventListener("click", (ev) => {
        if (ev.target.dataset.fav) return;
        const gen = state.items.find((g) => g.id === id);
        if (gen) openLightbox(gen);
      });
      card.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          const gen = state.items.find((g) => g.id === id);
          if (gen) openLightbox(gen);
        }
      });
    });

    grid.querySelectorAll("[data-fav]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = Number(btn.dataset.fav);
        const gen = state.items.find((g) => g.id === id);
        if (!gen) return;
        try {
          const updated = await api(`/api/generations/${id}/favourite`, {
            method: "PATCH",
            body: JSON.stringify({ is_favourite: !gen.is_favourite }),
          });
          gen.is_favourite = updated.is_favourite;
          btn.classList.toggle("on", updated.is_favourite);
          if (state.favouriteOnly && !updated.is_favourite) {
            state.items = state.items.filter((g) => g.id !== id);
            state.total -= 1;
            renderGallery();
          }
        } catch (err) {
          toast(err.message, true);
        }
      });
    });
  }

  $("loadMore").addEventListener("click", () => loadGallery(false));

  let searchTimer = null;
  $("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value.trim();
      loadGallery(true);
    }, 320);
  });

  $("favFilter").addEventListener("click", (e) => {
    state.favouriteOnly = !state.favouriteOnly;
    e.currentTarget.setAttribute("aria-pressed", String(state.favouriteOnly));
    loadGallery(true);
  });

  /* ── lightbox ─────────────────────────────────────────── */
  function openLightbox(gen) {
    state.active = gen;
    $("lbImage").src = gen.image_url;
    $("lbImage").alt = gen.prompt;
    $("lbPrompt").textContent = gen.prompt;
    $("lbStyle").textContent = gen.style;
    $("lbRatio").textContent = gen.aspect_ratio;
    $("lbSize").textContent = `${gen.width} × ${gen.height}`;
    $("lbSeed").textContent = gen.seed;
    $("lbProvider").textContent = `${gen.provider} · ${gen.model}`;
    $("lbRender").textContent = `${gen.render_ms} ms`;
    $("lbCreated").textContent = new Date(gen.created_at).toLocaleString();
    $("lbFav").textContent = gen.is_favourite ? "★ Favourited" : "★ Favourite";
    $("lbDownload").href = gen.image_url;
    $("lbDownload").setAttribute("download", `rang-${gen.id}.png`);
    $("lightbox").classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    $("lightbox").classList.add("hidden");
    document.body.style.overflow = "";
    state.active = null;
  }

  $("lbClose").addEventListener("click", closeLightbox);
  $("lightbox").addEventListener("click", (e) => {
    if (e.target.id === "lightbox") closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("lightbox").classList.contains("hidden")) closeLightbox();
  });

  $("lbFav").addEventListener("click", async () => {
    const gen = state.active;
    if (!gen) return;
    try {
      const updated = await api(`/api/generations/${gen.id}/favourite`, {
        method: "PATCH",
        body: JSON.stringify({ is_favourite: !gen.is_favourite }),
      });
      gen.is_favourite = updated.is_favourite;
      $("lbFav").textContent = updated.is_favourite ? "★ Favourited" : "★ Favourite";
      const inList = state.items.find((g) => g.id === gen.id);
      if (inList) inList.is_favourite = updated.is_favourite;
      renderGallery();
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("lbDelete").addEventListener("click", async () => {
    const gen = state.active;
    if (!gen) return;
    if (!confirm("Delete this image? This cannot be undone.")) return;
    try {
      await api(`/api/generations/${gen.id}`, { method: "DELETE" });
      state.items = state.items.filter((g) => g.id !== gen.id);
      state.total = Math.max(0, state.total - 1);
      closeLightbox();
      renderGallery();
      toast("Deleted");
    } catch (err) {
      toast(err.message, true);
    }
  });

  /* ── tip chips ────────────────────────────────────────── */
  const TIPS = [
    "A cinematic mountain range at golden hour",
    "Neon cyberpunk city at night, rain on the streets",
    "Calm ocean waves at sunset, pastel sky",
    "A misty forest in the early morning",
    "Deep space nebula with a ringed planet",
    "Minimal abstract shapes, soft pastel palette",
    "A grand mosque with domes at dusk",
    "Retro 80s desert highway at sunset",
  ];

  $("tipChips").innerHTML = TIPS.map(
    (t) => `<button type="button" class="chip tip">${escapeHtml(t)}</button>`
  ).join("");

  $("tipChips").querySelectorAll(".chip.tip").forEach((chip) => {
    chip.addEventListener("click", () => {
      promptEl.value = chip.textContent;
      countEl.textContent = promptEl.value.length;
      promptEl.focus();
      runPreview();
    });
  });

  /* ── boot ─────────────────────────────────────────────── */
  (async function boot() {
    if (!state.token) return;
    try {
      const me = await api("/api/auth/me");
      setSession(state.token, me);
      enterApp();
    } catch {
      signOut();
    }
  })();
})();
