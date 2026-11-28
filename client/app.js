// Tarayıcı istemcisi: mikrofon → 16 kHz PCM → WebSocket; gelen cümle sesleri sırayla çalınır.
(() => {
  const $ = (id) => document.getElementById(id);
  const log = $("log");
  const STATUS = {
    idle: ["", "Bağlı değil"],
    connecting: ["busy", "Bağlanıyor"],
    listening: ["listening", "Dinliyor"],
    speech: ["speech", "Konuşmanız alınıyor"],
    thinking: ["busy", "Yanıt hazırlanıyor"],
    speaking: ["busy", "Asistan konuşuyor"],
    ended: ["", "Görüşme bitti"],
    error: ["error", "Hata"],
  };

  let ws = null;
  let ctx = null;
  let micStream = null;
  let micNode = null;
  let pendingAudio = null; // sıradaki ikili çerçevenin bilgisi
  let playEnd = 0; // çalma kuyruğunun bittiği an (AudioContext zamanı)
  let playTimer = null;
  let turn = 0;

  function setStatus(key, extra) {
    const [cls, text] = STATUS[key];
    $("dot").className = "dot " + cls;
    $("status").textContent = extra ? `${text}: ${extra}` : text;
    setStatus.current = key;
  }

  function add(kind, text, note) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    el.textContent = text;
    if (note) {
      const small = document.createElement("small");
      small.textContent = note;
      el.appendChild(small);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  function storedSession() {
    try { return sessionStorage.getItem("voice-session") || ""; } catch { return ""; }
  }
  function storeSession(id) {
    try { sessionStorage.setItem("voice-session", id); } catch { /* özel pencere */ }
  }

  const speaking = () => ctx && ctx.currentTime < playEnd;

  function play(meta, buffer) {
    const pcm = new Int16Array(buffer);
    const audio = ctx.createBuffer(1, pcm.length, meta.sample_rate);
    const data = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 32768;
    const src = ctx.createBufferSource();
    src.buffer = audio;
    src.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.02, playEnd);
    src.start(at);
    playEnd = at + audio.duration;
    setStatus("speaking");
    clearTimeout(playTimer);
    playTimer = setTimeout(() => {
      if (!speaking() && setStatus.current === "speaking") setStatus("listening");
    }, (playEnd - ctx.currentTime) * 1000 + 50);
  }

  function showTimings(t) {
    turn += 1;
    const row = document.createElement("tr");
    const cells = [turn, t.vad, t.stt, t.llm, t.tts_first, t.first_audio];
    row.innerHTML = cells.map((v, i) => `<td>${i ? Number(v).toFixed(2) : v}</td>`).join("");
    const body = $("timings");
    body.prepend(row);
    while (body.children.length > 8) body.lastChild.remove();
  }

  function onMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      if (pendingAudio) play(pendingAudio, event.data);
      pendingAudio = null;
      return;
    }
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case "session":
        storeSession(msg.session_id);
        if (msg.resumed) add("sys", "Önceki görüşmeye devam ediliyor.");
        setStatus("listening");
        break;
      case "vad":
        if (msg.state === "speech_start") setStatus("speech");
        else setStatus("thinking");
        break;
      case "transcript":
        if (msg.text) add("user", msg.text, msg.source === "text" ? "yazıldı" : "duyulan");
        else if (!speaking()) setStatus("listening");
        break;
      case "reply":
        add("bot", msg.text);
        break;
      case "audio":
        pendingAudio = msg;
        break;
      case "turn_end":
        showTimings(msg.timings);
        break;
      case "end":
        add("sys", "Görüşme sona erdi.");
        setStatus("ended");
        stop(true);
        break;
      case "error":
        add("sys", msg.message);
        break;
    }
  }

  async function start() {
    $("start").disabled = true;
    setStatus("connecting");
    try {
      ctx = new AudioContext();
      await ctx.audioWorklet.addModule("mic-worklet.js");
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      setStatus("error", "mikrofon açılamadı");
      add("sys", "Mikrofona erişilemedi: " + err.message);
      $("start").disabled = false;
      return;
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const session = storedSession();
    ws = new WebSocket(`${proto}://${location.host}/ws/voice${session ? "?session_id=" + session : ""}`);
    ws.binaryType = "arraybuffer";
    ws.onmessage = onMessage;
    ws.onclose = () => {
      if (setStatus.current !== "ended" && setStatus.current !== "error") setStatus("idle");
      stop(false);
    };
    ws.onopen = () => {
      const source = ctx.createMediaStreamSource(micStream);
      micNode = new AudioWorkletNode(ctx, "mic-processor");
      // Aşama 4: asistan konuşurken mikrofon gönderilmez (yankı turu tetiklemesin).
      // Aşama 5'te araya girme için bu kısıt kalkacak.
      micNode.port.onmessage = (e) => {
        if (ws && ws.readyState === WebSocket.OPEN && !speaking()) ws.send(e.data);
      };
      source.connect(micNode);
      $("stop").disabled = false;
      $("text").disabled = false;
      $("send").disabled = false;
    };
  }

  function stop(closeSocket = true) {
    if (micNode) micNode.disconnect();
    if (micStream) micStream.getTracks().forEach((t) => t.stop());
    micNode = null;
    micStream = null;
    if (closeSocket && ws) ws.close();
    ws = null;
    $("start").disabled = false;
    $("stop").disabled = true;
    $("text").disabled = true;
    $("send").disabled = true;
  }

  $("start").addEventListener("click", start);
  $("stop").addEventListener("click", () => { stop(true); setStatus("idle"); });
  $("typed").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("text").value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "text", text }));
    $("text").value = "";
    setStatus("thinking");
  });
  setStatus("idle");
})();
