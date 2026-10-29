(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const TOKEN_KEY = "citation_admin_token";
  const FAVORITES_KEY = "citation_favorites";
  const state = {
    items: [], page: 1, pages: 1, total: 0, query: "", tag: "", sort: "recent", availableTags: [],
    adminToken: sessionStorage.getItem(TOKEN_KEY) || "", admin: false,
    favorites: loadFavorites(), activeDialog: null, returnFocus: null, toastTimer: null, requestId: 0,
  };

  function loadFavorites() {
    try {
      const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
      return new Set(Array.isArray(value) ? value.map(String) : []);
    } catch (_error) {
      return new Set();
    }
  }

  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    use.setAttribute("href", "#i-" + name);
    svg.append(use);
    return svg;
  }

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function showToast(message, isError = false) {
    const toast = $("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("is-error", isError);
    toast.classList.add("is-visible");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3200);
  }

  async function api(path, options = {}, token = "") {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set("Content-Type", "application/json");
    const bearer = token || state.adminToken;
    if (bearer) headers.set("Authorization", "Bearer " + bearer);
    const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.erreur || "Une erreur est survenue. Réessayez.");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function updateAdminUI() {
    const button = $("#admin-toggle");
    if (button) button.textContent = state.admin ? "Quitter l’espace éditeur" : "Espace éditeur";
    $$("[data-admin-only]").forEach((element) => { element.hidden = !state.admin; });
    renderQuotes();
  }

  function updateFavoriteCount() {
    const count = $("#stat-favorites");
    if (count) count.textContent = String(state.favorites.size);
  }

  function saveFavorites() {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites])); } catch (_error) { /* Storage can be disabled. */ }
    updateFavoriteCount();
  }

  function formatDate(value) {
    if (!value) return "Date inconnue";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Date inconnue";
    return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" }).format(date);
  }

  function renderQuoteTags(tags, container) {
    container.replaceChildren();
    (tags || []).forEach((tag) => {
      const button = make("button", "quote-tag", "#" + tag);
      button.type = "button";
      button.dataset.useTag = tag;
      button.setAttribute("aria-label", "Filtrer par thème " + tag);
      container.append(button);
    });
  }

  function renderQuotes() {
    const grid = $("#quote-grid");
    if (!grid) return;
    grid.replaceChildren();
    if (!state.items.length) {
      const empty = make("div", "empty-state");
      empty.append(make("span", "empty-symbol", "“"), make("span", "", "Aucune citation ne correspond à cette recherche."));
      grid.append(empty);
    } else {
      state.items.forEach((quote) => {
        const card = make("article", "quote-card");
        card.dataset.quoteId = String(quote.id);
        const top = make("div", "quote-card-top");
        top.append(make("span", "quote-index", "N° " + String(quote.id).padStart(3, "0")));
        const actions = make("div", "card-actions");
        const favorite = make("button", "icon-button favorite-button" + (state.favorites.has(String(quote.id)) ? " is-favorite" : ""));
        favorite.type = "button";
        favorite.dataset.favoriteId = String(quote.id);
        favorite.setAttribute("aria-label", state.favorites.has(String(quote.id)) ? "Retirer des favoris" : "Ajouter aux favoris");
        favorite.setAttribute("aria-pressed", String(state.favorites.has(String(quote.id))));
        favorite.title = state.favorites.has(String(quote.id)) ? "Dans vos favoris" : "Ajouter aux favoris";
        favorite.append(icon("heart"));
        actions.append(favorite);
        const adminActions = make("span", "card-actions admin-actions");
        adminActions.hidden = !state.admin;
        const edit = make("button", "icon-button");
        edit.type = "button"; edit.dataset.editId = String(quote.id); edit.title = "Modifier"; edit.setAttribute("aria-label", "Modifier la citation"); edit.append(icon("edit"));
        const remove = make("button", "icon-button");
        remove.type = "button"; remove.dataset.deleteId = String(quote.id); remove.title = "Supprimer"; remove.setAttribute("aria-label", "Supprimer la citation"); remove.append(icon("trash"));
        adminActions.append(edit, remove);
        actions.append(adminActions);
        top.append(actions);

        const body = make("blockquote", "quote-body", "“" + quote.citation + "”");
        const author = make("p", "quote-author", quote.auteur);
        const tags = make("div", "quote-tags");
        renderQuoteTags(quote.tags, tags);
        const footer = make("div", "quote-card-footer");
        footer.append(make("time", "", formatDate(quote.date_creation)));
        const copy = make("button", "icon-button");
        copy.type = "button"; copy.dataset.copyId = String(quote.id); copy.title = "Copier la citation"; copy.setAttribute("aria-label", "Copier la citation"); copy.append(icon("copy"));
        footer.append(copy);
        card.append(top, body, author, tags, footer);
        grid.append(card);
      });
    }
    grid.setAttribute("aria-busy", "false");
    const start = state.total ? Math.min(state.total, state.items.length) : 0;
    const count = $("#result-count");
    if (count) count.textContent = state.total ? start + " citation" + (state.total === 1 ? "" : "s") + " dans le carnet" : "0 citation";
    const loadMore = $("#load-more");
    if (loadMore) loadMore.hidden = state.page >= state.pages;
    updateFavoriteCount();
  }

  function renderFeatured(quote) {
    if (!quote) return;
    const text = $("#featured-text");
    const author = $("#featured-author");
    if (text) text.textContent = "“" + quote.citation + "”";
    if (author) author.textContent = quote.auteur;
  }

  function chooseFeatured() {
    if (!state.items.length) return;
    const quote = state.items[Math.floor(Math.random() * state.items.length)];
    renderFeatured(quote);
  }

  function renderTagFilters(tags) {
    const container = $("#tag-filters");
    if (!container) return;
    const active = state.tag;
    container.replaceChildren();
    const all = make("button", "filter-chip" + (active ? "" : " is-active"), "Tout");
    all.type = "button"; all.dataset.tag = ""; all.setAttribute("aria-pressed", String(!active)); container.append(all);
    (tags || []).slice(0, 10).forEach((item) => {
      const tag = typeof item === "string" ? item : item.tag;
      if (!tag) return;
      const button = make("button", "filter-chip" + (tag.toLocaleLowerCase("fr") === active.toLocaleLowerCase("fr") ? " is-active" : ""), tag);
      button.type = "button"; button.dataset.tag = tag; button.setAttribute("aria-pressed", String(tag.toLocaleLowerCase("fr") === active.toLocaleLowerCase("fr")));
      container.append(button);
    });
  }

  async function loadStats() {
    try {
      const stats = await api("/api/stats");
      const authors = Object.keys(stats.citations_par_auteur || {});
      const total = $("#stat-quotes");
      const authorCount = $("#stat-authors");
      if (total) total.textContent = String(stats.total_citations || 0).padStart(2, "0");
      if (authorCount) authorCount.textContent = String(authors.length).padStart(2, "0");
      state.availableTags = stats.tags_populaires || [];
      renderTagFilters(state.availableTags);
    } catch (error) { showToast(error.message, true); }
  }

  function buildQuery(page) {
    const params = new URLSearchParams({ page: String(page), per_page: "12", sort: state.sort });
    if (state.query) params.set("q", state.query);
    if (state.tag) params.set("tag", state.tag);
    return "/api/citations?" + params.toString();
  }

  async function loadQuotes({ append = false } = {}) {
    const grid = $("#quote-grid");
    const requestId = ++state.requestId;
    if (!append && grid) grid.setAttribute("aria-busy", "true");
    try {
      const page = append ? state.page + 1 : 1;
      const result = await api(buildQuery(page));
      if (requestId !== state.requestId) return;
      state.page = result.page;
      state.pages = result.pages;
      state.total = result.total;
      state.items = append ? state.items.concat(result.items) : result.items;
      renderQuotes();
      if (!append && state.items.length) chooseFeatured();
    } catch (error) {
      if (requestId !== state.requestId) return;
      state.items = [];
      state.total = 0;
      renderQuotes();
      showToast(error.message, true);
    }
  }

  async function refresh() {
    await Promise.all([loadStats(), loadQuotes()]);
  }

  function openModal(modal) {
    if (!modal) return;
    state.returnFocus = document.activeElement;
    state.activeDialog = modal;
    modal.hidden = false;
    document.body.classList.add("dialog-open");
    requestAnimationFrame(() => $("input:not([type=hidden]), textarea, button", modal)?.focus());
  }

  function closeModal(modal = state.activeDialog) {
    if (!modal) return;
    modal.hidden = true;
    state.activeDialog = null;
    document.body.classList.remove("dialog-open");
    state.returnFocus?.focus?.();
  }

  function setError(selector, message = "") {
    const element = $(selector);
    if (!element) return;
    element.textContent = message;
    element.hidden = !message;
  }

  function openQuoteForm(quote = null) {
    const form = $("#quote-form");
    form?.reset();
    $("#quote-id").value = quote ? quote.id : "";
    $("#quote-text").value = quote ? quote.citation : "";
    $("#quote-author").value = quote ? quote.auteur : "";
    $("#quote-tags").value = quote && quote.tags ? quote.tags.join(", ") : "";
    const heading = $("#quote-dialog-title");
    if (heading) heading.textContent = quote ? "Modifier la citation" : "Ajouter une citation";
    const submit = $("#quote-submit");
    if (submit) {
      submit.replaceChildren(document.createTextNode(quote ? "Enregistrer les modifications " : "Enregistrer la citation "), icon("arrow"));
    }
    setError("#quote-error");
    openModal($("#quote-modal"));
  }

  async function connectAdmin(token) {
    try {
      await api("/api/auth/check", {}, token);
      state.adminToken = token;
      state.admin = true;
      sessionStorage.setItem(TOKEN_KEY, token);
      $("#token-input").value = "";
      updateAdminUI();
      closeModal($("#token-modal"));
      showToast("Espace éditeur déverrouillé.");
      return true;
    } catch (error) {
      setError("#token-error", error.message);
      return false;
    }
  }

  function disconnectAdmin() {
    sessionStorage.removeItem(TOKEN_KEY);
    state.adminToken = "";
    state.admin = false;
    $("#token-input").value = "";
    updateAdminUI();
    showToast("Session éditeur fermée.");
  }

  function bindForms() {
    $$("[data-open-quote]").forEach((button) => button.addEventListener("click", () => {
      if (state.admin) openQuoteForm();
      else {
        showToast("Déverrouillez l’espace éditeur pour ajouter une citation.", true);
        openModal($("#token-modal"));
      }
    }));
    $("#admin-toggle")?.addEventListener("click", () => {
      if (state.admin) disconnectAdmin();
      else { setError("#token-error"); openModal($("#token-modal")); }
    });
    $$("[data-close-modal]").forEach((button) => button.addEventListener("click", () => closeModal(button.closest(".modal-backdrop"))));
    $$(".modal-backdrop").forEach((modal) => modal.addEventListener("mousedown", (event) => {
      if (event.target === modal) closeModal(modal);
    }));

    $("#token-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await connectAdmin($("#token-input").value.trim());
    });

    $("#quote-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!state.admin) return;
      const id = $("#quote-id").value;
      const payload = {
        citation: $("#quote-text").value.trim(),
        auteur: $("#quote-author").value.trim(),
        tags: $("#quote-tags").value.split(",").map((tag) => tag.trim().replace(/^#/, "")).filter(Boolean),
      };
      const submit = $("#quote-submit");
      submit.disabled = true;
      setError("#quote-error");
      try {
        await api(id ? "/api/citations/" + id : "/api/citations", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        closeModal($("#quote-modal"));
        showToast(id ? "Citation mise à jour." : "Votre citation a rejoint le carnet.");
        await refresh();
      } catch (error) { setError("#quote-error", error.message); }
      finally { submit.disabled = false; }
    });
  }

  function bindCollection() {
    $("#quote-grid")?.addEventListener("click", async (event) => {
      const favorite = event.target.closest("[data-favorite-id]");
      if (favorite) {
        const id = favorite.dataset.favoriteId;
        if (state.favorites.has(id)) state.favorites.delete(id); else state.favorites.add(id);
        saveFavorites();
        renderQuotes();
        return;
      }
      const useTag = event.target.closest("[data-use-tag]");
      if (useTag) {
        state.tag = useTag.dataset.useTag;
        renderTagFilters(state.availableTags);
        loadQuotes();
        $("#collection")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      const copy = event.target.closest("[data-copy-id]");
      if (copy) {
        const quote = state.items.find((item) => String(item.id) === copy.dataset.copyId);
        if (!quote) return;
        try {
          await navigator.clipboard.writeText("“" + quote.citation + "” — " + quote.auteur);
          showToast("Citation copiée.");
        } catch (_error) { showToast("La copie n’est pas disponible dans ce navigateur.", true); }
        return;
      }
      const edit = event.target.closest("[data-edit-id]");
      if (edit && state.admin) {
        const quote = state.items.find((item) => String(item.id) === edit.dataset.editId);
        if (quote) openQuoteForm(quote);
        return;
      }
      const remove = event.target.closest("[data-delete-id]");
      if (remove && state.admin) {
        const quote = state.items.find((item) => String(item.id) === remove.dataset.deleteId);
        if (!quote || !window.confirm("Supprimer définitivement cette citation ?")) return;
        remove.disabled = true;
        try {
          await api("/api/citations/" + quote.id, { method: "DELETE" });
          showToast("Citation supprimée du carnet.");
          await refresh();
        } catch (error) { showToast(error.message, true); remove.disabled = false; }
      }
    });

    $("#tag-filters")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-tag]");
      if (!button) return;
      state.tag = button.dataset.tag;
      renderTagFilters(state.availableTags);
      loadQuotes();
    });
    $("#sort-select")?.addEventListener("change", (event) => { state.sort = event.target.value; loadQuotes(); });
    $("#load-more")?.addEventListener("click", () => loadQuotes({ append: true }));

    let debounce;
    $("#search-input")?.addEventListener("input", (event) => {
      clearTimeout(debounce);
      state.query = event.target.value.trim();
      debounce = setTimeout(() => loadQuotes(), 240);
    });

    $("#surprise-button")?.addEventListener("click", chooseFeatured);
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); $("#search-input")?.focus();
      }
      if (event.key === "Escape" && state.activeDialog) closeModal();
      if (event.key === "Tab" && state.activeDialog) {
        const focusable = $$("button:not([disabled]), input:not([disabled]), textarea:not([disabled])", state.activeDialog).filter((item) => item.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
  }

  async function boot() {
    const year = $("#footer-year");
    if (year) year.textContent = "© " + new Date().getFullYear();
    updateFavoriteCount();
    bindForms();
    bindCollection();
    if (state.adminToken) {
      try { await api("/api/auth/check"); state.admin = true; }
      catch (_error) { sessionStorage.removeItem(TOKEN_KEY); state.adminToken = ""; }
    }
    updateAdminUI();
    await refresh();
  }

  boot();
})();
