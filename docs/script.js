// Language toggle (EN / TR). SSS uses native <details>, so JS only handles language.
(function () {
  "use strict";
  var root = document.documentElement;
  var btn = document.getElementById("lang-toggle");
  var KEY = "latex-editor-lang";

  // TEK DILLI SAYFADA HIC CALISMA. /tr/ sayfasi bu dosyayi da yukluyor ama
  // orada `.en` span'leri hic yok ve dugme yerine koke giden bir baglanti
  // var, yani `#lang-toggle` bulunamiyor. Bu erken cikis olmadan
  // apply(resolveInitial()) kayitli tercih "en" ise (ya da tarayici dili
  // Ingilizce ise) data-lang="en" yaziyordu; CSS o durumda BUTUN `.tr`
  // span'lerini gizledigi icin /tr/ sayfasi bombos aciliyordu.
  // Statik `data-lang` uretilen sayfada zaten dogru.
  if (!btn) return;

  function resolveInitial() {
    // `?lang=en` ACIK BIR SECIMDIR, kayitli tercihi de ezer ve yerine
    // gecer. /tr/ sayfasindaki "EN" baglantisi buraya bunu ekleyerek
    // geliyor: onceki tercih "tr" olsaydi kullanici EN'e tikladigi hâlde
    // yine Turkce sayfa aciliyordu.
    var q = /[?&]lang=(en|tr)\b/.exec(location.search);
    if (q) {
      try { localStorage.setItem(KEY, q[1]); } catch (e) {}
      return q[1];
    }
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    if (saved === "en" || saved === "tr") return saved;
    var nav = (navigator.language || "en").toLowerCase();
    return nav.indexOf("tr") === 0 ? "tr" : "en";
  }

  // Sekme basligi. <title> element iceremedigi icin iki dilli span numarasi
  // orada calismiyor; statik baslik HTML'de tek dilde duruyor (arama motoru
  // onu goruyor) ve kullaniciya gore burada degistiriliyor.
  var BASLIKLAR = {
    en: "LaTeX Editor: desktop LaTeX editor with live PDF preview",
    tr: "LaTeX Editor: canlı PDF önizlemeli masaüstü LaTeX editörü"
  };

  function apply(lang) {
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang);
    if (BASLIKLAR[lang]) document.title = BASLIKLAR[lang];
    btn.textContent = lang === "en" ? "TR" : "EN";
  }

  apply(resolveInitial());

  btn.addEventListener("click", function () {
    var next = root.getAttribute("data-lang") === "tr" ? "en" : "tr";
    try { localStorage.setItem(KEY, next); } catch (e) {}
    apply(next);
  });
})();

// Copy-to-clipboard for command blocks
document.querySelectorAll(".copy-btn").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var code = btn.parentElement.querySelector("code");
    if (!code) return;
    var text = code.textContent.replace(/ /g, " ");
    var mark = function () {
      var orig = btn.innerHTML;
      btn.classList.add("copied");
      btn.textContent = "✓";
      setTimeout(function () { btn.classList.remove("copied"); btn.innerHTML = orig; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(mark, function () {});
    } else {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); mark(); } catch (e) {}
      document.body.removeChild(ta);
    }
  });
});
