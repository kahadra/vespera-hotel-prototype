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
  "title", "tutorial", "handbook-ranks", "night1", "result1", "upgrade-r",
  "reservation2", "result3-discovery", "upgrade-expansion", "night4-synergy",
  "reservation5-ssr", "night5", "final",
];

const images = {};
let boxTargets = {};
const scenes = [
  { duration: 6, type: "intro" },
  { duration: 9, type: "notice" },
  {
    duration: 8, image: "title", kicker: "FIVE PRE-OPENING INVITATION NIGHTS",
    title: "다섯 번의 개장 전 초청 영업",
    caption: "튜토리얼 뒤 다섯 번의 영업으로 손님·공사 계약·호텔의 변화를 빠르게 확인합니다.",
    chromeLabel: "개장 전 초청 영업", targetNames: ["showcase-summary"], cursorFrom: [0.72, 0.78], click: 0.74,
  },
  {
    duration: 8, image: "tutorial", kicker: "UNTIMED PRACTICE",
    title: "시간 제한 없이 규칙을 익힙니다",
    caption: "두 손님으로 배치를 연습합니다. 규칙을 아는 플레이어는 튜토리얼을 건너뛸 수 있습니다.",
    chromeLabel: "튜토리얼", targetNames: ["tutorial-clock"], cursorFrom: [0.62, 0.76], click: 0.77,
  },
  { duration: 8, type: "loop" },
  {
    duration: 8, image: "handbook-ranks", kicker: "READ THE OPERATIONS HANDBOOK",
    title: "만나지 않은 종족과 등급은 미열람 규칙으로",
    caption: "종족·등급의 필수 숙박 조건과 공통 선호는 해당 손님을 처음 만난 뒤 수첩에서 열람할 수 있습니다.",
    chromeLabel: "규칙 수첩", targetNames: ["rank-handbook"], cursorFrom: [0.30, 0.30], click: 0.56,
  },
  {
    duration: 10, image: "night1", kicker: "PRE-OPENING NIGHT 1/5 · N",
    title: "N 등급 손님으로 첫 객실 배정을 시작합니다",
    caption: "첫 영업부터 체크인 마감은 2분입니다. 필수 숙박 조건을 지킨 뒤 현재 만족도를 높입니다.",
    showcaseStep: 1, targetNames: ["service-timer", "hotel-board"], captionY: 640, cursorTargetIndex: 1, cursorFrom: [0.72, 0.76], click: 0.74,
  },
  {
    duration: 10, image: "result1", kicker: "PRE-OPENING NIGHT 1/5 · SETTLEMENT",
    title: "정산이 다음 제안 확률을 바꿉니다",
    caption: "만족도와 수입, 평판이 쌓이면 다음 영업부터 R 손님과 시설이 제안에 섞입니다.",
    showcaseStep: 1, targetNames: ["next-rank-odds"], captionY: 570, cursorFrom: [0.64, 0.78], click: 0.72,
  },
  {
    duration: 6, image: "upgrade-r", kicker: "PRE-OPENING NIGHT 2/5 · SERVICE CONTRACT",
    title: "시설·인테리어 계약을 한 건 고릅니다",
    caption: "평판과 시드가 공사 후보를 바꾸며, 이 구획에서는 다음 영업 전 최대 한 건을 계약합니다.",
    showcaseStep: 2, targetNames: ["upgrade-offers"], captionY: 218, cursorFrom: [0.48, 0.78], click: 0.70,
  },
  {
    duration: 6, image: "reservation2", kicker: "PRE-OPENING NIGHT 2/5 · GUEST OFFERS",
    title: "응대 한도와 실제 객실 여유를 따로 봅니다",
    caption: "증축으로 늘어난 응대 한도와 사용 가능 객실을 비교합니다. 연박이 생기면 현재 객실도에서 고정 위치를 확인합니다.",
    showcaseStep: 2, targetNames: ["reservation-capacity"], captionLines: 2, captionY: 490, cursorFrom: [0.40, 0.78], click: 0.72,
  },
  {
    duration: 6, image: "result3-discovery", kicker: "PRE-OPENING NIGHT 3/5 · DISCOVERY",
    title: "정산 뒤 숨은 선호를 열람합니다",
    caption: "처음 숙박한 종족×등급 조합의 추가 점수 조건은 정산 뒤 ‘숨은 선호’로 수첩에 기록됩니다.",
    showcaseStep: 3, targetNames: ["hidden-preference-discovery"], cursorFrom: [0.68, 0.76], click: 0.68,
  },
  {
    duration: 6, image: "upgrade-expansion", kicker: "PRE-OPENING NIGHT 3/5 · EAST WING CONTRACT",
    title: "동관 증축도 한 층씩 계약합니다",
    caption: "같은 영업 준비에서 F1-D → F2-D → F3-D 순서를 지키며, 동관 증축과 시설·인테리어를 각각 최대 한 건 계약합니다.",
    captionLines: 2, captionY: 166,
    showcaseStep: 3, targetNames: ["upgrade-offers"], cursorFrom: [0.44, 0.78], click: 0.70,
  },
  {
    duration: 12, image: "night4-synergy", kicker: "PRE-OPENING NIGHT 4/5 · SPECIES EFFECTS",
    title: "투숙 인원에 따라 시너지와 상극이 달라집니다",
    caption: "같은 종족이 모이면 보너스가 커지고, 상극인 종족은 같은 층에서 만족도를 낮춥니다. 연박 손님도 인원에 포함됩니다.",
    showcaseStep: 4, targetNames: ["species-effects"], captionLines: 2, captionY: 602, cursorFrom: [0.70, 0.72], click: 0.72,
  },
  {
    duration: 9, image: "reservation5-ssr", kicker: "PRE-OPENING NIGHT 5/5 · ROYAL INVITATION",
    title: "왕실 특별 초청의 위험과 보상을 비교합니다",
    caption: "높은 숙박비와 만족 보상만큼 거절 손실과 선택 조건도 커집니다. 다른 손님과의 조합까지 보고 결정합니다.",
    showcaseStep: 5, targetNames: ["ssr-invite"], captionLines: 2, captionY: 620, cursorFrom: [0.34, 0.76], click: 0.70,
  },
  {
    duration: 10, image: "night5", kicker: "PRE-OPENING NIGHT 5/5 · FINAL HOTEL OPERATIONS",
    title: "누적된 호텔 상태를 한 번에 해결합니다",
    caption: "시설·인테리어와 동관 증축, 객실 상태, 연박 손님, 종족 효과와 숨은 선호가 마지막 배치에 함께 작용합니다.",
    showcaseStep: 5, targetNames: ["species-effects"], captionLines: 2, captionY: 602, cursorFrom: [0.70, 0.74], click: 0.72,
  },
  {
    duration: 14, image: "final", kicker: "PRE-OPENING INVITATION COMPLETE",
    title: "다섯 번의 선택이 호텔의 형태를 바꿉니다",
    caption: "최종 결과는 만족도뿐 아니라 수입, 평판, 열람한 숨은 선호, 시설, 증축과 객실 상태의 누적을 함께 보여줍니다.",
    showcaseStep: 5, targetNames: [], captionLines: 2, captionY: 602, cursorFrom: [0.64, 0.74], click: 0.70,
  },
  { duration: 14, type: "outro" },
];

