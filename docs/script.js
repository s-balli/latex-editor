// Language toggle (EN / TR). SSS uses native <details>, so JS only handles language.
(function () {
  "use strict";
  var root = document.documentElement;
  var btn = document.getElementById("lang-toggle");
  var KEY = "latex-editor-lang";

  function resolveInitial() {
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    if (saved === "en" || saved === "tr") return saved;
    var nav = (navigator.language || "en").toLowerCase();
    return nav.indexOf("tr") === 0 ? "tr" : "en";
  }

  function apply(lang) {
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang);
    if (btn) btn.textContent = lang === "en" ? "TR" : "EN";
  }

  apply(resolveInitial());

  if (btn) {
    btn.addEventListener("click", function () {
      var next = root.getAttribute("data-lang") === "tr" ? "en" : "tr";
      try { localStorage.setItem(KEY, next); } catch (e) {}
      apply(next);
    });
  }
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
