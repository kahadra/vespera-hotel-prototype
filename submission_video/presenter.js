"use strict";

const canvas = document.querySelector("#stage");
const ctx = canvas.getContext("2d");
const loading = document.querySelector("#loading");
const playButton = document.querySelector("#play");
const restartButton = document.querySelector("#restart");
const recordButton = document.querySelector("#record");
const statusLabel = document.querySelector("#status");

const W = canvas.width;
const H = canvas.height;
const GOLD = "#e0b457";
const PALE = "#f7f0e5";
const MUTED = "#b7a993";
const INK = "#0d0c0b";

const assetNames = [
  "title", "tutorial", "handbook-locked", "night1-empty", "night1-partial", "night1",
  "night1-result", "shop", "reservation-empty", "reservation",
  "handbook-unlocked", "night2-empty", "night2-partial", "night2", "final",
];

const images = {};
const scenes = [
  { duration: 6, type: "intro" },
  {
    duration: 8, image: "title", kicker: "AN INVITATION FROM HOTEL VESPERA",
    title: "낯선 손님을 위한 첫 영업",
    caption: "베스페라 호텔의 초대장을 열고, 오늘 밤의 운영을 시작합니다.",
    cursor: [[0.49, 0.80], [0.50, 0.73]], click: 0.72,
  },
  {
    duration: 8, image: "tutorial", kicker: "UNTIMED PRACTICE",
    title: "먼저, 시간 압박 없이 익힙니다",
    caption: "두 손님으로 객실 배치를 연습합니다. 규칙을 아는 플레이어는 바로 첫 영업으로 건너뛸 수 있습니다.",
    boxes: [[1041, 87, 206, 58], [892, 581, 338, 49]], captionY: 500, cursor: [[0.36, 0.73], [0.74, 0.84]], click: 0.77,
  },
  { duration: 8, type: "loop" },
  {
    duration: 9, image: "handbook-locked", kicker: "1. LEARN THE RULES",
    title: "필수 규칙은 운영 수첩에서",
    caption: "공통 규칙과 종족·등급 규칙을 언제든 확인합니다. 아직 만나지 못한 규칙은 잠겨 있습니다.",
    boxes: [[645, 308, 459, 280]], cursor: [[0.25, 0.25], [0.68, 0.50]], click: 0.50,
  },
  {
    duration: 8, image: "night1-empty", kicker: "2. ASSIGN THE ROOMS",
    title: "모든 손님에게 객실을",
    caption: "첫 영업부터 체크인 마감은 2분입니다. 객실의 환경과 필수 조건을 먼저 맞춥니다.",
    boxes: [[122, 178, 770, 300]], cursor: [[0.20, 0.75], [0.39, 0.56]], click: 0.78,
  },
  {
    duration: 10, image: "night1-partial", kicker: "HARD RULES FIRST",
    title: "가능한 배치를 만들고",
    caption: "필수 조건을 만족해야만 배치가 성립합니다. 두 손님을 놓자 가능한 선택지가 줄어듭니다.",
    boxes: [[387, 178, 257, 300]], cursor: [[0.62, 0.72], [0.40, 0.60]], click: 0.65,
  },
  {
    duration: 9, image: "night1", kicker: "THEN OPTIMIZE",
    title: "남은 시간으로 선호를 더 높게",
    caption: "답이 여러 개라면 개인 선호를 더 높입니다. 이미 놓은 손님을 옮길 때마다 5초가 줄어듭니다.",
    boxes: [[147, 598, 112, 35]], captionY: 492, cursor: [[0.74, 0.39], [0.18, 0.84]], click: 0.78,
  },
  {
    duration: 10, image: "night1-result", kicker: "NIGHT 1 COMPLETE",
    title: "배치의 결과가 경영으로 이어집니다",
    caption: "만족 19, 총수입 42G, 평판 +4. 좋은 배치는 다음 선택지를 넓힙니다.",
    boxes: [[462, 436, 339, 120], [812, 436, 340, 120]], cursor: [[0.50, 0.64], [0.76, 0.69]], click: 0.82,
  },
  {
    duration: 11, image: "shop", kicker: "3. CHANGE THE HOTEL",
    title: "번 돈으로 다음 밤의 규칙을 바꿉니다",
    caption: "세 시설 제안 중 비밀 통로를 선택합니다. 시설은 장식이 아니라 새로운 배치 조건입니다.",
    boxes: [[852, 173, 394, 418]], cursor: [[0.50, 0.74], [0.82, 0.75]], click: 0.72,
  },
  {
    duration: 8, image: "reservation-empty", kicker: "4. CHOOSE THE GUESTS",
    title: "누구를 받을지도 결정입니다",
    caption: "숙박비와 만족 보상은 높지만, 귀빈을 거절하면 평판 손실도 큽니다.",
    boxes: [[34, 174, 1211, 350]], cursor: [[0.14, 0.68], [0.22, 0.68]], click: 0.54,
  },
  {
    duration: 8, image: "reservation", kicker: "ACCEPT OR REFUSE",
    title: "거절의 손해까지 계산하고",
    caption: "Morrow를 거절해 평판을 잃지만, 나머지 손님으로 더 좋은 최종 배치를 노립니다.",
    boxes: [[34, 538, 1210, 75]], cursor: [[0.26, 0.58], [0.92, 0.82]], click: 0.75,
  },
  {
    duration: 9, image: "handbook-unlocked", kicker: "A HIDDEN RULE REVEALED",
    title: "새 손님은 새 규칙을 드러냅니다",
    caption: "귀빈을 처음 만나면 잠겨 있던 등급 규칙이 해금됩니다. 다음 판단부터는 수첩에서 다시 확인할 수 있습니다.",
    boxes: [[645, 308, 459, 280]], cursor: [[0.29, 0.25], [0.69, 0.50]], click: 0.48,
  },
  {
    duration: 10, image: "night2-partial", kicker: "NIGHT 2 · SECRET PASSAGE",
    title: "시설 효과까지 함께 읽고",
    caption: "비밀 통로로 연결된 F1-B와 F3-C는 새로운 점수 기회를 만듭니다.",
    boxes: [[387, 383, 257, 95], [650, 178, 257, 96]], cursor: [[0.41, 0.61], [0.61, 0.30]], click: 0.72,
  },
  {
    duration: 10, image: "night2", kicker: "THE BEST NIGHT",
    title: "필수 규칙과 선호를 동시에 해결합니다",
    caption: "수용한 다섯 손님의 필수 조건을 지키면서 만족도 합계 28을 만듭니다.",
    boxes: [[147, 612, 116, 34]], captionY: 506, cursor: [[0.69, 0.48], [0.18, 0.86]], click: 0.76,
  },
  {
    duration: 10, image: "final", kicker: "FINAL EVALUATION",
    title: "정답 하나가 아닌, 가장 좋은 운영을",
    caption: "두 번째 영업 평가 62. 규칙 학습과 최적화가 호텔의 성장으로 되돌아옵니다.",
    boxes: [[899, 307, 254, 80]], cursor: [[0.50, 0.70], [0.79, 0.49]], click: 0.44,
  },
  { duration: 8, type: "outro" },
];

