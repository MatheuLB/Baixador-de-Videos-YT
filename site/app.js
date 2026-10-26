// Site do Baixador de Vídeos.
// 1. Busca a versão mais recente na API do GitHub e troca os links pelos
//    arquivos certos (sem JavaScript, ou se a API falhar, os botões levam
//    para a página de releases, que sempre funciona).
// 2. Reconhece o sistema de quem visita e mostra o botão certo no topo.
// 3. Abas de instalação e botões de copiar.

(function () {
  "use strict";

  var REPO = "MatheuLB/Baixador-de-Videos-YT";
  var API = "https://api.github.com/repos/" + REPO + "/releases/latest";
  var CACHE_KEY = "baixador-release";
  var CACHE_MINUTES = 30;

  // ---------------------------------------------------------------- sistema

  function detectOS() {
    var ua = navigator.userAgent || "";
    var platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    if (/android|iphone|ipad|ipod/i.test(ua) || (/mac/i.test(platform) && navigator.maxTouchPoints > 1)) return "mobile";
    if (/win/i.test(platform) || /windows/i.test(ua)) return "windows";
    if (/mac/i.test(platform) || /mac os x/i.test(ua)) return "mac";
    if (/linux|x11|cros/i.test(platform + " " + ua)) return "linux";
    return "unknown";
  }

  // No Chrome/Edge dá para saber se o Mac é Apple Silicon; no Safari, não.
  function detectMacArch() {
    var data = navigator.userAgentData;
    if (!data || !data.getHighEntropyValues) return Promise.resolve(null);
    return data.getHighEntropyValues(["architecture"]).then(function (v) {
      if (v.architecture === "arm") return "apple-silicon";
      if (v.architecture === "x86") return "intel";
      return null;
    }).catch(function () { return null; });
  }

  // ---------------------------------------------------------------- release

  function readCache() {
    try {
      var raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (Date.now() - cached.time > CACHE_MINUTES * 60000) return null;
      return cached.release;
    } catch (e) { return null; }
  }

  function writeCache(release) {
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ time: Date.now(), release: release })); } catch (e) { /* sem cache */ }
  }

  function fetchRelease() {
    var cached = readCache();
    if (cached) return Promise.resolve(cached);
    return fetch(API, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        var release = { version: String(data.tag_name || "").replace(/^v/, ""), date: data.published_at, assets: {} };
        (data.assets || []).forEach(function (asset) {
          // "Baixador-1.0.0-windows-x64-instalador.exe" -> "windows-x64-instalador.exe"
          var match = /^Baixador-[^-]+-(.+)$/.exec(asset.name);
          if (match) release.assets[match[1]] = { url: asset.browser_download_url, size: asset.size };
        });
        writeCache(release);
        return release;
      });
  }

  function formatSize(bytes) {
    return Math.round(bytes / 1048576) + " MB";
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" });
    } catch (e) { return ""; }
  }

  function applyRelease(release) {
    if (release.version) {
      document.querySelectorAll("[data-version]").forEach(function (el) { el.textContent = release.version; });
    }
    if (release.date) {
      document.querySelectorAll("[data-date]").forEach(function (el) { el.textContent = ", publicada em " + formatDate(release.date); });
    }
    document.querySelectorAll("[data-asset]").forEach(function (link) {
      var asset = release.assets[link.getAttribute("data-asset")];
      if (!asset) return;
      link.href = asset.url;
      var size = link.querySelector("[data-size]");
      if (size) size.textContent = "· " + formatSize(asset.size);
    });
  }

  // ---------------------------------------------------------------- topo

  function assetLink(key) {
    var link = document.querySelector('.platforms [data-asset="' + key + '"]');
    return link ? link.href : "#download";
  }

  function button(label, key, primary) {
    var a = document.createElement("a");
    a.className = "btn btn-lg " + (primary ? "btn-primary" : "btn-secondary");
    a.setAttribute("data-asset", key);
    a.href = assetLink(key);
    a.innerHTML = '<svg class="icon"><use href="#i-download"/></svg>';
    a.appendChild(document.createTextNode(label));
    return a;
  }

  function note(html) {
    var p = document.createElement("p");
    p.className = "cta-note";
    p.innerHTML = html;
    return p;
  }

  function renderHeroCTA(os, macArch) {
    var box = document.getElementById("hero-cta");
    if (!box) return;
    box.textContent = "";
    if (os === "windows") {
      box.appendChild(button("Baixar para Windows", "windows-x64-instalador.exe", true));
      box.appendChild(note('Windows 10 e 11 · ou <a href="' + assetLink("windows-x64-portatil.zip") + '" data-asset="windows-x64-portatil.zip">versão portátil (.zip)</a>'));
    } else if (os === "mac" && macArch) {
      var other = macArch === "apple-silicon" ? "intel" : "apple-silicon";
      var label = macArch === "apple-silicon" ? "Baixar para Mac (Chip Apple)" : "Baixar para Mac (Intel)";
      var otherLabel = other === "intel" ? "processador Intel" : "chip Apple";
      box.appendChild(button(label, "macos-" + macArch + ".dmg", true));
      box.appendChild(note('macOS 12 ou mais novo · Mac com ' + otherLabel + '? <a href="' + assetLink("macos-" + other + ".dmg") + '" data-asset="macos-' + other + '.dmg">Baixe aqui</a>'));
    } else if (os === "mac") {
      box.appendChild(button("Mac com chip Apple", "macos-apple-silicon.dmg", true));
      box.appendChild(button("Mac com Intel", "macos-intel.dmg", false));
      box.appendChild(note('Não sabe qual é o seu? <a href="#qual-mac" data-open-hint>Veja como descobrir</a>'));
    } else if (os === "linux") {
      box.appendChild(button("Baixar para Linux", "linux-x64.AppImage", true));
      box.appendChild(note('AppImage, roda na maioria das distribuições · ou <a href="' + assetLink("linux-x64.tar.gz") + '" data-asset="linux-x64.tar.gz">.tar.gz</a>'));
    } else {
      var a = document.createElement("a");
      a.className = "btn btn-primary btn-lg";
      a.href = "#download";
      a.innerHTML = '<svg class="icon"><use href="#i-download"/></svg>Ver downloads';
      box.appendChild(a);
      if (os === "mobile") {
        box.appendChild(note("O Baixador é um app para computador. Abra esta página no Windows, no Mac ou no Linux para instalar."));
      }
    }
  }

  function highlightPlatform(os, macArch) {
    var card = document.querySelector('.platform[data-os="' + os + '"]');
    if (card) card.classList.add("is-current");
    if (os === "mac" && macArch === "intel") {
      // Deixa o botão Intel como principal e o do chip Apple como secundário.
      var intel = document.querySelector('.mac-option[data-arch="intel"] .btn');
      var apple = document.querySelector('.mac-option[data-arch="apple-silicon"] .btn');
      if (intel && apple) {
        intel.classList.replace("btn-secondary", "btn-primary");
        apple.classList.replace("btn-primary", "btn-secondary");
      }
    }
  }

  // ---------------------------------------------------------------- abas

  function setupTabs(initial) {
    var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(tab, false); });
      tab.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (next) { e.preventDefault(); select(next, true); }
      });
    });
    var start = tabs.filter(function (t) { return t.getAttribute("data-tab") === initial; })[0];
    if (start) select(start, false);
  }

  // ---------------------------------------------------------------- copiar

  function setupCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = document.getElementById(btn.getAttribute("data-copy")).textContent;
        var done = function () {
          var label = btn.querySelector("span");
          btn.classList.add("done");
          label.textContent = "Copiado!";
          setTimeout(function () { btn.classList.remove("done"); label.textContent = "Copiar"; }, 2000);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { selectText(btn); });
        } else {
          selectText(btn);
        }
      });
    });
  }

  function selectText(btn) {
    var code = document.getElementById(btn.getAttribute("data-copy"));
    var range = document.createRange();
    range.selectNodeContents(code);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // O link "Veja como descobrir" abre a explicação dentro do cartão do Mac.
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("[data-open-hint]");
    if (link) {
      var hint = document.getElementById("qual-mac");
      if (hint) hint.open = true;
    }
  });

  // ---------------------------------------------------------------- início

  var os = detectOS();
  setupTabs(os === "mac" || os === "linux" ? os : "windows");
  setupCopy();

  var archPromise = os === "mac" ? detectMacArch() : Promise.resolve(null);
  archPromise.then(function (macArch) {
    renderHeroCTA(os, macArch);
    highlightPlatform(os, macArch);
    return fetchRelease().then(function (release) {
      applyRelease(release);
    }).catch(function () {
      // Sem a API, os botões continuam levando para a página de releases.
    });
  });
})();
