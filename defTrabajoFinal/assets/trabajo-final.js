/* Trabajo Final M04 — navegación e interacciones, sin dependencias. */
(function () {
  "use strict";

  var TOTAL_PANELS = 18;
  var ROUTE = [
    { file: "index.html", count: 2, start: 0, label: "Introducción" },
    { file: "01-caso-de-negocio.html", count: 3, start: 2, label: "Caso" },
    { file: "02-que-construir.html", count: 3, start: 5, label: "Sistema" },
    { file: "03-entregables-y-demo.html", count: 3, start: 8, label: "Entrega" },
    { file: "04-rubrica.html", count: 4, start: 11, label: "Rúbrica" },
    { file: "05-recursos-y-datos.html", count: 3, start: 15, label: "Datos" }
  ];
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var file = location.pathname.split("/").pop() || "index.html";
  var routeIndex = ROUTE.findIndex(function (item) { return item.file === file; });
  var route = ROUTE[routeIndex] || ROUTE[0];
  var panels = Array.prototype.slice.call(document.querySelectorAll(".panel"));
  var current = 0;
  var scrolling = false;

  function setProgress() {
    var globalIndex = route.start + current + 1;
    var progress = document.querySelector(".deck-progress");
    var count = document.querySelector(".deck-top .count");
    var step = document.querySelector(".deck-top .step-name");
    if (progress) {
      progress.style.width = globalIndex / TOTAL_PANELS * 100 + "%";
      progress.setAttribute("aria-valuenow", String(globalIndex));
      progress.setAttribute("aria-valuetext", "Panel " + globalIndex + " de " + TOTAL_PANELS);
    }
    if (count) count.textContent = globalIndex + " / " + TOTAL_PANELS;
    if (step) step.textContent = route.label + " · " + (current + 1) + "/" + panels.length;
    panels.forEach(function (panel, index) {
      panel.classList.toggle("in", index === current);
      if (index === current) panel.setAttribute("aria-current", "step");
      else panel.removeAttribute("aria-current");
    });
    updateControls(globalIndex);
  }

  function updateControls(globalIndex) {
    var previous = document.querySelector("[data-deck-prev]");
    var next = document.querySelector("[data-deck-next]");
    var label = document.querySelector(".deck-controls .control-label");
    if (previous) previous.disabled = globalIndex === 1;
    if (next) {
      next.disabled = false;
      next.setAttribute("aria-label", globalIndex === TOTAL_PANELS ? "Volver al índice" : "Panel siguiente");
    }
    if (label) label.textContent = globalIndex === TOTAL_PANELS ? "reiniciar" : "navegar";
  }

  function goLocal(index) {
    current = Math.max(0, Math.min(panels.length - 1, index));
    scrolling = true;
    panels[current].scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    setProgress();
    window.setTimeout(function () { scrolling = false; }, reducedMotion ? 0 : 450);
  }

  function goFile(index, last) {
    if (index < 0) return;
    if (index >= ROUTE.length) {
      location.href = "index.html";
      return;
    }
    location.href = ROUTE[index].file + (last ? "#last" : "");
  }

  function navigate(delta) {
    var rect = panels[current].getBoundingClientRect();
    if (delta > 0 && rect.height > window.innerHeight + 8 && rect.bottom > window.innerHeight + 12) {
      window.scrollBy({ top: Math.min(window.innerHeight * .68, rect.bottom - window.innerHeight + 18), behavior: reducedMotion ? "auto" : "smooth" });
      return;
    }
    if (delta < 0 && rect.height > window.innerHeight + 8 && rect.top < -12) {
      window.scrollBy({ top: -Math.min(window.innerHeight * .68, -rect.top + 18), behavior: reducedMotion ? "auto" : "smooth" });
      return;
    }
    var nextLocal = current + delta;
    if (nextLocal >= 0 && nextLocal < panels.length) goLocal(nextLocal);
    else if (delta > 0) goFile(routeIndex + 1, false);
    else goFile(routeIndex - 1, true);
  }

  function initializeNavigation() {
    panels.forEach(function (panel, index) {
      panel.id = panel.id || "panel-" + (index + 1);
      panel.classList.add("in");
    });

    if (location.hash === "#last") {
      current = panels.length - 1;
      panels[current].scrollIntoView({ behavior: "auto", block: "start" });
    } else {
      var match = location.hash.match(/^#panel-(\d+)$/);
      if (match) {
        current = Math.max(0, Math.min(panels.length - 1, Number(match[1]) - 1));
        panels[current].scrollIntoView({ behavior: "auto", block: "start" });
      }
    }

    var previous = document.querySelector("[data-deck-prev]");
    var next = document.querySelector("[data-deck-next]");
    if (previous) previous.addEventListener("click", function () { navigate(-1); });
    if (next) next.addEventListener("click", function () { navigate(1); });

    window.addEventListener("keydown", function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      var target = event.target;
      if (target && target.matches && target.matches("textarea,select,[contenteditable=true]")) return;
      if (target && target.matches && target.matches("input") && target.type !== "checkbox") return;
      if (event.key === " " && target && target.matches && target.matches("button,a,input[type=checkbox]")) return;
      if (["ArrowRight", "ArrowDown", "PageDown", " "].indexOf(event.key) >= 0) {
        event.preventDefault(); navigate(1);
      } else if (["ArrowLeft", "ArrowUp", "PageUp"].indexOf(event.key) >= 0) {
        event.preventDefault(); navigate(-1);
      } else if (event.key === "Home") {
        event.preventDefault(); goLocal(0);
      } else if (event.key === "End") {
        event.preventDefault(); goLocal(panels.length - 1);
      }
    });

    var queued = false;
    window.addEventListener("scroll", function () {
      if (queued || scrolling) return;
      queued = true;
      window.requestAnimationFrame(function () {
        var center = window.innerHeight * .46;
        var best = 0;
        var distance = Infinity;
        panels.forEach(function (panel, index) {
          var rect = panel.getBoundingClientRect();
          var panelCenter = rect.top + Math.min(rect.height, window.innerHeight) / 2;
          var candidate = Math.abs(panelCenter - center);
          if (candidate < distance) { distance = candidate; best = index; }
        });
        if (best !== current) { current = best; setProgress(); }
        queued = false;
      });
    }, { passive: true });
    setProgress();
  }

  function storageKey(group, index) {
    return "m04-final:" + file + ":" + group + ":" + index;
  }

  function safeStorageGet(key) {
    try { return window.sessionStorage.getItem(key); }
    catch (error) { return null; }
  }

  function safeStorageSet(key, value) {
    try { window.sessionStorage.setItem(key, value); }
    catch (error) { return false; }
    return true;
  }

  function initializePersistence() {
    document.querySelectorAll("[data-persist-group]").forEach(function (group) {
      var name = group.getAttribute("data-persist-group");
      var controls = Array.prototype.slice.call(group.querySelectorAll("input,select"));
      controls.forEach(function (control, index) {
        var saved = safeStorageGet(storageKey(name, index));
        if (saved !== null) {
          if (control.type === "checkbox" || control.type === "radio") control.checked = saved === "1";
          else control.value = saved;
        }
        control.addEventListener("change", function () {
          var value = control.type === "checkbox" || control.type === "radio" ? (control.checked ? "1" : "0") : control.value;
          safeStorageSet(storageKey(name, index), value);
        });
      });
    });
  }

  function initializeCaseChecklist() {
    var box = document.getElementById("caseSelf");
    var out = document.getElementById("caseVerdict");
    if (!box || !out) return;
    var checks = Array.prototype.slice.call(box.querySelectorAll('input[type="checkbox"]'));
    function render() {
      var count = checks.filter(function (check) { return check.checked; }).length;
      if (count === checks.length) out.textContent = count + "/6 — caso viable: cumple las capacidades base. Recomendación: compártanlo temprano con el profesor para detectar brechas.";
      else if (count >= 4) out.textContent = count + "/6 — conversable: completen la evidencia faltante y revisen la rúbrica.";
      else if (count > 0) out.textContent = count + "/6 — faltan capacidades de la rúbrica; usen el ejemplo de farmacias como referencia.";
      else out.textContent = "Marca las condiciones que tu caso cumple.";
    }
    checks.forEach(function (check) { check.addEventListener("change", render); });
    render();
  }

  var ARCH_INFO = {
    front: ["front conversacional", "Punto 6", "Consume tu API; envía {user_id, pregunta}. No llama al LLM en forma directa."],
    api: ["API · FastAPI", "Punto 6", "Contrato mínimo: POST /chat. Valida entrada, invoca el grafo y devuelve una respuesta trazable."],
    agent: ["orquestación · LangGraph", "Punto 2", "El grafo enruta entre tools y mantiene estado. El historial no es una tool: vive en el checkpointer o store."],
    minsal: ["tool · MINSAL", "Punto 4", "Consulta turnos en vivo con timeout y error manejado. Informa local, dirección y horario; no stock ni precio."],
    rag: ["tool · RAG", "Punto 3", "Recupera fichas del vademécum con embeddings y vector store; responde con citas al registro recuperado."],
    mem: ["estado · historial", "Punto 2", "Memoria multi-turno por user_id en la aplicación. Se demuestra con dos turnos dependientes."],
    guard: ["control transversal", "Punto 5", "Valida entrada y salida: no recomienda medicamentos ni dosis; tampoco diagnostica ni prescribe; rechaza y deriva."]
  };

  function initializeArchitecture() {
    var map = document.getElementById("archMap");
    var tag = document.getElementById("archTag");
    var text = document.getElementById("archText");
    var rubric = document.getElementById("archRub");
    if (!map || !tag || !text || !rubric) return;
    var nodes = Array.prototype.slice.call(map.querySelectorAll(".arch-node"));
    function show(key) {
      var info = ARCH_INFO[key];
      if (!info) return;
      tag.textContent = info[0]; text.textContent = info[2]; rubric.textContent = info[1];
      nodes.forEach(function (node) {
        node.setAttribute("aria-pressed", node.getAttribute("data-k") === key ? "true" : "false");
      });
    }
    nodes.forEach(function (node) { node.addEventListener("click", function () { show(node.getAttribute("data-k")); }); });
    show("agent");
  }

  var FLOW_INFO = {
    turnos: ["Farmacias de turno + historial", "» ¿Qué farmacia está de turno en Ñuñoa?\n[tool: MINSAL getLocalesTurnos]\nRespuesta basada en registros vigentes: nombre, dirección y horario.\n\n» ¿Y en Providencia?\n[state: conserva que la consulta es sobre turnos]", "Valida datos en vivo + 2 turnos dependientes."],
    rag: ["Ficha de medicamento con fuente", "» ¿Para qué se usa la amoxicilina?\n[tool: RAG vademécum]\nRespuesta general basada sólo en el retrieval.\nFuente: ficha/registro Amoxicillin.", "Valida embeddings, vector store y cita trazable."],
    safety: ["Rechazo útil + derivación", "» Me duele la cabeza, ¿qué me tomo?\n[control: guardrail de entrada/salida]\nNo puedo recomendar medicamentos ni dosis. Consulta a un profesional de salud. Sí puedo ayudarte a encontrar una farmacia de turno o explicar una ficha ya indicada.", "Valida la condición dura del punto 5."]
  };

  function initializeFlows() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll("[data-flow-tab]"));
    var title = document.getElementById("flowTitle");
    var text = document.getElementById("flowText");
    var note = document.getElementById("flowNote");
    if (!tabs.length || !title || !text || !note) return;
    function show(key) {
      var info = FLOW_INFO[key]; if (!info) return;
      title.textContent = info[0]; text.textContent = info[1]; note.textContent = info[2];
      tabs.forEach(function (tab) { tab.setAttribute("aria-pressed", tab.getAttribute("data-flow-tab") === key ? "true" : "false"); });
    }
    tabs.forEach(function (tab) { tab.addEventListener("click", function () { show(tab.getAttribute("data-flow-tab")); }); });
    show("turnos");
  }

  function initializeCounter(containerId, numberId, messageId, total, completeText) {
    var box = document.getElementById(containerId);
    var number = document.getElementById(numberId);
    var message = document.getElementById(messageId);
    if (!box || !number) return;
    var checks = Array.prototype.slice.call(box.querySelectorAll('input[type="checkbox"]'));
    function render() {
      var count = checks.filter(function (check) { return check.checked; }).length;
      number.textContent = count;
      if (message) {
        message.textContent = count === total ? completeText : count + " de " + total + " — faltan evidencias por preparar.";
        message.classList.toggle("done", count === total);
      }
    }
    checks.forEach(function (check) { check.addEventListener("change", render); });
    render();
  }

  var SAMPLE = [
    {local_nombre:"ISAIAS  2",comuna_nombre:"ARICA",local_direccion:"AVENIDA  TUCAPEL   2596",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"21:00:00",local_telefono:"",fk_region:"1",fecha:"2026-07-14"},
    {local_nombre:"FARMACIA CRUZ VERDE ",comuna_nombre:"IQUIQUE",local_direccion:"TARAPACA 496",funcionamiento_hora_apertura:"00:00:00",funcionamiento_hora_cierre:"23:59:00",local_telefono:"+562425641",fk_region:"2",fecha:"2026-07-01"},
    {local_nombre:"VICTORIA",comuna_nombre:"TOCOPILLA",local_direccion:"CALLE 21 DE MAYO 1513",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"23:00:00",local_telefono:"2813238",fk_region:"3",fecha:"2026-07-14"},
    {local_nombre:"FARMACIA VIDA",comuna_nombre:"HUASCO",local_direccion:"PASAJE RIQUELME  147",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"21:00:00",local_telefono:"512539390",fk_region:"4",fecha:"2026-07-14"},
    {local_nombre:"FARMACIA RIVERA 1",comuna_nombre:"VICUÑA",local_direccion:"CALLE SAN MARTIN 291",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"23:00:00",local_telefono:"2411286",fk_region:"5",fecha:"2026-07-14"},
    {local_nombre:"CRUZ VERDE",comuna_nombre:"LA CALERA",local_direccion:"AVENIDA JJ PEREZ 202",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"08:59:00",local_telefono:"2724714",fk_region:"6",fecha:"2026-07-14"},
    {local_nombre:"CRUZ VERDE ",comuna_nombre:"BUIN",local_direccion:"AVENIDA JOSE MANUEL BALMACEDA 114",funcionamiento_hora_apertura:"08:00:00",funcionamiento_hora_cierre:"07:59:00",local_telefono:"28221985",fk_region:"7",fecha:"2026-07-14"},
    {local_nombre:"FUTURO",comuna_nombre:"ARAUCO",local_direccion:"ESMERALDA Nº 515-B",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"08:59:00",local_telefono:"+56412552942",fk_region:"10",fecha:"2026-07-14"},
    {local_nombre:"FARMACIA CRUZ VERDE L-367",comuna_nombre:"TEMUCO",local_direccion:"AVENIDA ALEMANIA 0780",funcionamiento_hora_apertura:"00:00:00",funcionamiento_hora_cierre:"23:59:00",local_telefono:"2244915",fk_region:"11",fecha:"2026-07-01"},
    {local_nombre:"ALBORADA",comuna_nombre:"FUTRONO",local_direccion:"BALMACEDA Nº 500",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"08:59:00",local_telefono:"+56639481390",fk_region:"12",fecha:"2026-07-14"},
    {local_nombre:"FARMACIAS CRUZ VERDE ",comuna_nombre:"PUERTO MONTT",local_direccion:"AVDA. PRESIDENTE IBAÑEZ 173 LOCAL 1",funcionamiento_hora_apertura:"00:00:00",funcionamiento_hora_cierre:"23:59:00",local_telefono:"+56993796664",fk_region:"13",fecha:"2026-07-01"},
    {local_nombre:"FARMACIA CRUZ VERDE ",comuna_nombre:"CHILE CHICO",local_direccion:"CALLE AVENIDA BERNARDO O'HIGGINS 505",funcionamiento_hora_apertura:"09:00:00",funcionamiento_hora_cierre:"20:00:00",local_telefono:"976684836",fk_region:"14",fecha:"2026-07-14"},
    {local_nombre:"ITALIA",comuna_nombre:"BULNES",local_direccion:"CALLE CARLOS PALACIOS 394",funcionamiento_hora_apertura:"08:00:00",funcionamiento_hora_cierre:"22:00:00",local_telefono:"2631272",fk_region:"16",fecha:"2026-07-14"}
  ];

  function escapeHtml(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function initializeSample() {
    var select = document.getElementById("mxSel");
    var output = document.getElementById("mxJson");
    if (!select || !output) return;
    SAMPLE.forEach(function (record, index) {
      var option = document.createElement("option");
      option.value = String(index); option.textContent = record.comuna_nombre;
      select.appendChild(option);
    });
    var saved = safeStorageGet(storageKey("minsal-sample", 0));
    if (saved !== null) select.value = saved;
    function render() {
      var record = SAMPLE[Number(select.value)] || SAMPLE[0];
      var html = "{\n";
      Object.keys(record).forEach(function (key, index, keys) {
        var value = escapeHtml(JSON.stringify(record[key]));
        var warning = key === "fk_region" || (key === "fecha" && record.fecha !== "2026-07-14") || (key === "local_telefono" && !record.local_telefono) || /\s\"$|\s\s/.test(value);
        html += '  <span class="k">"' + key + '"</span>: <span' + (warning ? ' class="warnv"' : '') + '>' + value + "</span>" + (index < keys.length - 1 ? "," : "") + "\n";
      });
      output.innerHTML = html + "}";
      safeStorageSet(storageKey("minsal-sample", 0), select.value);
    }
    select.addEventListener("change", render); render();
  }

  function initializeCopyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var text = button.getAttribute("data-copy");
        var status = document.getElementById("copyStatus");
        function copied() { if (status) status.textContent = "Endpoint copiado."; }
        function failed() { if (status) status.textContent = "No se pudo copiar; abre el endpoint."; }
        if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
          failed();
          return;
        }
        try {
          navigator.clipboard.writeText(text).then(copied).catch(function () { failed(); });
        } catch (error) {
          failed();
        }
      });
    });
  }

  initializePersistence();
  initializeNavigation();
  initializeCaseChecklist();
  initializeArchitecture();
  initializeFlows();
  initializeCounter("preDemo", "preNum", "preMsg", 8, "8 de 8 — núcleo funcional y evidencias preparados.");
  initializeCounter("rubricSelf", "rubricNum", "rubricMsg", 7, "7 de 7 — cobertura técnica completa antes de bonus.");
  initializeSample();
  initializeCopyButtons();
})();