const TOTAL = scenes.reduce((sum, scene) => sum + scene.duration, 0);
let playhead = 0;
let playing = false;
let lastFrame = performance.now();
let ready = false;
let mediaRecorder = null;
let audioContext = null;

function clamp(value, min = 0, max = 1) { return Math.max(min, Math.min(max, value)); }
function ease(value) { const t = clamp(value); return t * t * (3 - 2 * t); }
function lerp(a, b, t) { return a + (b - a) * t; }

function roundedRect(x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, r);
}

function fitText(text, maxWidth, startSize, minSize = 18, weight = 800, family = '"Malgun Gothic", sans-serif') {
  let size = startSize;
  while (size > minSize) {
    ctx.font = `${weight} ${size}px ${family}`;
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 1;
  }
  return size;
}

function wrapText(text, x, y, maxWidth, lineHeight, maxLines = 2) {
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines - 1) break;
    } else {
      line = test;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  lines.forEach((item, index) => ctx.fillText(item, x, y + index * lineHeight));
}

function drawBackdrop() {
  const gradient = ctx.createRadialGradient(W * 0.5, H * 0.2, 10, W * 0.5, H * 0.4, W * 0.75);
  gradient.addColorStop(0, "#211b12");
  gradient.addColorStop(0.5, "#11100e");
  gradient.addColorStop(1, "#080808");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, W, H);
}