const TOTAL = scenes.reduce((sum, scene) => sum + scene.duration, 0);
let playhead = 0;
let playing = false;
let lastFrame = performance.now();
let ready = false;
let mediaRecorder = null;
let recordingTimer = null;
let captureTrack = null;
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
  ctx.fillText("개장 전 초청 영업", W / 2, y + 54);
  ctx.fillStyle = "#75664f";
  ctx.font = '500 16px "Malgun Gothic", sans-serif';
  ctx.fillText("개장 전, 다섯 번의 초청 영업으로 호텔을 미리 운영합니다", W / 2, y + 112);
  ctx.globalAlpha = 1;
}

function drawProgressionCard(x, y, width, title, body, accent) {
  roundedRect(x, y, width, 116, 14);
  ctx.fillStyle = "#171512";
  ctx.fill();
  ctx.strokeStyle = accent;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.textAlign = "left";
  ctx.fillStyle = accent;
  ctx.font = '800 16px "Malgun Gothic", sans-serif';
  ctx.fillText(title, x + 24, y + 36);
  ctx.fillStyle = PALE;
  ctx.font = '600 18px "Malgun Gothic", sans-serif';
  wrapText(body, x + 24, y + 73, width - 48, 26, 2);
}

function drawNotice(progress) {
  drawBackdrop();
  const reveal = ease(clamp(progress / 0.34));
  ctx.globalAlpha = reveal;
  ctx.textAlign = "center";
  ctx.fillStyle = GOLD;
  ctx.font = '800 15px "Malgun Gothic", sans-serif';
  ctx.fillText("PRE-OPENING PROGRAM NOTICE", W / 2, 84);
  ctx.fillStyle = PALE;
  const title = "정식 게임의 성장 구조를 5회 영업으로 압축했습니다";
  const titleSize = fitText(title, 1100, 45, 32);
  ctx.font = `800 ${titleSize}px "Malgun Gothic", sans-serif`;
  ctx.fillText(title, W / 2, 143);
  ctx.fillStyle = MUTED;
  ctx.font = '500 18px "Malgun Gothic", sans-serif';
  ctx.fillText("이 빌드의 빠른 등급 등장은 정식판의 성장 속도를 뜻하지 않습니다.", W / 2, 181);

  const ranks = [
    ["•", "N", "#8B9099"],
    ["◆", "R", "#4D91D1"],
    ["✦", "SR", "#9A68D1"],
    ["♛", "SSR", "#D7AA4E"],
  ];
  ranks.forEach(([symbol, rank, color], index) => {
    const appear = ease(clamp((progress - 0.10 - index * 0.06) / 0.28));
    const x = 188 + index * 230;
    const y = lerp(286, 224, appear);
    ctx.globalAlpha = reveal * appear;
    roundedRect(x, y, 204, 84, 13);
    ctx.fillStyle = "#191714";
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = rank === "SSR" ? 2.5 : 1.5;
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.font = '800 25px "Malgun Gothic", sans-serif';
    ctx.fillText(`${symbol}  ${rank}`, x + 102, y + 52);
    if (index < ranks.length - 1) {
      ctx.fillStyle = "#6f604a";
      ctx.font = '700 25px "Malgun Gothic", sans-serif';
      ctx.fillText("→", x + 217, y + 52);
    }
  });

  ctx.globalAlpha = reveal;
  drawProgressionCard(170, 356, 450, "개장 전 초청 영업", "5회 영업으로 손님·공사·호텔 성장 구조를 한눈에 확인", GOLD);
  drawProgressionCard(660, 356, 450, "정식 운영", "여러 챕터에 걸쳐 등급과 공사 후보를 점진적으로 발견", "#776b5b");
  roundedRect(170, 506, 940, 66, 12);
  ctx.fillStyle = "rgba(36,30,20,.94)";
  ctx.fill();
  ctx.strokeStyle = "#8a6934";
  ctx.stroke();
  ctx.fillStyle = PALE;
  ctx.textAlign = "center";
  ctx.font = '700 19px "Malgun Gothic", sans-serif';
  ctx.fillText("5번째 영업의 SSR은 영구 해금이 아닌 시연용 특별 초청입니다.", W / 2, 547);
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
  ctx.fillText("다섯 번의 영업, 반복되는 판단", W / 2, 184);

  const cards = [
    ["01", "규칙을 읽는다", "공개 규정과 열람한 숨은 선호 확인"],
    ["02", "손님과 공사를 고른다", "수입·거절 손실·다음 영업을 비교"],
    ["03", "배치하고 정산한다", "객실 운영을 조정하고 새 정보를 열람"],
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

function collectTargetBoxes(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    if (value.length === 4 && value.every(Number.isFinite)) return [[...value]];
    return value.flatMap(collectTargetBoxes);
  }
  if (typeof value !== "object") return [];
  if (value.visible === false) return [];
  const width = value.width ?? value.w;
  const height = value.height ?? value.h;
  if ([value.x, value.y, width, height].every(Number.isFinite)) {
    return [[value.x, value.y, width, height]];
  }
  if (value.boxes) return collectTargetBoxes(value.boxes);
  if (value.targets) return collectTargetBoxes(value.targets);
  return Object.entries(value)
    .filter(([key]) => !["cursor", "click", "cursorFrom", "cursorTo"].includes(key))
    .flatMap(([, item]) => collectTargetBoxes(item));
}

function toCanvasPoint(point) {
  if (!Array.isArray(point) || point.length < 2 || !point.slice(0, 2).every(Number.isFinite)) return null;
  const [x, y] = point;
  return [Math.abs(x) <= 1 ? x * W : x, Math.abs(y) <= 1 ? y * H : y];
}

function resolveSceneTarget(scene) {
  const key = scene.targetKey ?? scene.image;
  let source = boxTargets.frames?.[`${key}.png`]
    ?? boxTargets.frames?.[key]
    ?? boxTargets.scenes?.[key]
    ?? boxTargets.targets?.[key]
    ?? boxTargets[key]
    ?? null;
  if (!source) return { boxes: [], cursor: null, click: scene.click };
  if (Array.isArray(source)) {
    source = source.filter((item) => item?.visible !== false);
    if (Array.isArray(scene.targetNames)) {
      source = source.filter((item) => scene.targetNames.includes(item?.target));
    }
  }
  const boxes = collectTargetBoxes(source.boxes ?? source);
  let cursor = null;
  if (Array.isArray(source.cursor) && source.cursor.length === 2 && Array.isArray(source.cursor[0])) {
    const from = toCanvasPoint(source.cursor[0]);
    const to = toCanvasPoint(source.cursor[1]);
    if (from && to) cursor = [from, to];
  } else {
    const from = toCanvasPoint(source.cursorFrom ?? scene.cursorFrom ?? [0.72, 0.78]);
    const explicitTo = toCanvasPoint(source.cursorTo ?? source.cursor);
    const boxIndex = Math.min(Math.max(0, source.cursorTargetIndex ?? scene.cursorTargetIndex ?? 0), Math.max(0, boxes.length - 1));
    const box = boxes[boxIndex];
    const to = explicitTo ?? (box ? [box[0] + box[2] / 2, box[1] + box[3] / 2] : null);
    if (from && to) cursor = [from, to];
  }
  return { boxes, cursor, click: source.click ?? scene.click };
}

function drawImageScene(scene, progress) {
  const image = images[scene.image];
  ctx.drawImage(image, 0, 0, W, H);
  const target = resolveSceneTarget(scene);

  const topGradient = ctx.createLinearGradient(0, 0, 0, 190);
  topGradient.addColorStop(0, "rgba(5,4,3,.92)");
  topGradient.addColorStop(0.52, "rgba(5,4,3,.55)");
  topGradient.addColorStop(1, "rgba(5,4,3,0)");
  ctx.fillStyle = topGradient;
  ctx.fillRect(0, 0, W, 200);

  if (target.boxes.length) {
    const pulse = 0.55 + Math.sin(progress * Math.PI * 5) * 0.12;
    target.boxes.forEach(([x, y, width, height]) => {
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

  drawCaption(scene.caption, scene.captionY, scene.captionLines ?? 1);
  drawCursor(target, progress);
}

function drawCaption(caption, captionY = 618, maxLines = 1) {
  const height = maxLines > 1 ? 84 : 62;
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
  roundedRect(52, captionY, 1176, height, 10);
  ctx.fillStyle = "rgba(24,21,17,.92)";
  ctx.fill();
  ctx.strokeStyle = "rgba(224,180,87,.36)";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
  ctx.fillStyle = PALE;
  ctx.textAlign = "left";
  ctx.font = '600 19px "Malgun Gothic", sans-serif';
  wrapText(caption, 78, captionY + (maxLines > 1 ? 32 : 37), 1080, 27, maxLines);
}

function drawCursor(target, progress) {
  if (!target.cursor) return;
  const from = target.cursor[0];
  const to = target.cursor[1];
  const move = ease(clamp((progress - 0.12) / 0.58));
  const x = lerp(from[0], to[0], move);
  const y = lerp(from[1], to[1], move);
  if (target.click && Math.abs(progress - target.click) < 0.11) {
    const ring = clamp(Math.abs(progress - target.click) / 0.11);
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
  ctx.fillText("개장 전 초청 영업을 직접 플레이하세요", W / 2, 277);
  ctx.fillStyle = MUTED;
  ctx.font = '500 21px "Malgun Gothic", sans-serif';
  ctx.fillText("튜토리얼부터 다섯 번째 영업까지 공개 링크에서 실행할 수 있습니다.", W / 2, 325);

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
  ctx.fillText("베스페라 호텔 · 개장 전 초청 영업 · 2026", W / 2, 558);
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

function chromeLabel(scene, index) {
  if (Number.isInteger(scene.showcaseStep)) return `개장 전 초청 영업 · ${scene.showcaseStep}/5`;
  if (scene.chromeLabel) return scene.chromeLabel;
  if (scene.type === "notice") return "진행 속도 안내";
  if (scene.type === "loop") return "코어 루프";
  return "개장 전 초청 영업";
}

function drawChrome(scene, index) {
  const progress = playhead / TOTAL;
  ctx.fillStyle = "rgba(9,8,7,.72)";
  roundedRect(1036, 24, 190, 34, 17);
  ctx.fill();
  ctx.fillStyle = "#d3c7b5";
  ctx.textAlign = "center";
  ctx.font = '700 12px "Malgun Gothic", sans-serif';
  ctx.fillText(chromeLabel(scene, index), 1131, 45);

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
  else if (scene.type === "notice") drawNotice(local);
  else if (scene.type === "loop") drawLoop(local);
  else if (scene.type === "outro") drawOutro(local);
  else drawImageScene(scene, local);

  const fade = local < 0.055 ? 1 - local / 0.055 : local > 0.955 ? (local - 0.955) / 0.045 : 0;
  if (fade > 0) {
    ctx.fillStyle = `rgba(6,5,4,${fade * 0.82})`;
    ctx.fillRect(0, 0, W, H);
  }
  drawChrome(scene, index);
  statusLabel.textContent = `${formatTime(playhead)} / ${formatTime(TOTAL)}`;
}

function frame(now) {
  const elapsed = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  if (playing && !recordingTimer) {
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
  const videoStream = canvas.captureStream(0);
  captureTrack = videoStream.getVideoTracks()[0] ?? null;
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
    if (recordingTimer) clearInterval(recordingTimer);
    recordingTimer = null;
    captureTrack?.stop();
    captureTrack = null;
    playing = false;
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
  recordButton.textContent = `녹화 중 · ${formatTime(TOTAL)}`;
  playhead = clamp(Number(startAt) || 0, 0, TOTAL);
  playing = true;
  mediaRecorder.start(1000);
  const recordingStartPlayhead = playhead;
  const recordingStartTime = performance.now();
  const renderRecordingFrame = () => {
    playhead = Math.min(TOTAL, recordingStartPlayhead + (performance.now() - recordingStartTime) / 1000);
    render();
    captureTrack?.requestFrame?.();
    if (playhead >= TOTAL) {
      if (recordingTimer) clearInterval(recordingTimer);
      recordingTimer = null;
      playing = false;
      setTimeout(() => {
        if (mediaRecorder?.state === "recording") mediaRecorder.stop();
      }, 250);
    }
  };
  recordingTimer = setInterval(renderRecordingFrame, 1000 / 30);
  renderRecordingFrame();
}

async function loadAssets() {
  const targetPromise = fetch("box_audit/targets.json", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : {})
    .catch(() => ({}));
  const imagePromises = assetNames.map((name) => new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => {
      if (image.naturalWidth !== W || image.naturalHeight !== H) {
        reject(new Error(`영상 에셋 규격 오류: ${name}.png (${image.naturalWidth}×${image.naturalHeight})`));
        return;
      }
      images[name] = image;
      resolve();
    });
    image.addEventListener("error", () => reject(new Error(`이미지 로드 실패: ${name}`)));
    image.src = `assets/${name}.png`;
  }));
  const [targets] = await Promise.all([targetPromise, ...imagePromises]);
  boxTargets = targets && typeof targets === "object" ? targets : {};
  window.__vesperaVideoTargets = boxTargets;
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
