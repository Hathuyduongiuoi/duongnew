/* Hà Thuỳ Dương - Site shell: routing, header/search, hero slider, reveal, chat, contact, i18n */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------------ */
  /* Thông tin doanh nghiệp: chỉnh tại đây, footer + liên hệ tự cập nhật */
  /* ------------------------------------------------------------------ */
  const SITE_CONFIG = {
    company: "Hà Thuỳ Dương - Data Analyst & BI",
    address: "Hà Nội",
    tax: "", // Mã số thuế
    phone: "0332 125 570",
    email: "htd24307@gmail.com",
    hours: "Thứ 2 - Thứ 6, 08:30 - 17:30",
  };

  const norm = (s) =>
    String(s || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase()
      .trim();

  const toast = (msg, isErr = false) => (typeof showToast === "function" ? showToast(msg, isErr) : undefined);
  const sceneState = () => (typeof state !== "undefined" ? state : { currentScene: 0, lastResult: null });

  /* ------------------------------------------------------------------ */
  /* Routes (cấu trúc phân cấp: Cấp 1 Trang chủ > Cấp 2 Dịch vụ > Cấp 3)  */
  /* ------------------------------------------------------------------ */
  const HOME = ["Trang chủ", "/"];
  const SVC = ["Dịch vụ", "/dich-vu"];
  const ROUTES = {
    "/": { scene: 0, title: "Trang chủ", nav: "home", crumbs: [HOME] },
    "/hathuyduong2403": { scene: 0, title: "Hà Thuỳ Dương", nav: "home", crumbs: [HOME] },
    "/gioi-thieu": { scene: 0, anchor: "gioi-thieu", title: "Giới thiệu", nav: "about", crumbs: [HOME, ["Giới thiệu", "/gioi-thieu"]] },
    "/quy-trinh": { scene: 0, anchor: "quy-trinh", title: "Quy trình", nav: "about", crumbs: [HOME, ["Quy trình", "/quy-trinh"]] },
    "/dich-vu": { scene: 0, anchor: "dich-vu", title: "Dịch vụ", nav: "service", crumbs: [HOME, SVC] },
    "/phan-hoi": { scene: 0, anchor: "phan-hoi", title: "Phản hồi", nav: "home", crumbs: [HOME, ["Phản hồi", "/phan-hoi"]] },
    "/lien-he": { scene: 0, anchor: "lien-he", title: "Liên hệ", nav: "contact", crumbs: [HOME, ["Liên hệ", "/lien-he"]] },
    "/gui-du-lieu": { scene: 1, title: "Gửi dữ liệu", nav: "scene1", crumbs: [HOME, SVC, ["Gửi dữ liệu", "/gui-du-lieu"]] },
    "/xu-ly": { scene: 2, title: "Nhận & làm sạch dữ liệu", nav: "scene2", crumbs: [HOME, SVC, ["Nhận & làm sạch", "/xu-ly"]] },
    "/ket-qua": { scene: 3, title: "Kết quả phân tích", nav: "scene3", crumbs: [HOME, SVC, ["Kết quả", "/ket-qua"]] },
    "/faq": { modal: "faq", title: "Hỏi đáp (FAQ)", nav: "faq" },
    "/chinh-sach-bao-mat": { modal: "privacy", title: "Chính sách bảo mật", nav: "" },
    "/dieu-khoan": { modal: "terms", title: "Điều khoản sử dụng", nav: "" },
  };
  const SCENE_PATH = { 0: "/", 1: "/gui-du-lieu", 2: "/xu-ly", 3: "/ket-qua" };

  let curPath = "/";
  let lastScenePath = "/";
  let applyingRoute = false;

  function normPath(p) {
    let path = String(p || "/").split("?")[0].split("#")[0];
    if (path.length > 1) path = path.replace(/\/+$/, "");
    return path || "/";
  }

  function setHistory(path, mode) {
    if (mode === "none") return;
    if (normPath(location.pathname) === path && mode !== "replace") return;
    try {
      if (mode === "replace") history.replaceState({ p: path }, "", path + location.search);
      else history.pushState({ p: path }, "", path);
    } catch (_) {
      /* file:// or sandboxed contexts */
    }
  }

  function renderCrumbs(path) {
    const bar = $("breadcrumbBar");
    const list = $("breadcrumbList");
    if (!bar || !list) return;
    const r = ROUTES[path];
    if (!r || !r.crumbs || r.crumbs.length < 2) {
      bar.classList.add("is-empty");
      list.innerHTML = "";
      return;
    }
    bar.classList.remove("is-empty");
    list.innerHTML = r.crumbs
      .map(([label, href], i) => {
        const last = i === r.crumbs.length - 1;
        const item = last
          ? `<span aria-current="page" class="text-pink-700">${label}</span>`
          : `<a href="${href}" data-route class="hover:text-pink-600 transition">${i === 0 ? '<i class="fa-solid fa-house text-[10px] mr-1"></i>' : ""}${label}</a>`;
        return `<li class="flex items-center gap-1.5">${item}${last ? "" : '<i class="fa-solid fa-chevron-right text-[8px] text-pink-300"></i>'}</li>`;
      })
      .join("");
  }

  function highlightNav(path) {
    const r = ROUTES[path] || ROUTES["/"];
    const active = new Set([r.nav]);
    if (r.scene >= 1) active.add("service");
    document.querySelectorAll("[data-nav]").forEach((el) => {
      const on = active.has(el.dataset.nav);
      el.classList.toggle("is-active", on);
      if (on) el.setAttribute("aria-current", "page");
      else el.removeAttribute("aria-current");
    });
  }

  function playTransition() {
    if (reduceMotion) return;
    const sweep = $("pageSweep");
    const prog = $("routeProgress");
    [sweep, prog].forEach((el) => {
      if (!el) return;
      el.classList.remove("run");
      void el.offsetWidth;
      el.classList.add("run");
    });
  }

  function scrollToAnchorOrTop(path) {
    const r = ROUTES[path] || {};
    const go = () => {
      if (r.anchor && $(r.anchor)) {
        const header = $("dynamicIslandBar");
        const off = (header ? header.offsetHeight : 72) + 14;
        const y = $(r.anchor).getBoundingClientRect().top + window.scrollY - off;
        window.scrollTo({ top: Math.max(0, y), behavior: reduceMotion ? "auto" : "smooth" });
      } else {
        window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      }
    };
    requestAnimationFrame(() => requestAnimationFrame(go));
  }

  function updateChrome(path) {
    const r = ROUTES[path] || ROUTES["/"];
    curPath = path;
    if (!r.modal) lastScenePath = path;
    renderCrumbs(path);
    highlightNav(path);
    document.title = `${r.title} · Hà Thuỳ Dương | AI301 AI Agent - Đề Dự Án 04`;
    document.body.dataset.route = path;
  }

  // Called by app.js goToScene()
  window.onSceneChanged = (target, prev, opts = {}) => {
    const path = opts.path || SCENE_PATH[target] || "/";
    const mode = opts.history || (opts.silent ? "none" : "push");
    // Close any info modal when the workflow moves on its own
    if (!applyingRoute) closeInfoModal(true);
    if (!applyingRoute) setHistory(path, mode);
    updateChrome(path);
    if (!opts.silent && prev !== target) playTransition();
    if (!applyingRoute && !opts.silent) scrollToAnchorOrTop(path);
  };

  function applyRoute(rawPath, opts = {}) {
    let path = normPath(rawPath);
    let r = ROUTES[path];
    const mode = opts.history || "push";
    if (!r) {
      path = "/";
      r = ROUTES["/"];
    }

    if (r.modal) {
      openInfoModal(r.modal);
      setHistory(path, mode);
      curPath = path;
      document.title = `${r.title} · Hà Thuỳ Dương`;
      highlightNav(path);
      return;
    }

    if (r.scene >= 2 && !sceneState().lastResult) {
      toast("Hãy gửi dữ liệu trước để xem bước này.", true);
      path = "/gui-du-lieu";
      r = ROUTES[path];
    }

    closeInfoModal(true);
    applyingRoute = true;
    try {
      const st = sceneState();
      if (st.currentScene !== r.scene) {
        goToScene(r.scene, "", { path, history: "none", silent: true });
        playTransition();
      }
      setHistory(path, mode);
      updateChrome(path);
      if (!opts.noScroll) scrollToAnchorOrTop(path);
    } finally {
      applyingRoute = false;
    }
  }
  window.navigateTo = (p, o) => applyRoute(p, o);

  /* ------------------------------------------------------------------ */
  /* Link delegation (a[data-route])                                     */
  /* ------------------------------------------------------------------ */
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-route]");
    if (!a) return;
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const href = a.getAttribute("href");
    closeMobileMenu();
    applyRoute(href);
    const src = a.dataset.switchSource;
    if (src && typeof switchInputSource === "function") switchInputSource(src);
    const tab = a.dataset.openTab;
    if (tab && sceneState().lastResult && typeof switchTab === "function") switchTab(tab);
  });

  window.addEventListener("popstate", () => applyRoute(location.pathname, { history: "none" }));

  /* ------------------------------------------------------------------ */
  /* Header: mobile menu, sticky state, progress                         */
  /* ------------------------------------------------------------------ */
  function closeMobileMenu() {
    $("mobileMenu")?.classList.add("hidden");
    const t = $("menuToggle");
    if (t) {
      t.setAttribute("aria-expanded", "false");
      t.innerHTML = '<i class="fa-solid fa-bars"></i>';
    }
  }
  window.toggleMobileMenu = () => {
    const m = $("mobileMenu");
    const t = $("menuToggle");
    if (!m || !t) return;
    const open = m.classList.toggle("hidden") === false;
    t.setAttribute("aria-expanded", String(open));
    t.innerHTML = open ? '<i class="fa-solid fa-xmark"></i>' : '<i class="fa-solid fa-bars"></i>';
  };
  window.toggleMobileSearch = () => {
    const row = $("mobileSearchRow");
    if (!row) return;
    const open = row.classList.toggle("hidden") === false;
    if (open) $("mobileSearchInput")?.focus();
  };

  function onScroll() {
    const y = window.scrollY || 0;
    const doc = document.documentElement;
    const max = Math.max(1, doc.scrollHeight - window.innerHeight);
    const sp = $("scrollProgress");
    if (sp) sp.style.transform = `scaleX(${Math.min(1, y / max)})`;
    $("dynamicIslandBar")?.classList.toggle("is-scrolled", y > 12);
    $("backToTop")?.classList.toggle("is-visible", y > 480);
  }
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ------------------------------------------------------------------ */
  /* Search                                                              */
  /* ------------------------------------------------------------------ */
  const SEARCH_INDEX = [
    { t: "Trang chủ", d: "Banner và điểm nổi bật", k: "trang chu home banner slider", p: "/", i: "fa-house" },
    { t: "Giới thiệu & điểm nổi bật", d: "Vì sao chọn quy trình 7 giai đoạn", k: "gioi thieu diem noi bat 7 giai doan uu diem", p: "/gioi-thieu", i: "fa-circle-info" },
    { t: "Quy trình 4 bước", d: "Gửi, nhận, làm sạch, xuất kết quả", k: "quy trinh buoc nhan lam sach xuat huong dan cach hoat dong", p: "/quy-trinh", i: "fa-diagram-next" },
    { t: "Danh mục dịch vụ", d: "Excel, Word, Google Sheet, Dashboard", k: "dich vu danh muc san pham", p: "/dich-vu", i: "fa-layer-group" },
    { t: "Gửi dữ liệu Excel / Word / PDF", d: "Tải file lên để phân tích", k: "gui du lieu tai len upload excel word pdf csv json xml zip file", p: "/gui-du-lieu", i: "fa-cloud-arrow-up" },
    { t: "Google Sheet & Lark Base", d: "Dán link để đọc tất cả tab", k: "google sheet lark base link bang tinh", p: "/gui-du-lieu", i: "fa-table", src: "gsheet" },
    { t: "Nhận & làm sạch dữ liệu", d: "Báo lỗi, yêu cầu gửi lại", k: "nhan lam sach du lieu bao loi gui lai trung thieu ngoai lai", p: "/xu-ly", i: "fa-broom" },
    { t: "Dashboard & biểu đồ", d: "Cột, đường, tròn, Pareto, Histogram", k: "dashboard bieu do chart thong ke kpi", p: "/ket-qua", i: "fa-chart-column" },
    { t: "Báo cáo Word / PDF", d: "Báo cáo 10 mục kèm giải pháp", k: "bao cao word pdf docx insight giai phap bc", p: "/ket-qua", i: "fa-file-word", tab: "tabProposal" },
    { t: "Phản hồi từ người dùng", d: "Đánh giá minh họa", k: "phan hoi danh gia khach hang testimonial", p: "/phan-hoi", i: "fa-star" },
    { t: "Liên hệ & nhận tư vấn", d: "Biểu mẫu và chat trực tuyến", k: "lien he tu van hotline email form chat", p: "/lien-he", i: "fa-envelope" },
    { t: "Câu hỏi thường gặp (FAQ)", d: "Định dạng file, bảo mật, cách dùng", k: "faq hoi dap cau hoi thuong gap", p: "/faq", i: "fa-circle-question" },
    { t: "Chính sách bảo mật", d: "Cách dữ liệu được xử lý", k: "chinh sach bao mat quyen rieng tu du lieu an toan", p: "/chinh-sach-bao-mat", i: "fa-shield-halved" },
    { t: "Điều khoản sử dụng", d: "Quy định khi dùng hệ thống", k: "dieu khoan su dung quy dinh", p: "/dieu-khoan", i: "fa-file-contract" },
  ];

  function runSearch(q) {
    const tokens = norm(q).split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    return SEARCH_INDEX.map((it) => {
      const hay = norm(`${it.t} ${it.d} ${it.k}`);
      const title = norm(it.t);
      let score = 0;
      for (const tk of tokens) {
        if (title.includes(tk)) score += 3;
        else if (hay.includes(tk)) score += 1;
        else return { it, score: -1 };
      }
      return { it, score };
    })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map((x) => x.it);
  }

  function bindSearch(inputId, boxId, inline) {
    const input = $(inputId);
    const box = $(boxId);
    if (!input || !box) return;
    let items = [];
    let active = -1;

    const close = () => {
      box.classList.add("hidden");
      active = -1;
    };
    const choose = (it) => {
      if (!it) return;
      close();
      input.value = "";
      applyRoute(it.p);
      if (it.src && typeof switchInputSource === "function") switchInputSource(it.src);
      if (it.tab && sceneState().lastResult && typeof switchTab === "function") switchTab(it.tab);
      $("mobileSearchRow")?.classList.add("hidden");
    };
    const render = () => {
      box.innerHTML = items.length
        ? items
            .map(
              (it, i) =>
                `<button type="button" role="option" data-i="${i}" class="${i === active ? "is-active" : ""}"><i class="fa-solid ${it.i}"></i><span><b>${it.t}</b><small>${it.d}</small></span></button>`
            )
            .join("")
        : `<div class="search-empty">Không tìm thấy nội dung phù hợp. Thử từ khoá khác hoặc <a href="/lien-he" data-route>liên hệ</a>.</div>`;
      box.classList.remove("hidden");
    };

    input.addEventListener("input", () => {
      if (!input.value.trim()) return close();
      items = runSearch(input.value);
      active = items.length ? 0 : -1;
      render();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && items.length) {
        e.preventDefault();
        active = (active + 1) % items.length;
        render();
      } else if (e.key === "ArrowUp" && items.length) {
        e.preventDefault();
        active = (active - 1 + items.length) % items.length;
        render();
      } else if (e.key === "Enter") {
        e.preventDefault();
        choose(items[Math.max(0, active)]);
      } else if (e.key === "Escape") {
        close();
        input.blur();
      }
    });
    box.addEventListener("mousedown", (e) => {
      const b = e.target.closest("button[data-i]");
      if (b) {
        e.preventDefault();
        choose(items[Number(b.dataset.i)]);
      }
    });
    document.addEventListener("click", (e) => {
      if (!box.contains(e.target) && e.target !== input) close();
    });
    input.addEventListener("focus", () => {
      if (input.value.trim() && items.length) render();
    });
    return { input, choose, run: () => (items = runSearch(input.value)) };
  }

  /* ------------------------------------------------------------------ */
  /* Hero slider (3D tilt, swipe, auto-play, keyboard)                   */
  /* ------------------------------------------------------------------ */
  const heroSlider = (() => {
    const root = $("heroSlider");
    if (!root) return { next() {}, prev() {}, go() {} };
    const slides = Array.from(root.querySelectorAll(".hero-slide"));
    const dotsBox = $("heroDots");
    const bar = $("heroProgressBar");
    const DURATION = 6800;
    let idx = 0;
    let timer = null;
    let hovering = false;

    dotsBox.innerHTML = slides
      .map((_, i) => `<button type="button" role="tab" aria-label="Slide ${i + 1}" data-i="${i}"></button>`)
      .join("");
    const dots = Array.from(dotsBox.querySelectorAll("button"));
    dotsBox.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (b) go(Number(b.dataset.i), true);
    });

    function restartProgress() {
      if (!bar) return;
      bar.classList.remove("run");
      void bar.offsetWidth;
      if (!reduceMotion) bar.classList.add("run");
    }
    function paint() {
      slides.forEach((s, i) => {
        s.classList.toggle("is-active", i === idx);
        s.classList.toggle("is-before", i < idx);
        s.setAttribute("aria-hidden", String(i !== idx));
        s.querySelectorAll("a,button").forEach((el) => (el.tabIndex = i === idx ? 0 : -1));
      });
      dots.forEach((d, i) => {
        d.classList.toggle("is-active", i === idx);
        d.setAttribute("aria-selected", String(i === idx));
      });
    }
    function go(i, manual) {
      idx = (i + slides.length) % slides.length;
      paint();
      restartProgress();
      if (manual) schedule();
    }
    function next(manual) {
      go(idx + 1, manual);
    }
    function prev(manual) {
      go(idx - 1, manual);
    }
    function homeVisible() {
      const sc = $("scene0");
      return sc && sc.classList.contains("scene-active") && !document.hidden && window.scrollY < root.offsetHeight + 160;
    }
    function schedule() {
      clearTimeout(timer);
      if (reduceMotion) return;
      timer = setTimeout(() => {
        if (!hovering && homeVisible()) next(false);
        schedule();
      }, DURATION);
    }

    root.addEventListener("mouseenter", () => {
      hovering = true;
      bar?.classList.add("paused");
    });
    root.addEventListener("mouseleave", () => {
      hovering = false;
      bar?.classList.remove("paused");
    });
    root.addEventListener("focusin", () => (hovering = true));
    root.addEventListener("focusout", () => (hovering = false));
    root.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") next(true);
      else if (e.key === "ArrowLeft") prev(true);
    });

    // Pointer swipe / drag with live tilt feedback
    const stage = root.querySelector(".hero-stage");
    let sx = null;
    let sy = null;
    let dragging = false;
    stage.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 && e.pointerType === "mouse") return;
      if (e.target.closest("a,button")) return;
      sx = e.clientX;
      sy = e.clientY;
      dragging = true;
    });
    stage.addEventListener("pointermove", (e) => {
      if (!dragging || sx === null) return;
      const dx = e.clientX - sx;
      const dy = e.clientY - sy;
      if (Math.abs(dx) > Math.abs(dy)) {
        const cur = slides[idx];
        cur.style.transition = "none";
        cur.style.transform = `translate3d(${dx * 0.35}px,0,0) rotateY(${Math.max(-8, Math.min(8, dx / 22))}deg)`;
        cur.style.opacity = String(Math.max(0.35, 1 - Math.abs(dx) / 520));
      }
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      const cur = slides[idx];
      cur.style.transition = "";
      cur.style.transform = "";
      cur.style.opacity = "";
      if (sx === null) return;
      const dx = (e.clientX ?? sx) - sx;
      const dy = (e.clientY ?? sy) - sy;
      sx = sy = null;
      if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) {
        if (dx < 0) next(true);
        else prev(true);
      }
    };
    stage.addEventListener("pointerup", endDrag);
    stage.addEventListener("pointercancel", endDrag);
    stage.addEventListener("pointerleave", (e) => dragging && endDrag(e));

    // Pointer parallax on visuals
    root.addEventListener("mousemove", (e) => {
      if (reduceMotion) return;
      const r = root.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      root.style.setProperty("--px", px.toFixed(3));
      root.style.setProperty("--py", py.toFixed(3));
    });

    paint();
    restartProgress();
    schedule();
    document.addEventListener("visibilitychange", () => schedule());
    return { next, prev, go };
  })();
  window.heroSlider = heroSlider;

  /* ------------------------------------------------------------------ */
  /* Reveal on scroll + animated counters                                */
  /* ------------------------------------------------------------------ */
  function animateCount(el) {
    if (el.dataset.done) return;
    el.dataset.done = "1";
    const to = Number(el.dataset.count || 0);
    const suffix = el.dataset.suffix || "";
    if (reduceMotion) {
      el.textContent = to + suffix;
      return;
    }
    const start = performance.now();
    const dur = 1200;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(to * eased) + suffix;
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function initReveal() {
    const revealEls = Array.from(document.querySelectorAll(".reveal"));
    const counters = Array.from(document.querySelectorAll("[data-count]"));
    if (!("IntersectionObserver" in window)) {
      revealEls.forEach((el) => el.classList.add("is-visible"));
      counters.forEach(animateCount);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (!en.isIntersecting) return;
          en.target.classList.add("is-visible");
          en.target.querySelectorAll("[data-count]").forEach(animateCount);
          io.unobserve(en.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );
    revealEls.forEach((el) => io.observe(el));
  }

  /* ------------------------------------------------------------------ */
  /* Đa ngôn ngữ: VI / EN / 中文 / 日本語 / 한국어                         */
  /* ------------------------------------------------------------------ */
  const I18N = {
    en: {
      "nav.home": "Home", "nav.about": "About", "nav.services": "Services", "nav.faq": "FAQ", "nav.contact": "Contact", "nav.cta": "Send data",
      "search.ph": "Search pages, services...",
      "hero1.badge": "Data Analyst &amp; Business Intelligence",
      "hero1.title": 'Turn raw data into <span class="pink-underline text-pink-600">business decisions</span>',
      "hero1.desc": "Send Excel, Word, PDF files or a Google Sheet / Lark Base link. AI receives, cleans, analyzes and exports Dashboard & reports.",
      "hero1.cta1": "Send data now", "hero1.cta2": "Try sample data",
      "hero2.badge": "Reads every format",
      "hero2.title": 'One intake for <span class="pink-underline text-pink-600">every data source</span>',
      "hero2.desc": "Excel, CSV, Word, PDF, JSON, XML, HTML, ZIP, Google Sheet, Lark Base. Unreadable files are flagged immediately to resend.",
      "hero2.cta1": "Upload files", "hero2.cta2": "View services",
      "hero3.badge": "4 deliverables",
      "hero3.title": 'Dashboard, Excel and Word report <span class="pink-underline text-pink-600">in a single run</span>',
      "hero3.desc": "7-stage workflow: inspect, clean, analyze, charts, insight, solutions and a 10-section report.",
      "hero3.cta1": "Get a consultation", "hero3.cta2": "See workflow",
      "about.kicker": "About", "about.title": "BI Data Analysis with Ha Thuy Duong",
      "about.sub": "Upload file → AI checks & cleans → Export Dashboard, Excel and Word Report. Original files stay untouched.",
      "how.kicker": "How it works", "how.title": "4 steps from data to report",
      "demo.kicker": "Interactive Demo", "demo.title": "Preview what you will receive",
      "demo.sub": "Click each tab below to preview cleaned table, KPI Dashboard and Word Report — or click Try Demo Now.",
      "demo.run": "Try Demo Now",
      "svc.kicker": "Services", "svc.title": "Analysis services", "svc.sub": "Pick a service to jump straight to it. Max 3 clicks from Home to results.",
      "tst.kicker": "Real Feedback", "tst.title": "What users say in detail", "tst.sub": "Real workflows from catching broken sheets and cleaning 15,000 rows to executive Word reports.",
      "ct.kicker": "Contact", "ct.title": "Get a consultation", "ct.sub": "Leave your details and we will reply as soon as possible.",
      "ft.company": "Company information", "ft.services": "Services", "ft.links": "Quick links", "ft.social": "Connect", "ft.rights": "All rights reserved.",
    },
    zh: {
      "nav.home": "首页", "nav.about": "简介", "nav.services": "服务", "nav.faq": "常见问题", "nav.contact": "联系", "nav.cta": "上传数据",
      "search.ph": "搜索页面、服务...",
      "hero1.badge": "数据分析师 &amp; 商业智能",
      "hero1.title": '将原始数据转化为<span class="pink-underline text-pink-600">商业决策</span>',
      "hero1.desc": "上传 Excel、Word、PDF 或 Google Sheet / Lark Base 链接。AI 自动接收、清洗、分析并导出仪表盘与报告。",
      "hero1.cta1": "立即上传数据", "hero1.cta2": "运行示例数据",
      "hero2.badge": "支持全格式",
      "hero2.title": '统一入口处理<span class="pink-underline text-pink-600">各类数据源</span>',
      "hero2.desc": "支持 Excel、CSV、Word、PDF、JSON、XML、HTML、ZIP、Google Sheet 与 Lark Base。文件异常即时提示重传。",
      "hero2.cta1": "上传文件", "hero2.cta2": "查看服务",
      "hero3.badge": "4项交付成果",
      "hero3.title": '仪表盘、Excel 与 Word 报告<span class="pink-underline text-pink-600">一次生成</span>',
      "hero3.desc": "7大分析阶段：数据接收、清洗、统计分析、图表可视化、洞察、行动方案与10节专业报告。",
      "hero3.cta1": "获取咨询", "hero3.cta2": "查看流程",
      "about.kicker": "简介", "about.title": "与河垂阳一起进行商业智能数据分析",
      "about.sub": "上传文件 → AI 检查并清洗 → 导出仪表盘、Excel 与 Word 报告。完整保留原始文件，绝不编造数据。",
      "how.kicker": "工作流程", "how.title": "从数据到报告仅需4步",
      "demo.kicker": "在线演示", "demo.title": "提前体验您将获得的分析成果",
      "demo.sub": "点击下方标签查看清洗表、KPI 仪表盘与 Word 报告示例，或点击立即体验。",
      "demo.run": "立即体验演示",
      "svc.kicker": "服务目录", "svc.title": "数据分析服务", "svc.sub": "选择任意服务直达操作界面，从首页最多3次点击即可查看结果。",
      "tst.kicker": "用户评价", "tst.title": "用户的真实使用反馈", "tst.sub": "从拦截错误表格、清洗 15,000 行数据到一键导出管理层 Word 报告。",
      "ct.kicker": "联系我们", "ct.title": "预约咨询", "ct.sub": "留下您的联系方式，我们将尽快回复。",
      "ft.company": "机构信息", "ft.services": "核心服务", "ft.links": "快速链接", "ft.social": "社交媒体", "ft.rights": "保留所有权利。",
    },
    ja: {
      "nav.home": "ホーム", "nav.about": "紹介", "nav.services": "サービス", "nav.faq": "FAQ", "nav.contact": "お問い合わせ", "nav.cta": "データ送信",
      "search.ph": "ページ・サービスを検索...",
      "hero1.badge": "データアナリスト &amp; BI",
      "hero1.title": '生データを<span class="pink-underline text-pink-600">ビジネス意思決定</span>へ',
      "hero1.desc": "Excel・Word・PDF・Google Sheet・Lark Baseを送信するだけ。AIが検査・クレンジング・分析し、ダッシュボードと報告書を出力します。",
      "hero1.cta1": "データを送信", "hero1.cta2": "サンプルを実行",
      "hero2.badge": "全形式対応",
      "hero2.title": 'あらゆるデータソースを<span class="pink-underline text-pink-600">一つの窓口で</span>',
      "hero2.desc": "Excel、CSV、Word、PDF、JSON、XML、HTML、ZIP等に対応。読めないファイルは即座にエラー通知して再送信を促します。",
      "hero2.cta1": "ファイル選択", "hero2.cta2": "サービス一覧",
      "hero3.badge": "4つの成果物",
      "hero3.title": 'ダッシュボード・Excel・Word報告書を<span class="pink-underline text-pink-600">一括作成</span>',
      "hero3.desc": "7段階の分析プロセス：データ受付、クレンジング、集計分析、グラフ化、インサイト、施策提案、10章レポート。",
      "hero3.cta1": "相談する", "hero3.cta2": "手順を見る",
      "about.kicker": "紹介", "about.title": "ハー・トゥイ・ズオンのBIデータ分析",
      "about.sub": "送信 → AI検査・クレンジング → ダッシュボード・Excel・Word出力。元ファイルは変更せず数値の捏造もしません。",
      "how.kicker": "仕組み", "how.title": "データから報告まで4ステップ",
      "demo.kicker": "デモ表示", "demo.title": "分析結果のプレビューを体験",
      "demo.sub": "下のタブでクレンジング表・KPIダッシュボード・Word報告書を確認、または「今すぐデモ実行」をクリック。",
      "demo.run": "今すぐデモ実行",
      "svc.kicker": "サービス", "svc.title": "分析サービス一覧", "svc.sub": "ホームから最大3クリックで結果画面へ移動できます。",
      "tst.kicker": "利用者の声", "tst.title": "詳細なユーザーレビュー", "tst.sub": "15,000行のクレンジングから経営層向けWord報告書作成までの実例。",
      "ct.kicker": "お問い合わせ", "ct.title": "ご相談・お問い合わせ", "ct.sub": "内容をご記入いただければ折り返しご連絡いたします。",
      "ft.company": "運営情報", "ft.services": "サービス", "ft.links": "クイックリンク", "ft.social": "SNS", "ft.rights": "All rights reserved.",
    },
    ko: {
      "nav.home": "홈", "nav.about": "소개", "nav.services": "서비스", "nav.faq": "FAQ", "nav.contact": "문의", "nav.cta": "데이터 전송",
      "search.ph": "페이지, 서비스 검색...",
      "hero1.badge": "데이터 애널리스트 &amp; BI",
      "hero1.title": '원본 데이터를 <span class="pink-underline text-pink-600">비즈니스 의사결정</span>으로',
      "hero1.desc": "Excel, Word, PDF 또는 Google Sheet / Lark Base 링크를 보내세요. AI가 수신, 정제, 분석 후 대시보드와 보고서를 출력합니다.",
      "hero1.cta1": "데이터 보내기", "hero1.cta2": "샘플 실행",
      "hero2.badge": "모든 형식 지원",
      "hero2.title": '모든 데이터 소스를 <span class="pink-underline text-pink-600">하나의 창구로</span>',
      "hero2.desc": "Excel, CSV, Word, PDF, JSON, XML, HTML, ZIP 지원. 오류가 있는 파일은 즉시 알려 재전송을 안내합니다.",
      "hero2.cta1": "파일 업로드", "hero2.cta2": "서비스 보기",
      "hero3.badge": "4가지 결과물",
      "hero3.title": '대시보드·Excel·Word 보고서를 <span class="pink-underline text-pink-600">한 번에 생성</span>',
      "hero3.desc": "7단계 프로세스: 데이터 점검, 정제, 다차원 분석, 차트 시각화, 인사이트, 실행 솔루션 및 10개 섹션 보고서.",
      "hero3.cta1": "상담 받기", "hero3.cta2": "프로세스 보기",
      "about.kicker": "소개", "about.title": "하 투이 즈엉의 BI 데이터 분석",
      "about.sub": "파일 전송 → AI 검증 및 정제 → 대시보드, Excel, Word 보고서 출력. 원본 파일은 그대로 유지됩니다.",
      "how.kicker": "작동 방식", "how.title": "데이터에서 보고서까지 4단계",
      "demo.kicker": "데모 미리보기", "demo.title": "결과물을 미리 체험해 보세요",
      "demo.sub": "아래 탭에서 정제 테이블, KPI 대시보드, Word 보고서를 미리 보거나 지금 데모를 실행하세요.",
      "demo.run": "지금 데모 실행",
      "svc.kicker": "서비스", "svc.title": "분석 서비스 목록", "svc.sub": "홈에서 최대 3번 클릭으로 원하는 결과 화면으로 이동합니다.",
      "tst.kicker": "사용자 후기", "tst.title": "실제 사용자 상세 후기", "tst.sub": "15,000행 데이터 정제부터 임원 보고용 Word 문서 생성까지.",
      "ct.kicker": "문의하기", "ct.title": "상담 신청", "ct.sub": "정보를 남겨주시면 빠르게 답변드리겠습니다.",
      "ft.company": "기관 정보", "ft.services": "서비스", "ft.links": "바로가기", "ft.social": "소셜 미디어", "ft.rights": "All rights reserved.",
    },
  };
  let lang = "vi";

  function applyLang(next) {
    lang = I18N[next] ? next : "vi";
    document.documentElement.lang = lang;
    const dict = I18N[lang] || {};
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      if (el.dataset.vi === undefined) el.dataset.vi = el.innerHTML;
      const tr = dict[el.dataset.i18n];
      el.innerHTML = lang !== "vi" && tr ? tr : el.dataset.vi;
    });
    document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
      if (el.dataset.viPh === undefined) el.dataset.viPh = el.getAttribute("placeholder") || "";
      const tr = dict[el.dataset.i18nPh];
      el.setAttribute("placeholder", lang !== "vi" && tr ? tr : el.dataset.viPh);
    });
    if ($("langSelect")) $("langSelect").value = lang;
    document.querySelectorAll(".langSelectMobile").forEach((s) => (s.value = lang));
    try {
      localStorage.setItem("site_lang", lang);
    } catch (_) {
      /* ignore */
    }
  }
  window.setLanguage = (next) => applyLang(next);
  window.toggleLanguage = () => {
    const order = ["vi", "en", "zh", "ja", "ko"];
    applyLang(order[(order.indexOf(lang) + 1) % order.length]);
  };
  window.switchDemoTab = (tab) => {
    ["clean", "dash", "report"].forEach((t) => {
      const btn = document.querySelector(`[data-demo-tab="${t}"]`);
      if (btn) btn.classList.toggle("is-active", t === tab);
      const pane = $(`demoPane${t.charAt(0).toUpperCase() + t.slice(1)}`);
      if (pane) pane.classList.toggle("hidden", t !== tab);
    });
  };

  /* ------------------------------------------------------------------ */
  /* Site config binding                                                 */
  /* ------------------------------------------------------------------ */
  function bindSiteConfig() {
    document.querySelectorAll("[data-site]").forEach((el) => {
      const key = el.dataset.site;
      const val = SITE_CONFIG[key];
      if (val) el.textContent = val;
    });
    const phone = SITE_CONFIG.phone.replace(/[^\d+]/g, "");
    const hot = $("hotlineBtn");
    if (hot && phone) {
      hot.removeAttribute("data-route");
      hot.setAttribute("href", `tel:${phone}`);
      $("hotlineText").textContent = SITE_CONFIG.phone;
    }
    document.querySelectorAll("[data-site='phone']").forEach((el) => {
      if (phone) el.innerHTML = `<a href="tel:${phone}" class="hover:text-pink-600">${SITE_CONFIG.phone}</a>`;
    });
    document.querySelectorAll("[data-site='email']").forEach((el) => {
      if (SITE_CONFIG.email) el.innerHTML = `<a href="mailto:${SITE_CONFIG.email}" class="hover:text-pink-600">${SITE_CONFIG.email}</a>`;
    });
    if ($("copyYear")) $("copyYear").textContent = String(new Date().getFullYear());
    if ($("secureLabel")) $("secureLabel").textContent = location.protocol === "https:" ? "Kết nối an toàn (HTTPS)" : "Kết nối cục bộ";
  }

  /* ------------------------------------------------------------------ */
  /* Info modal: FAQ / Chính sách / Điều khoản                           */
  /* ------------------------------------------------------------------ */
  const INFO = {
    faq: {
      title: "Câu hỏi thường gặp (FAQ)",
      html: () => {
        const qa = [
          ["Hệ thống đọc được những định dạng nào?", "Excel (.xlsx, .xlsm, .xls, .ods), CSV/TSV, Word (.docx, .doc, .odt, .rtf), PDF, JSON, XML, HTML, Markdown, TXT, ZIP, ảnh, cùng link Google Sheet và Lark Base."],
          ["Nếu file lỗi hoặc rỗng thì sao?", "AI báo lỗi ngay ở bước nhận dữ liệu và hiện khung gửi lại file. Nếu làm sạch không thành công, hệ thống cũng báo lỗi và yêu cầu bạn gửi lại."],
          ["Tôi nhận được những sản phẩm nào?", "Excel dữ liệu sạch, Excel tổng hợp kèm biểu đồ, Dashboard (xuất HTML) và báo cáo Word/PDF 10 mục."],
          ["Dữ liệu gốc của tôi có bị sửa không?", "Không. Hệ thống tạo bản dữ liệu sạch riêng, giữ nguyên file gốc và không tự điền số liệu thay thế cho ô thiếu."],
          ["Dữ liệu có được gửi ra ngoài không?", "Mặc định xử lý ngay trên máy chủ cục bộ. Chỉ khi bạn chọn Gemini hoặc OpenAI trong Cài đặt thì nội dung cần phân tích mới được gửi tới nhà cung cấp đó."],
          ["Làm sao để được tư vấn thêm?", "Dùng biểu mẫu ở mục Liên hệ hoặc mở Chat trực tuyến ở góc phải màn hình."],
        ];
        return qa
          .map(([q, a]) => `<details class="faq-item"><summary>${q}</summary><p>${a}</p></details>`)
          .join("");
      },
    },
    privacy: {
      title: "Chính sách bảo mật",
      html: () => `
        <p>Chúng tôi chỉ xử lý dữ liệu ở mức cần thiết để thực hiện yêu cầu phân tích của bạn.</p>
        <ul class="list-disc pl-5 space-y-1.5">
          <li>Dữ liệu bạn gửi được xử lý an toàn trên hệ thống máy chủ bảo mật (HTTPS/SSL).</li>
          <li>Khi bạn bật Gemini hoặc OpenAI trong Cài đặt, nội dung cần phân tích được gửi tới nhà cung cấp tương ứng bằng khoá API của bạn.</li>
          <li>Nhật ký kiểm tra (audit) được lưu cục bộ trong thư mục <code>audit_logs</code>, gồm các bước xử lý và thống kê, có thể kèm trích dẫn số liệu.</li>
          <li>Biểu mẫu liên hệ lưu họ tên, email/số điện thoại và lời nhắn vào tệp <code>contact_requests.jsonl</code> trên máy chủ.</li>
          <li>Trang không dùng cookie theo dõi. Lựa chọn ngôn ngữ được lưu trong bộ nhớ trình duyệt (localStorage).</li>
        </ul>
        <p>Bạn có thể yêu cầu xoá thông tin liên hệ bằng cách gửi yêu cầu qua mục Liên hệ.</p>`,
    },
    terms: {
      title: "Điều khoản sử dụng",
      html: () => `
        <ul class="list-disc pl-5 space-y-1.5">
          <li>Kết quả phân tích mang tính hỗ trợ ra quyết định, được tạo từ chính dữ liệu bạn cung cấp.</li>
          <li>Bạn chịu trách nhiệm về tính hợp pháp và độ chính xác của dữ liệu tải lên.</li>
          <li>Hệ thống không tự bịa số liệu. Khi dữ liệu thiếu hoặc không đủ điều kiện, kết quả sẽ nêu rõ thay vì suy đoán.</li>
          <li>Các giá trị ngoại lai được cảnh báo để bạn đối chiếu chứng từ gốc, không tự động bị xoá.</li>
          <li>Không dùng hệ thống để xử lý dữ liệu vi phạm pháp luật hoặc quyền của bên thứ ba.</li>
        </ul>`,
    },
  };

  function openInfoModal(key) {
    const info = INFO[key];
    const m = $("infoModal");
    if (!info || !m) return;
    $("infoTitle").textContent = info.title;
    $("infoBody").innerHTML = info.html();
    m.classList.remove("hidden");
    m.classList.add("flex");
    m.querySelector("button")?.focus();
  }
  function closeInfoModal(silent) {
    const m = $("infoModal");
    if (!m || m.classList.contains("hidden")) return;
    m.classList.add("hidden");
    m.classList.remove("flex");
    if (!silent && ROUTES[curPath] && ROUTES[curPath].modal) {
      setHistory(lastScenePath, "push");
      updateChrome(lastScenePath);
    }
  }
  window.closeInfoModal = closeInfoModal;
  $("infoModal")?.addEventListener("click", (e) => {
    if (e.target === $("infoModal")) closeInfoModal();
  });

  /* ------------------------------------------------------------------ */
  /* Contact form                                                        */
  /* ------------------------------------------------------------------ */
  function initContactForm() {
    const form = $("contactForm");
    if (!form) return;
    const status = $("contactStatus");
    const submit = $("contactSubmit");
    const setStatus = (msg, kind) => {
      status.textContent = msg;
      status.className = `text-xs font-bold ${kind === "ok" ? "text-emerald-600" : kind === "err" ? "text-rose-600" : "text-slate-500"}`;
    };
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const name = String(fd.get("name") || "").trim();
      const contact = String(fd.get("contact") || "").trim();
      const message = String(fd.get("message") || "").trim();
      const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(contact);
      const isPhone = contact.replace(/\D/g, "").length >= 8;
      if (!name) return setStatus("Vui lòng nhập họ và tên.", "err");
      if (!isEmail && !isPhone) return setStatus("Vui lòng nhập email hoặc số điện thoại hợp lệ.", "err");
      if (!fd.get("consent")) return setStatus("Vui lòng đồng ý để chúng tôi liên hệ lại.", "err");
      submit.disabled = true;
      setStatus("Đang gửi...", "");
      try {
        const resp = await fetch("/api/contact", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, contact, topic: fd.get("topic"), message, website: fd.get("website") || "" }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || "Không gửi được yêu cầu.");
        form.reset();
        setStatus("Đã nhận yêu cầu. Cảm ơn bạn, chúng tôi sẽ phản hồi sớm.", "ok");
        toast("Đã gửi yêu cầu tư vấn!");
      } catch (err) {
        setStatus(err.message || "Có lỗi xảy ra, vui lòng thử lại.", "err");
      } finally {
        submit.disabled = false;
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Live chat (Trợ lý AI thông minh + thông tin Hà Thuỳ Dương)          */
  /* ------------------------------------------------------------------ */
  const DUONG_BIO =
    "Hà Thuỳ Dương là một cô sinh viên ngành Quản trị Kinh doanh đầy năng nổ của Học viện Công nghệ Bưu chính Viễn thông (PTIT), đồng thời là Trưởng ban Sự kiện nhiệt huyết của câu lạc bộ Business Creators Club (BCC). Không chỉ vậy, Dương sinh ngày 24/3/2007, hiện đang sống tại Hà Nội và có lịch trình khá bận rộn với các dự án, sự kiện sinh viên — đồng thời là người phát triển hệ thống Data Analyst & BI này!";
  const BOT = [
    { re: /(ha thuy duong|thuy duong|duong la ai|ban la ai|chu trang|tac gia|ptit|bcc|business creators|sinh ngay|24\/3|2007|o dau|hoc truong|nganh gi)/, a: DUONG_BIO },
    { re: /(dinh dang|file|excel|word|pdf|csv|json|doc)/, a: "Mình đọc được Excel (.xlsx/.xls/.ods), CSV, Word, PDF, JSON, XML, HTML, Markdown, ZIP, ảnh, và link Google Sheet / Lark Base. File lỗi sẽ được báo ngay để bạn gửi lại." },
    { re: /(bao mat|an toan|rieng tu|du lieu co)/, a: "Dữ liệu được xử lý ngay trên máy chủ cục bộ. Chỉ khi bạn bật Gemini/OpenAI trong Cài đặt thì nội dung mới gửi tới nhà cung cấp đó. Xem thêm ở Chính sách bảo mật." },
    { re: /(san pham|ban giao|ket qua|dau ra|bao cao|dashboard)/, a: "Bạn nhận 4 sản phẩm: Excel dữ liệu sạch, Excel tổng hợp kèm biểu đồ, Dashboard (xuất HTML) và báo cáo Word/PDF 10 mục." },
    { re: /(loi|gui lai|khong doc|that bai)/, a: "Nếu AI không đọc được hoặc làm sạch không thành công, hệ thống báo lỗi và hiện khung gửi lại file ngay trong màn hình xử lý." },
    { re: /(lien he|tu van|hotline|goi|email|sdt|so dien thoai|facebook|instagram|tiktok)/, a: "Bạn có thể liên hệ Hà Thuỳ Dương qua SĐT/Hotline 0332 125 570, Email htd24307@gmail.com, hoặc để lại thông tin ngay tại mục Liên hệ trên trang!" },
    { re: /(xin chao|hello|hi\b|chao)/, a: "Xin chào! Mình là Trợ lý AI của Hà Thuỳ Dương. Bạn có thể hỏi mình bất cứ điều gì về Hà Thuỳ Dương (PTIT · BCC), cách phân tích dữ liệu, hoặc nhờ tư vấn nhé!" },
  ];
  const QUICK = ["Hà Thuỳ Dương là ai?", "Đọc được định dạng nào?", "Nhận được sản phẩm nào?", "Dữ liệu có an toàn không?", "Liên hệ tư vấn"];
  const chatHistory = [];

  function chatAdd(text, who) {
    const log = $("chatLog");
    if (!log) return;
    const div = document.createElement("div");
    div.className = `chat-msg ${who}`;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    chatHistory.push({ role: who, text });
    return div;
  }
  async function chatReply(q) {
    const n = norm(q);
    const hit = BOT.find((b) => b.re.test(n));
    const typingEl = chatAdd("Đang suy nghĩ...", "bot");
    let text = "";

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, history: chatHistory.slice(-8), lang }),
      });
      if (resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (data.reply) text = data.reply;
      }
    } catch (_) {
      /* fallback to local rules below */
    }

    if (!text) {
      text = hit
        ? hit.a
        : "Mình đã ghi nhận câu hỏi của bạn! Nếu cần trao đổi trực tiếp với Hà Thuỳ Dương (PTIT · BCC), bạn có thể gọi 0332 125 570, email htd24307@gmail.com hoặc điền biểu mẫu ở mục Liên hệ nhé.";
    }

    if (typingEl) {
      typingEl.textContent = text;
      chatHistory[chatHistory.length - 1] = { role: "bot", text };
    } else {
      chatAdd(text, "bot");
    }

    if (/lien he|tu van|hotline|email/.test(n)) {
      const log = $("chatLog");
      const a = document.createElement("a");
      a.href = "/lien-he";
      a.setAttribute("data-route", "");
      a.className = "chat-link";
      a.textContent = "Mở biểu mẫu liên hệ →";
      a.addEventListener("click", () => closeChat());
      log.appendChild(a);
      log.scrollTop = log.scrollHeight;
    }
  }
  function initChat() {
    const quick = $("chatQuick");
    if (quick) {
      quick.innerHTML = QUICK.map((q) => `<button type="button">${q}</button>`).join("");
      quick.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        chatAdd(b.textContent, "me");
        chatReply(b.textContent);
      });
    }
    $("chatForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("chatInput");
      const v = input.value.trim();
      if (!v) return;
      chatAdd(v, "me");
      input.value = "";
      chatReply(v);
    });
    chatAdd("Xin chào! Mình là trợ lý tự động của Hà Thuỳ Dương. Bạn cần hỏi gì?", "bot");
  }
  window.openChat = () => {
    const p = $("chatPanel");
    if (!p) return;
    p.classList.remove("hidden");
    p.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => p.classList.add("is-open"));
    $("chatFab")?.classList.add("is-hidden");
    $("chatInput")?.focus();
  };
  window.closeChat = () => {
    const p = $("chatPanel");
    if (!p || p.classList.contains("hidden")) return;
    p.classList.remove("is-open");
    p.setAttribute("aria-hidden", "true");
    setTimeout(() => p.classList.add("hidden"), reduceMotion ? 0 : 220);
    $("chatFab")?.classList.remove("is-hidden");
  };

  /* ------------------------------------------------------------------ */
  /* Nav dropdown keyboard + outside click                               */
  /* ------------------------------------------------------------------ */
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#mobileMenu") && !e.target.closest("#menuToggle")) closeMobileMenu();
  });

  window.enterMainSite = (e) => {
    const sp = $("welcomeSplash");
    if (!sp) return;
    if (e && typeof spawnSparkles === "function" && e.clientX > 0) {
      spawnSparkles(e.clientX, e.clientY, 18);
    }
    sp.classList.add("is-hidden");
    try {
      sessionStorage.setItem("entered_site", "1");
    } catch (_) {
      /* ignore */
    }
    if (!currentUser) {
      openAuthModal();
      switchAuthTab("register");
    }
  };

  /* ------------------------------------------------------------------ */
  /* Theme (Sáng / Tối)                                                  */
  /* ------------------------------------------------------------------ */
  let theme = "light";
  function applyTheme(next) {
    theme = next === "dark" ? "dark" : "light";
    document.documentElement.classList.toggle("dark", theme === "dark");
    const icon = $("themeIcon");
    if (icon) icon.className = theme === "dark" ? "fa-solid fa-sun text-amber-300" : "fa-solid fa-moon";
    document.querySelectorAll(".themeLabelMobile").forEach((n) => (n.textContent = theme === "dark" ? "Sáng" : "Tối"));
    const tc = document.querySelector('meta[name="theme-color"]');
    if (tc) tc.setAttribute("content", theme === "dark" ? "#18101c" : "#ffd0e3");
    try {
      localStorage.setItem("site_theme", theme);
    } catch (_) {
      /* ignore */
    }
  }
  window.toggleTheme = () => applyTheme(theme === "dark" ? "light" : "dark");

  /* ------------------------------------------------------------------ */
  /* Auth (Đăng nhập / Tạo tài khoản) & Thống kê riêng của Admin        */
  /* ------------------------------------------------------------------ */
  let currentUser = null;
  let authMode = "register";
  const closeAdminStatsModal = () => {
    const m = $("adminStatsModal");
    if (!m) return;
    m.classList.add("hidden");
    m.classList.remove("flex");
  };
  window.closeAdminStatsModal = closeAdminStatsModal;

  const escTxt = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  function renderAuthUI() {
    const lbl = $("authHeaderLabel");
    const adminBtn = $("btnAdminStats");
    const statsLbl = $("btnStatsLabel");
    const profPane = $("authProfilePane");
    const formPane = $("authFormPane");
    const profAdmin = $("btnProfileAdminStats");
    const closeBtn = $("btnCloseAuthModal");
    const reqNotice = $("authRequiredNotice");

    if (currentUser) {
      if (lbl) lbl.textContent = currentUser.display_name || currentUser.username;
      const isAdmin = currentUser.role === "admin";
      if (adminBtn) {
        adminBtn.classList.remove("hidden");
        adminBtn.classList.add("flex");
      }
      if (statsLbl) {
        statsLbl.textContent = isAdmin ? "Thống kê Admin" : "Thống kê của tôi";
      }
      if (profAdmin) {
        profAdmin.classList.remove("hidden");
        profAdmin.textContent = isAdmin
          ? "📊 Xem thống kê toàn bộ hệ thống (Admin)"
          : "📊 Xem thống kê cá nhân của tôi";
      }
      if (closeBtn) closeBtn.classList.remove("hidden");
      if (reqNotice) reqNotice.classList.add("hidden");
      if (profPane) profPane.classList.remove("hidden");
      if (formPane) formPane.classList.add("hidden");
      if ($("authAvatarLetter")) $("authAvatarLetter").textContent = (currentUser.display_name || "U").charAt(0).toUpperCase();
      if ($("authProfileName")) $("authProfileName").textContent = currentUser.display_name || currentUser.username;
      if ($("authProfileMeta")) {
        const phonePart = currentUser.phone ? ` · SĐT ${currentUser.phone}` : "";
        $("authProfileMeta").textContent = `${currentUser.username}${phonePart} · ${isAdmin ? "Quản trị viên (Chủ sở hữu)" : "Thành viên"}`;
      }
    } else {
      if (lbl) lbl.textContent = "Đăng ký / Đăng nhập";
      if (adminBtn) {
        adminBtn.classList.add("hidden");
        adminBtn.classList.remove("flex");
      }
      if (closeBtn) closeBtn.classList.add("hidden");
      if (reqNotice) reqNotice.classList.remove("hidden");
      if (profPane) profPane.classList.add("hidden");
      if (formPane) formPane.classList.remove("hidden");
    }
  }

  window.switchAuthTab = (mode) => {
    authMode = mode === "login" || mode === "forgot" ? mode : "register";
    const isReg = authMode === "register";
    const isForgot = authMode === "forgot";

    $("authForm")?.classList.toggle("hidden", isForgot);
    $("authForgotPane")?.classList.toggle("hidden", !isForgot);

    $("authNameWrap")?.classList.toggle("hidden", !isReg);
    $("authPhoneWrap")?.classList.toggle("hidden", !isReg);
    if ($("authDisplayName")) $("authDisplayName").required = isReg;
    if ($("authPhone")) $("authPhone").required = isReg;
    if ($("authSubmitBtn")) {
      $("authSubmitBtn").textContent = isReg ? "Tạo tài khoản & Bắt đầu" : "Đăng nhập";
    }

    const activeCls = "py-2 rounded-xl bg-gradient-to-r from-pink-400 to-rose-400 text-white";
    const idleCls = "py-2 rounded-xl text-slate-600";
    if ($("tabAuthRegister")) $("tabAuthRegister").className = isReg ? activeCls : idleCls;
    if ($("tabAuthLogin")) $("tabAuthLogin").className = authMode === "login" ? activeCls : idleCls;
    if ($("tabAuthForgot")) $("tabAuthForgot").className = isForgot ? activeCls : idleCls;

    $("authErrorBox")?.classList.add("hidden");
    $("forgotErrorBox")?.classList.add("hidden");
  };

  window.openAuthModal = () => {
    const m = $("authModal");
    if (!m) return;
    renderAuthUI();
    m.classList.remove("hidden");
    m.classList.add("flex");
  };
  window.closeAuthModal = () => {
    if (!currentUser) {
      toast("Vui lòng tạo tài khoản hoặc đăng nhập để sử dụng hệ thống.");
      return;
    }
    const m = $("authModal");
    if (!m) return;
    m.classList.add("hidden");
    m.classList.remove("flex");
  };
  $("authModal")?.addEventListener("click", (e) => {
    if (e.target === $("authModal")) window.closeAuthModal();
  });

  window.logoutUser = async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    currentUser = null;
    renderAuthUI();
    closeAdminStatsModal();
    window.openAuthModal();
    window.switchAuthTab("login");
    toast("Đã đăng xuất! Vui lòng đăng nhập lại.");
  };

  window.sendForgotOtp = async () => {
    const errBox = $("forgotErrorBox");
    const notice = $("forgotOtpNotice");
    errBox?.classList.add("hidden");
    notice?.classList.add("hidden");
    const phone = ($("forgotPhone")?.value || "").trim();
    if (!phone) {
      if (errBox) {
        errBox.textContent = "Vui lòng nhập số điện thoại đã đăng ký.";
        errBox.classList.remove("hidden");
      }
      return;
    }
    try {
      const resp = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Không gửi được mã OTP.");
      if (notice) {
        notice.innerHTML = `${escTxt(data.message || "Đã gửi mã OTP.")}${data.demo_otp ? `<div class="mt-1 text-sm font-black text-pink-700">Mã OTP xác nhận (SĐT ${escTxt(data.phone || phone)}): <span class="px-2 py-0.5 rounded bg-white border border-pink-200">${escTxt(data.demo_otp)}</span></div>` : ""}`;
        notice.classList.remove("hidden");
      }
      toast("Đã gửi mã xác nhận về SĐT!");
    } catch (err) {
      if (errBox) {
        errBox.textContent = err.message;
        errBox.classList.remove("hidden");
      }
    }
  };

  window.submitPasswordReset = async () => {
    const errBox = $("forgotErrorBox");
    errBox?.classList.add("hidden");
    const phone = ($("forgotPhone")?.value || "").trim();
    const otp_code = ($("forgotOtpCode")?.value || "").trim();
    const new_password = $("forgotNewPassword")?.value || "";
    if (!phone || !otp_code || !new_password) {
      if (errBox) {
        errBox.textContent = "Vui lòng nhập đầy đủ SĐT, mã OTP và mật khẩu mới.";
        errBox.classList.remove("hidden");
      }
      return;
    }
    try {
      const resp = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, otp_code, new_password }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Không đặt lại được mật khẩu.");
      toast(data.message || "Đặt lại mật khẩu thành công!");
      if ($("authUsername") && phone) $("authUsername").value = phone;
      window.switchAuthTab("login");
    } catch (err) {
      if (errBox) {
        errBox.textContent = err.message;
        errBox.classList.remove("hidden");
      }
    }
  };

  window.openStatsModal = async () => {
    const m = $("adminStatsModal");
    const body = $("adminStatsBody");
    const titleEl = $("statsModalTitle");
    if (!m || !body) return;
    if (!currentUser) {
      window.openAuthModal();
      return;
    }
    const isAdmin = currentUser.role === "admin";
    if (titleEl) {
      titleEl.textContent = isAdmin
        ? "📊 Thống kê Toàn hệ thống (Chỉ Admin — Hà Thuỳ Dương)"
        : `📊 Thống kê Cá nhân (${currentUser.display_name || currentUser.username})`;
    }
    m.classList.remove("hidden");
    m.classList.add("flex");
    body.innerHTML = `<p class="text-slate-500 font-semibold">Đang tải thống kê...</p>`;
    try {
      const endpoint = isAdmin ? "/api/admin/stats" : "/api/user/my-stats";
      const resp = await fetch(endpoint);
      const data = await resp.json();
      if (!resp.ok) {
        body.innerHTML = `<div class="p-4 rounded-2xl bg-rose-50 text-rose-700 font-bold">${escTxt(data.error || "Không có quyền truy cập.")}</div>`;
        return;
      }

      if (!isAdmin) {
        const u = data.user || {};
        const s = data.summary || {};
        const actsHtml = (data.recent_activity || []).length
          ? data.recent_activity
              .map(
                (a) =>
                  `<div class="flex justify-between py-1.5 border-b border-pink-50"><span>${escTxt(a.path || "/")} <span class="text-slate-400">(${escTxt(a.device || "Web")})</span></span><span class="text-slate-500">${escTxt((a.ts || "").slice(0, 16).replace("T", " "))}</span></div>`
              )
              .join("")
          : `<div class="text-slate-400">Chưa có lịch sử hoạt động.</div>`;
        body.innerHTML = `
          <div class="p-3.5 rounded-2xl bg-emerald-50/80 border border-emerald-200 text-emerald-900 font-bold">
            🔒 Chế độ riêng tư: Bạn chỉ xem được dữ liệu tài khoản của chính mình (không thể xem thông tin của người dùng khác).
          </div>
          <div class="grid grid-cols-3 gap-3 text-center">
            <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Lượt truy cập của bạn</div><div class="text-xl font-extrabold text-pink-700 mt-0.5">${s.my_visits || 0}</div></div>
            <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Lần phân tích dữ liệu</div><div class="text-xl font-extrabold text-orange-700 mt-0.5">${s.my_analysis_runs || 0}</div></div>
            <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Tin nhắn Chat AI</div><div class="text-xl font-extrabold text-emerald-700 mt-0.5">${s.my_chat_messages || 0}</div></div>
          </div>
          <div class="p-3.5 rounded-2xl bg-white/80 border border-white space-y-1.5">
            <div class="font-extrabold text-pink-900">👤 Thông tin tài khoản của bạn</div>
            <div>Tên hiển thị: <strong>${escTxt(u.display_name)}</strong> · Tài khoản: <strong>${escTxt(u.username)}</strong> · SĐT: <strong>${escTxt(u.phone || "—")}</strong></div>
            <div class="text-slate-500">Ngày tạo: ${escTxt((u.created_at || "").slice(0, 16).replace("T", " "))} · Đăng nhập gần nhất: ${escTxt((u.last_login_at || "").slice(0, 16).replace("T", " "))}</div>
          </div>
          <div class="p-3.5 rounded-2xl bg-white/80 border border-white space-y-2 max-h-56 overflow-y-auto">
            <div class="font-extrabold text-pink-900">🕒 Hoạt động gần đây của bạn</div>
            <div class="text-[11px]">${actsHtml}</div>
          </div>`;
        return;
      }

      const s = data.summary || {};
      const usersHtml = (data.users || [])
        .map(
          (u) => `
        <tr class="border-t border-pink-50">
          <td class="p-2 font-extrabold text-slate-800">${escTxt(u.display_name)}</td>
          <td class="p-2 text-slate-600">${escTxt(u.username)}</td>
          <td class="p-2 text-slate-600">${escTxt(u.phone || "—")}</td>
          <td class="p-2"><span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold ${u.role === "admin" ? "bg-emerald-100 text-emerald-800" : "bg-pink-100 text-pink-700"}">${escTxt(u.role === "admin" ? "Admin (Chủ)" : "Thành viên")}</span></td>
          <td class="p-2 text-slate-500">${escTxt((u.created_at || "").slice(0, 16).replace("T", " "))}</td>
          <td class="p-2 text-slate-500">${escTxt((u.last_login_at || "").slice(0, 16).replace("T", " "))}</td>
        </tr>`
        )
        .join("");

      const pathsHtml = (data.top_paths || [])
        .map((p) => `<div class="flex justify-between py-1 border-b border-pink-50"><span>${escTxt(p.path)}</span><strong class="text-pink-700">${p.count}</strong></div>`)
        .join("");

      const devEntries = Object.entries(data.devices || {})
        .map(([k, v]) => `<span class="px-2.5 py-1 rounded-full bg-white border border-pink-100 font-bold">${escTxt(k)}: <strong class="text-pink-700">${v}</strong></span>`)
        .join(" ");

      const contactsHtml = (data.recent_contacts || []).length
        ? data.recent_contacts
            .map(
              (c) => `<div class="p-2.5 rounded-xl bg-white/80 border border-white"><strong>${escTxt(c.name)}</strong> (${escTxt(c.contact)}) · <span class="text-pink-700">${escTxt(c.topic)}</span><div class="text-slate-600 mt-0.5">${escTxt(c.message)}</div></div>`
            )
            .join("")
        : `<div class="text-slate-400">Chưa có yêu cầu liên hệ nào.</div>`;

      body.innerHTML = `
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Tổng lượt truy cập</div><div class="text-xl font-extrabold text-pink-700 mt-0.5">${s.total_visits || 0}</div><div class="text-[10px] text-emerald-600 font-bold">Hôm nay: ${s.visits_today || 0}</div></div>
          <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Người dùng duy nhất</div><div class="text-xl font-extrabold text-slate-800 mt-0.5">${s.unique_visitors || 0}</div></div>
          <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Tài khoản đã tạo</div><div class="text-xl font-extrabold text-orange-700 mt-0.5">${s.registered_users || 0}</div></div>
          <div class="p-3 rounded-2xl bg-white/85 border border-white"><div class="text-slate-500 font-bold">Phân tích · Chat AI</div><div class="text-xl font-extrabold text-emerald-700 mt-0.5">${s.analysis_runs || 0} · ${s.chat_messages || 0}</div></div>
        </div>
        <div class="grid md:grid-cols-2 gap-3">
          <div class="p-3.5 rounded-2xl bg-white/80 border border-white space-y-2">
            <div class="font-extrabold text-pink-900">📱 Thiết bị &amp; Trang xem nhiều</div>
            <div class="flex flex-wrap gap-2">${devEntries || "Chưa có dữ liệu"}</div>
            <div class="pt-1 text-[11px]">${pathsHtml || ""}</div>
          </div>
          <div class="p-3.5 rounded-2xl bg-white/80 border border-white space-y-2 max-h-48 overflow-y-auto">
            <div class="font-extrabold text-pink-900">📩 Yêu cầu tư vấn gần đây (${s.contact_requests || 0})</div>
            <div class="space-y-1.5">${contactsHtml}</div>
          </div>
        </div>
        <div class="p-3.5 rounded-2xl bg-white/80 border border-white space-y-2">
          <div class="font-extrabold text-pink-900">👥 Danh sách tài khoản đã đăng ký (${(data.users || []).length})</div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-[11px]">
              <thead class="bg-pink-50 text-pink-900 font-extrabold"><tr><th class="p-2">Tên hiển thị</th><th class="p-2">Tài khoản</th><th class="p-2">SĐT</th><th class="p-2">Vai trò</th><th class="p-2">Ngày tạo</th><th class="p-2">Đăng nhập cuối</th></tr></thead>
              <tbody>${usersHtml || `<tr><td colspan="6" class="p-3 text-slate-400">Chưa có tài khoản nào.</td></tr>`}</tbody>
            </table>
          </div>
        </div>`;
    } catch (err) {
      body.innerHTML = `<div class="p-4 rounded-2xl bg-rose-50 text-rose-700 font-bold">Lỗi tải thống kê: ${escTxt(err.message)}</div>`;
    }
  };
  window.openAdminStatsModal = window.openStatsModal;
  $("adminStatsModal")?.addEventListener("click", (e) => {
    if (e.target === $("adminStatsModal")) closeAdminStatsModal();
  });

  async function initAuthAndAdmin() {
    window.switchAuthTab("register");
    $("authForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = $("authErrorBox");
      errBox?.classList.add("hidden");
      const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
      const payload = {
        display_name: ($("authDisplayName")?.value || "").trim(),
        username: ($("authUsername")?.value || "").trim(),
        phone: ($("authPhone")?.value || "").trim(),
        password: $("authPassword")?.value || "",
      };
      try {
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || "Thao tác thất bại.");
        currentUser = data.user;
        renderAuthUI();
        window.closeAuthModal();
        toast(authMode === "register" ? `Chào mừng ${currentUser.display_name}!` : `Đã đăng nhập: ${currentUser.display_name}`);
      } catch (err) {
        if (errBox) {
          errBox.textContent = err.message;
          errBox.classList.remove("hidden");
        }
      }
    });

    try {
      const sResp = await fetch("/api/site-settings");
      if (sResp.ok) {
        const st = await sResp.json();
        if (st.site_title) document.title = st.site_title;
        if (st.announcement_bar || st.maintenance_mode) {
          let bar = document.getElementById("liveAdminAnnouncement");
          if (!bar) {
            bar = document.createElement("div");
            bar.id = "liveAdminAnnouncement";
            bar.className = "no-print text-center text-xs font-extrabold py-2 px-4 bg-gradient-to-r from-pink-500 via-rose-500 to-orange-400 text-white shadow";
            document.body.prepend(bar);
          }
          bar.textContent = st.maintenance_mode
            ? `🛠️ Hệ thống đang bảo trì nhẹ${st.announcement_bar ? " · " + st.announcement_bar : ""}`
            : st.announcement_bar;
        }
      }
    } catch (_) {
      /* ignore */
    }

    try {
      const resp = await fetch("/api/auth/me");
      if (resp.ok) {
        const data = await resp.json();
        currentUser = data.user || null;
        renderAuthUI();
        if (!currentUser && sessionStorage.getItem("entered_site") === "1") {
          window.openAuthModal();
          window.switchAuthTab("register");
        }
      }
    } catch (_) {
      /* ignore */
    }
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                                */
  /* ------------------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", () => {
    initAuthAndAdmin();
    try {
      if (sessionStorage.getItem("entered_site") === "1") {
        $("welcomeSplash")?.classList.add("is-hidden");
      }
    } catch (_) {
      /* ignore */
    }
    try {
      applyTheme(localStorage.getItem("site_theme") || "light");
    } catch (_) {
      applyTheme("light");
    }
    try {
      applyLang(localStorage.getItem("site_lang") || "vi");
    } catch (_) {
      applyLang("vi");
    }
    bindSiteConfig();
    const desk = bindSearch("siteSearchInput", "siteSearchResults");
    bindSearch("mobileSearchInput", "mobileSearchResults");
    initReveal();
    initContactForm();
    initChat();
    onScroll();

    const q = new URLSearchParams(location.search).get("q");
    if (q && desk) {
      desk.input.value = q;
      desk.input.dispatchEvent(new Event("input"));
    }

    // initial route (server returns index.html for every known path)
    applyRoute(location.pathname, { history: "replace", noScroll: normPath(location.pathname) === "/" });
  });
})();