function drawDiamond(x, y, size) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(Math.PI / 4);
  ctx.fillStyle = GOLD;
  ctx.fillRect(-size / 2, -size / 2, size, size);
  ctx.restore();
}

function drawIntro(progress) {
  drawBackdrop();
  const reveal = ease(clamp(progress / 0.42));
  const y = lerp(385, 350, reveal);
  ctx.globalAlpha = reveal;
  drawDiamond(W / 2, 205, 24);
  ctx.textAlign = "center";
  ctx.fillStyle = GOLD;
  ctx.font = '700 17px "Malgun Gothic", sans-serif';
  ctx.letterSpacing = "5px";
  ctx.fillText("HOTEL VESPERA", W / 2, 270);
  ctx.letterSpacing = "0px";
  ctx.fillStyle = PALE;
  ctx.font = '800 58px "Malgun Gothic", sans-serif';
  ctx.fillText("베스페라 호텔", W / 2, y);
  ctx.fillStyle = MUTED;
  ctx.font = '500 25px "Malgun Gothic", sans-serif';
  ctx.fillText("첫 영업", W / 2, y + 54);
  ctx.fillStyle = "#75664f";
  ctx.font = '500 16px "Malgun Gothic", sans-serif';
  ctx.fillText("규칙을 배우고 · 손님을 고르고 · 가장 좋은 밤을 설계하세요", W / 2, y + 112);
  ctx.globalAlpha = 1;
}

function drawLoop(progress) {
  drawBackdrop();
  ctx.textAlign = "center";
  ctx.fillStyle = GOLD;
  ctx.font = '700 15px "Malgun Gothic", sans-serif';
  ctx.fillText("CORE LOOP", W / 2, 126);
  ctx.fillStyle = PALE;
  ctx.font = '800 42px "Malgun Gothic", sans-serif';
  ctx.fillText("한 번의 영업, 세 번의 판단", W / 2, 184);

  const cards = [
    ["01", "규칙을 익힌다", "수첩에서 필수 조건을 확인"],
    ["02", "손님을 고른다", "수입과 거절 손해를 저울질"],
    ["03", "최선의 배치를 찾는다", "가능한 답 중 선호를 최대화"],
  ];
  cards.forEach((card, index) => {
    const appear = ease(clamp((progress - index * 0.12) / 0.35));
    const x = 96 + index * 374;
    const y = lerp(350, 280, appear);
    ctx.globalAlpha = appear;
    roundedRect(x, y, 342, 225, 16);
    ctx.fillStyle = index === 2 ? "#241e14" : "#171512";
    ctx.fill();
    ctx.strokeStyle = index === 2 ? GOLD : "#4d402e";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.textAlign = "left";
    ctx.fillStyle = GOLD;
    ctx.font = '800 17px "Malgun Gothic", sans-serif';
    ctx.fillText(card[0], x + 26, y + 42);
    ctx.fillStyle = PALE;
    ctx.font = '800 25px "Malgun Gothic", sans-serif';
    ctx.fillText(card[1], x + 26, y + 95);
    ctx.fillStyle = MUTED;
    ctx.font = '500 16px "Malgun Gothic", sans-serif';
    wrapText(card[2], x + 26, y + 139, 286, 25, 2);
    if (index < 2) {
      ctx.fillStyle = GOLD;
      ctx.font = '700 30px "Malgun Gothic", sans-serif';
      ctx.fillText("→", x + 351, y + 120);
    }
  });
  ctx.globalAlpha = 1;
}

