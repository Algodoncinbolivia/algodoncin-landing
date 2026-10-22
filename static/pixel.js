// Eventos del Píxel de Meta. Si el píxel no está activo, todo esto no hace nada.
// Nunca se envían nombres ni teléfonos: solo el tipo de acción.
(function () {
  window.track = function (evento, datos) {
    try {
      if (typeof window.fbq === "function") window.fbq("track", evento, datos || {});
    } catch (e) {}
  };

  // cualquier botón o enlace a WhatsApp cuenta como "Contact"
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href*="wa.me"]');
    if (!a) return;
    window.track("Contact", { content_name: a.id === "wa-foto" ? "whatsapp_foto_halloween" : "whatsapp" });
  });
})();
