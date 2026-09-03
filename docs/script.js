// DIL DEGISTIRME BURADA DEGIL. Iki ayri sayfa var: / (Ingilizce) ve /tr/
// (Turkce, docs/index.html'den uretiliyor). Gecis duz baglantiyla oluyor.
//
// Onceden burada bir dil dugmesi mantigi vardi: `data-lang` degistirilip
// CSS ile oteki dilin span'leri gizleniyordu. /tr/ sayfasi cikinca bu
// YANLIS oldu ve iki somut kusur uretti:
//   - sunucu kok URL'de Ingilizce HTML gonderdigi hâlde tarayici dili
//     Turkce olan (ya da daha once TR'ye tiklamis) ziyaretci orada Turkce
//     sayfa goruyordu; /tr/ ise ayri duruyordu, hangi URL hangi dil belli
//     degildi
//   - ayni betik /tr/ sayfasinda da yukleniyor ve kayitli tercih "en" ise
//     BUTUN Turkce span'leri gizliyordu: sayfa bombos aciliyordu
//
// Artik her sayfanin dili statik HTML'de sabit; JS'in dile dokunmasi yok.
// SSS icin de JS gerekmiyor, yerlesik <details> kullaniliyor.

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