function drawImageScene(scene, progress) {
  const image = images[scene.image];
  ctx.drawImage(image, 0, 0, W, H);
  const scaleX = 1;
  const scaleY = 1;
  const mapPoint = (x, y) => [x, y];

  const topGradient = ctx.createLinearGradient(0, 0, 0, 190);
  topGradient.addColorStop(0, "rgba(5,4,3,.92)");
  topGradient.addColorStop(0.52, "rgba(5,4,3,.55)");
  topGradient.addColorStop(1, "rgba(5,4,3,0)");
  ctx.fillStyle = topGradient;
  ctx.fillRect(0, 0, W, 200);

  if (scene.boxes) {
    const pulse = 0.55 + Math.sin(progress * Math.PI * 5) * 0.12;
    scene.boxes.forEach(([assetX, assetY, assetWidth, assetHeight]) => {
      const [x, y] = mapPoint(assetX, assetY);
      const width = assetWidth * scaleX;
      const height = assetHeight * scaleY;
      ctx.save();
      ctx.shadowColor = `rgba(224,180,87,${pulse})`;
      ctx.shadowBlur = 24;
      roundedRect(x, y, width, height, 12);
      ctx.strokeStyle = `rgba(236,192,105,${0.78 + pulse * 0.2})`;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
    });
  }

  ctx.textAlign = "left";
  ctx.fillStyle = GOLD;
  ctx.font = '800 14px "Malgun Gothic", sans-serif';
  ctx.fillText(scene.kicker, 54, 42);
  ctx.fillStyle = PALE;
  const titleSize = fitText(scene.title, 1030, 38, 28);
  ctx.font = `800 ${titleSize}px "Malgun Gothic", sans-serif`;
  ctx.fillText(scene.title, 54, 88);

  drawCaption(scene.caption, scene.captionY);
  drawCursor(scene, progress, mapPoint);
}

function drawCaption(caption, captionY = 618) {
  if (captionY >= 600) {
    const gradient = ctx.createLinearGradient(0, 555, 0, H);
    gradient.addColorStop(0, "rgba(7,6,5,0)");
    gradient.addColorStop(0.36, "rgba(7,6,5,.75)");
    gradient.addColorStop(1, "rgba(7,6,5,.97)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 540, W, 180);
  }
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.58)";
  ctx.shadowBlur = captionY < 600 ? 18 : 0;
  roundedRect(52, captionY, 1176, 62, 10);
  ctx.fillStyle = "rgba(24,21,17,.92)";
  ctx.fill();
  ctx.strokeStyle = "rgba(224,180,87,.36)";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
  ctx.fillStyle = PALE;
  ctx.textAlign = "left";
  ctx.font = '600 19px "Malgun Gothic", sans-serif';
  wrapText(caption, 78, captionY + 37, 1080, 25, 1);
}

