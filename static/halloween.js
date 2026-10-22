(function () {
  var form = document.getElementById("form-registro");
  if (!form) return;

  var errorBox = document.getElementById("error");
  var boton = document.getElementById("enviar");
  var exito = document.getElementById("exito");
  var otroBox = document.getElementById("otro-box");
  var otroInput = document.getElementById("disfraz_otro");

  // de dónde llegó la persona (?f=tiktok, ?f=volante, ?utm_source=...) para saber qué trae más registros
  try {
    var q = new URLSearchParams(location.search);
    document.getElementById("fuente").value = q.get("f") || q.get("utm_source") || "";
  } catch (e) {}

  function valorDisfraz() {
    var marcado = form.querySelector('input[name="disfraz"]:checked');
    return marcado ? marcado.value : "";
  }

  form.addEventListener("change", function (ev) {
    if (ev.target.name !== "disfraz") return;
    var esOtro = ev.target.value === "Otro disfraz";
    otroBox.hidden = !esOtro;
    if (esOtro) otroInput.focus();
  });

  function mostrarError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    errorBox.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    errorBox.hidden = true;

    var datos = {
      nombre_nino: form.nombre_nino.value,
      nombre_adulto: form.nombre_adulto.value,
      whatsapp: form.whatsapp.value,
      disfraz: valorDisfraz(),
      disfraz_otro: otroInput.value,
      cantidad: form.cantidad.value,
      fuente: form.fuente.value,
      web: form.web.value,
      acepta: form.acepta.checked,
    };

    boton.disabled = true;
    var textoOriginal = boton.textContent;
    boton.textContent = "Guardando…";

    fetch("/api/halloween/registro", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, json: j }; });
      })
      .then(function (res) {
        if (!res.ok || !res.json.ok) {
          mostrarError(res.json.error || "No pudimos guardar tu registro. Inténtalo otra vez o escríbenos por WhatsApp.");
          return;
        }
        if (window.track) window.track("CompleteRegistration", { content_name: "halloween_2026", value: 0, currency: "BOB" });
        document.getElementById("wa-foto").href = res.json.wa_foto || "#";
        if (res.json.nombre_nino) {
          document.getElementById("exito-titulo").textContent = "¡Listo, " + res.json.nombre_nino + "!";
        }
        form.hidden = true;
        exito.hidden = false;
        exito.focus();
        exito.scrollIntoView({ block: "center", behavior: "smooth" });
      })
      .catch(function () {
        mostrarError("Parece que no hay conexión. Revisa tu internet e inténtalo otra vez.");
      })
      .then(function () {
        boton.disabled = false;
        boton.textContent = textoOriginal;
      });
  });
})();
