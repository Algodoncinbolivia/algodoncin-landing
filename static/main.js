(() => {
  const DOW = ["L", "M", "M", "J", "V", "S", "D"];
  const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

  const today = new Date(HOY + "T00:00:00");
  const state = {
    ciudad: document.getElementById("selCiudad").value,
    tipo: "evento",
    punto: null,
    viewYear: today.getFullYear(),
    viewMonth: today.getMonth(), // 0-indexed
    takenDates: new Set(),
    selectedDate: null,
  };

  const selCiudad = document.getElementById("selCiudad");
  const tipoWrap = document.getElementById("tipoWrap");
  const tipoToggle = document.getElementById("tipoToggle");
  const puntoWrap = document.getElementById("puntoWrap");
  const selPunto = document.getElementById("selPunto");
  const calTitle = document.getElementById("calTitle");
  const calDow = document.getElementById("calDow");
  const calGrid = document.getElementById("calGrid");
  const calPrev = document.getElementById("calPrev");
  const calNext = document.getElementById("calNext");
  const bookingCard = document.getElementById("bookingCard");

  DOW.forEach(d => {
    const el = document.createElement("div");
    el.className = "cal-dow";
    el.textContent = d;
    calDow.appendChild(el);
  });

  function updatePuntoVisibility() {
    const puntos = PUNTOS_FIJOS[state.ciudad] || [];
    const hasFijos = puntos.length > 0;
    tipoWrap.style.display = hasFijos ? "" : "none";
    if (!hasFijos) state.tipo = "evento";
    tipoToggle.querySelectorAll(".toggle-btn").forEach(b => b.classList.toggle("active", b.dataset.tipo === state.tipo));

    if (state.tipo === "punto_fijo" && hasFijos) {
      puntoWrap.style.display = "";
      selPunto.innerHTML = puntos.map(p => `<option value="${p}">${p}</option>`).join("");
      state.punto = puntos[0];
    } else {
      puntoWrap.style.display = "none";
      state.punto = null;
    }
  }

  async function fetchAvailability() {
    const mes = `${state.viewYear}-${String(state.viewMonth + 1).padStart(2, "0")}`;
    const res = await fetch(`/api/disponibilidad?ciudad=${encodeURIComponent(state.ciudad)}&mes=${mes}`);
    const data = await res.json();
    state.takenDates = new Set();
    if (Array.isArray(data)) {
      data.forEach(r => {
        const sameTipo = r.tipo === state.tipo;
        const samePunto = state.tipo !== "punto_fijo" || r.punto === state.punto;
        if (sameTipo && samePunto) state.takenDates.add(r.fecha);
      });
    }
  }

  function renderCalendar() {
    calTitle.textContent = `${MESES[state.viewMonth]} ${state.viewYear}`;
    calGrid.innerHTML = "";

    const firstOfMonth = new Date(state.viewYear, state.viewMonth, 1);
    let startOffset = firstOfMonth.getDay() - 1; // Monday-first
    if (startOffset < 0) startOffset = 6;

    const daysInMonth = new Date(state.viewYear, state.viewMonth + 1, 0).getDate();

    for (let i = 0; i < startOffset; i++) {
      const el = document.createElement("div");
      el.className = "cal-day empty";
      calGrid.appendChild(el);
    }

    const todayStr = HOY;
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${state.viewYear}-${String(state.viewMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cal-day";
      btn.textContent = d;

      const isPast = dateStr < todayStr;
      const isTaken = state.takenDates.has(dateStr);

      if (isPast) {
        btn.classList.add("past");
        btn.disabled = true;
      } else if (isTaken) {
        btn.classList.add("taken");
        btn.disabled = true;
      } else {
        if (dateStr === state.selectedDate) btn.classList.add("selected");
        btn.addEventListener("click", () => selectDate(dateStr));
      }
      calGrid.appendChild(btn);
    }

    const isCurrentMonth = state.viewYear === today.getFullYear() && state.viewMonth === today.getMonth();
    calPrev.disabled = isCurrentMonth;
  }

  function selectDate(dateStr) {
    state.selectedDate = dateStr;
    renderCalendar();
    renderBookingForm();
  }

  function renderBookingForm() {
    if (!state.selectedDate) {
      bookingCard.innerHTML = `<div class="empty-state"><div class="big">🍬</div>Elige una fecha disponible en el calendario para continuar con tu reserva.</div>`;
      return;
    }

    const fechaBonita = new Date(state.selectedDate + "T00:00:00").toLocaleDateString("es-BO", { weekday: "long", day: "numeric", month: "long" });
    const esEvento = state.tipo === "evento";

    bookingCard.innerHTML = `
      <h3>${esEvento ? "🎉 Evento privado" : "📍 Punto fijo"} — ${state.ciudad}</h3>
      <p class="hint">${fechaBonita}${state.punto ? " · " + state.punto : ""}</p>
      <div id="formMsg"></div>
      <form id="bookingForm">
        <div class="field">
          <label for="nombre">Tu nombre</label>
          <input type="text" id="nombre" required>
        </div>
        <div class="field">
          <label for="whatsapp">WhatsApp de contacto</label>
          <input type="tel" id="whatsapp" placeholder="Ej. 71234567" required>
        </div>
        ${esEvento ? `
        <div class="row2">
          <div class="field">
            <label for="tipoEvento">Tipo de evento</label>
            <select id="tipoEvento">
              <option>Cumpleaños</option>
              <option>Evento empresarial</option>
              <option>Baby shower</option>
              <option>Otro</option>
            </select>
          </div>
          <div class="field">
            <label for="invitados">Invitados aprox.</label>
            <input type="number" id="invitados" min="1">
          </div>
        </div>
        <div class="field">
          <label for="lugar">Lugar / dirección del evento</label>
          <input type="text" id="lugar" placeholder="Ej. Salón, zona, referencia">
        </div>` : ""}
        <div class="field">
          <label for="mensaje">Mensaje (opcional)</label>
          <textarea id="mensaje" placeholder="Diseños que te interesan, horario, etc."></textarea>
        </div>
        <button type="submit" class="btn btn-pink" style="width:100%;justify-content:center">Confirmar mi reserva</button>
      </form>
    `;

    document.getElementById("bookingForm").addEventListener("submit", submitBooking);
  }

  async function submitBooking(e) {
    e.preventDefault();
    const msgEl = document.getElementById("formMsg");
    msgEl.innerHTML = "";

    const payload = {
      ciudad: state.ciudad,
      tipo: state.tipo,
      punto: state.punto,
      fecha: state.selectedDate,
      nombre: document.getElementById("nombre").value.trim(),
      whatsapp: document.getElementById("whatsapp").value.trim(),
    };
    if (state.tipo === "evento") {
      payload.tipo_evento = document.getElementById("tipoEvento").value;
      payload.invitados = document.getElementById("invitados").value;
      payload.lugar = document.getElementById("lugar").value.trim();
    }
    payload.mensaje = document.getElementById("mensaje").value.trim();

    const submitBtn = e.target.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Enviando…";

    try {
      const res = await fetch("/api/reservas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "No se pudo completar la reserva.");

      if (window.track) window.track("Lead", { content_name: "reserva_" + state.tipo, content_category: state.ciudad });

      bookingCard.innerHTML = `
        <div class="empty-state">
          <div class="big">✅</div>
          <strong style="color:var(--text)">¡Tu fecha quedó reservada!</strong><br>
          Te contactaremos por WhatsApp al ${payload.whatsapp} para confirmar los detalles.
        </div>`;
      state.selectedDate = null;
      await fetchAvailability();
      renderCalendar();
    } catch (err) {
      msgEl.innerHTML = `<div class="form-msg error">${err.message}</div>`;
      submitBtn.disabled = false;
      submitBtn.textContent = "Confirmar mi reserva";
      if (String(err.message).includes("disponible")) {
        state.selectedDate = null;
        await fetchAvailability();
        renderCalendar();
        renderBookingForm();
      }
    }
  }

  async function refresh() {
    state.selectedDate = null;
    await fetchAvailability();
    renderCalendar();
    renderBookingForm();
  }

  selCiudad.addEventListener("change", () => {
    state.ciudad = selCiudad.value;
    updatePuntoVisibility();
    refresh();
  });

  tipoToggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".toggle-btn");
    if (!btn) return;
    state.tipo = btn.dataset.tipo;
    updatePuntoVisibility();
    refresh();
  });

  selPunto.addEventListener("change", () => {
    state.punto = selPunto.value;
    refresh();
  });

  calPrev.addEventListener("click", () => {
    state.viewMonth--;
    if (state.viewMonth < 0) { state.viewMonth = 11; state.viewYear--; }
    refresh();
  });
  calNext.addEventListener("click", () => {
    state.viewMonth++;
    if (state.viewMonth > 11) { state.viewMonth = 0; state.viewYear++; }
    refresh();
  });

  updatePuntoVisibility();
  refresh();
})();