function drawCursor(scene, progress, mapPoint) {
  if (!scene.cursor) return;
  const from = scene.cursor[0];
  const to = scene.cursor[1];
  const move = ease(clamp((progress - 0.12) / 0.58));
  const mappedFrom = mapPoint(from[0] * W, from[1] * H);
  const mappedTo = mapPoint(to[0] * W, to[1] * H);
  const x = lerp(mappedFrom[0], mappedTo[0], move);
  const y = lerp(mappedFrom[1], mappedTo[1], move);
  if (scene.click && Math.abs(progress - scene.click) < 0.11) {
    const ring = clamp(Math.abs(progress - scene.click) / 0.11);
    ctx.beginPath();
    ctx.arc(x, y, lerp(11, 35, ring), 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(224,180,87,${1 - ring})`;
    ctx.lineWidth = 4;
    ctx.stroke();
  }
  ctx.save();
  ctx.translate(x, y);
  ctx.shadowColor = "rgba(0,0,0,.75)";
  ctx.shadowBlur = 7;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(2, 29);
  ctx.lineTo(10, 21);
  ctx.lineTo(18, 39);
  ctx.lineTo(27, 34);
  ctx.lineTo(18, 16);
  ctx.lineTo(31, 14);
  ctx.closePath();
  ctx.fillStyle = PALE;
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2.5;
  ctx.stroke();
  ctx.restore();
}

function drawOutro(progress) {
  drawBackdrop();
  const reveal = ease(clamp(progress / 0.4));
  ctx.globalAlpha = reveal;
  drawDiamond(W / 2, 135, 20);
  ctx.textAlign = "center";
  ctx.fillStyle = GOLD;
  ctx.font = '800 15px "Malgun Gothic", sans-serif';
  ctx.fillText("HOTEL VESPERA", W / 2, 194);
  ctx.fillStyle = PALE;
  ctx.font = '800 48px "Malgun Gothic", sans-serif';
  ctx.fillText("오늘 밤의 객실은 준비되었습니다", W / 2, 277);
  ctx.fillStyle = MUTED;
  ctx.font = '500 21px "Malgun Gothic", sans-serif';
  ctx.fillText("플레이 링크는 제출 페이지에서 바로 열 수 있습니다.", W / 2, 325);

  roundedRect(395, 385, 490, 88, 12);
  ctx.fillStyle = "#181510";
  ctx.fill();
  ctx.strokeStyle = "#6b522d";
  ctx.stroke();
  ctx.fillStyle = "#8f7c61";
  ctx.font = '700 13px "Malgun Gothic", sans-serif';
  ctx.fillText("PLAYABLE BUILD", W / 2, 420);
  ctx.fillStyle = GOLD;
  ctx.font = '800 21px "Malgun Gothic", sans-serif';
  ctx.fillText("공개 플레이 URL · 제출란 참조", W / 2, 452);
  ctx.fillStyle = "#6e604d";
  ctx.font = '500 14px "Malgun Gothic", sans-serif';
  ctx.fillText("베스페라 호텔: 첫 영업 · 2026", W / 2, 558);
  ctx.globalAlpha = 1;
}

function locateScene(time) {
  let cursor = 0;
  for (let index = 0; index < scenes.length; index += 1) {
    const scene = scenes[index];
    if (time < cursor + scene.duration || index === scenes.length - 1) {
      return { scene, index, local: clamp((time - cursor) / scene.duration) };
    }
    cursor += scene.duration;
  }
  return { scene: scenes.at(-1), index: scenes.length - 1, local: 1 };
}

function drawChrome(index) {
  const progress = playhead / TOTAL;
  ctx.fillStyle = "rgba(9,8,7,.72)";
  roundedRect(1082, 24, 144, 34, 17);
  ctx.fill();
  ctx.fillStyle = "#d3c7b5";
  ctx.textAlign = "center";
  ctx.font = '700 12px "Malgun Gothic", sans-serif';
  ctx.fillText(index === 0 || index === scenes.length - 1 ? "PLAY DEMO" : "실제 플레이 화면", 1154, 45);

  ctx.fillStyle = "rgba(255,255,255,.14)";
  ctx.fillRect(0, H - 5, W, 5);
  ctx.fillStyle = GOLD;
  ctx.fillRect(0, H - 5, W * progress, 5);
}

function render() {
  if (!ready) return;
  const { scene, index, local } = locateScene(playhead);
  ctx.clearRect(0, 0, W, H);
  if (scene.type === "intro") drawIntro(local);
  else if (scene.type === "loop") drawLoop(local);
  else if (scene.type === "outro") drawOutro(local);
  else drawImageScene(scene, local);

  const fade = local < 0.055 ? 1 - local / 0.055 : local > 0.955 ? (local - 0.955) / 0.045 : 0;
  if (fade > 0) {
    ctx.fillStyle = `rgba(6,5,4,${fade * 0.82})`;
    ctx.fillRect(0, 0, W, H);
  }
  drawChrome(index);
  statusLabel.textContent = `${formatTime(playhead)} / ${formatTime(TOTAL)}`;
}

function frame(now) {
  const elapsed = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  if (playing) {
    playhead = Math.min(TOTAL, playhead + elapsed);
    if (playhead >= TOTAL) {
      playing = false;
      playButton.textContent = "재생";
      if (mediaRecorder?.state === "recording") setTimeout(() => mediaRecorder.stop(), 250);
    }
  }
  render();
  requestAnimationFrame(frame);
}

function formatTime(seconds) {
  const value = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function setPlaying(value) {
  if (!ready || mediaRecorder?.state === "recording") return;
  if (playhead >= TOTAL) playhead = 0;
  playing = value;
  playButton.textContent = playing ? "정지" : "재생";
}

function makeAmbientTrack() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  audioContext = new AudioCtx();
  const destination = audioContext.createMediaStreamDestination();
  const master = audioContext.createGain();
  const filter = audioContext.createBiquadFilter();
  master.gain.value = 0.025;
  filter.type = "lowpass";
  filter.frequency.value = 520;
  master.connect(filter).connect(destination);
  [82.41, 123.47, 164.81].forEach((frequency, index) => {
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = index === 0 ? "sine" : "triangle";
    oscillator.frequency.value = frequency;
    gain.gain.value = index === 0 ? 0.28 : 0.08;
    oscillator.connect(gain).connect(master);
    oscillator.start();
  });
  return destination.stream.getAudioTracks()[0] ?? null;
}

async function recordVideo(startAt = 0) {
  if (!ready || mediaRecorder?.state === "recording") return;
  window.recordedReady = false;
  window.recordedBlob = null;
  window.recordedBytes = null;
  const videoStream = canvas.captureStream(30);
  const audioTrack = window.automatedExport ? null : makeAmbientTrack();
  if (audioTrack) videoStream.addTrack(audioTrack);
  const candidates = [
    "video/webm;codecs=vp8",
    "video/webm;codecs=vp9",
    "video/webm",
  ];
  const mimeType = candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  const chunks = [];
  mediaRecorder = new MediaRecorder(videoStream, mimeType ? { mimeType, videoBitsPerSecond: 2_500_000 } : undefined);
  mediaRecorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
  mediaRecorder.addEventListener("stop", async () => {
    const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "video/webm" });
    window.recordedBlob = blob;
    window.recordedBytes = new Uint8Array(await blob.arrayBuffer());
    window.recordedReady = true;
    if (!window.automatedExport) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vespera-hotel-play-demo.webm";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    }
    if (audioContext) await audioContext.close();
    audioContext = null;
    recordButton.disabled = false;
    playButton.disabled = false;
    restartButton.disabled = false;
    recordButton.textContent = "영상 저장 완료";
  });
  recordButton.disabled = true;
  playButton.disabled = true;
  restartButton.disabled = true;
  recordButton.textContent = "녹화 중 · 02:30";
  playhead = clamp(Number(startAt) || 0, 0, TOTAL);
  playing = true;
  mediaRecorder.start(1000);
}

async function loadAssets() {
  await Promise.all(assetNames.map((name) => new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => { images[name] = image; resolve(); });
    image.addEventListener("error", () => reject(new Error(`이미지 로드 실패: ${name}`)));
    image.src = `assets/${name}.png`;
  })));
  ready = true;
  loading.classList.add("hidden");
  render();
  const params = new URLSearchParams(location.search);
  if (params.get("autoplay") === "1") setPlaying(true);
  if (params.get("record") === "1") setTimeout(recordVideo, 500);
}

playButton.addEventListener("click", () => setPlaying(!playing));
restartButton.addEventListener("click", () => { playhead = 0; setPlaying(false); render(); });
recordButton.addEventListener("click", recordVideo);
canvas.addEventListener("click", () => setPlaying(!playing));
document.addEventListener("keydown", async (event) => {
  if (event.code === "Space") { event.preventDefault(); setPlaying(!playing); }
  if (event.key === "ArrowRight") { playhead = Math.min(TOTAL, playhead + 5); render(); }
  if (event.key === "ArrowLeft") { playhead = Math.max(0, playhead - 5); render(); }
  if (event.key.toLowerCase() === "r") { playhead = 0; setPlaying(false); render(); }
  if (event.key.toLowerCase() === "f") {
    if (!document.fullscreenElement) await document.querySelector(".stage-shell").requestFullscreen();
    else await document.exitFullscreen();
  }
});
document.addEventListener("fullscreenchange", () => document.body.classList.toggle("fullscreen", Boolean(document.fullscreenElement)));

loadAssets().catch((error) => { loading.textContent = error.message; console.error(error); });
requestAnimationFrame(frame);
