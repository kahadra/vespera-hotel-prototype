import { getGuestRules } from "./data.js";
import { attributeLabel, revisitBonusFor } from "./rules.js";
import { rankOddsFor } from "./progression.js";
import { canPurchaseUpgrade } from "./upgrades.js";
import { endlessAuditProgress } from "./endless.js";
import { PHASES } from "./state.js";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function signed(value) {
  return value > 0 ? `+${value}` : String(value);
}

function phaseLabel(controller) {
  const { phase } = controller.state;
  const night = controller.currentNightNumber;
  const length = controller.isEndlessMode ? controller.endlessSeasonLength : controller.totalNights;
  const season = controller.state.endlessSeasonIndex + 1;
  return {
    [PHASES.TITLE]: "영업 준비",
    [PHASES.NEW_GAME]: "새 캠페인 설정",
    [PHASES.TUTORIAL]: "배치 연습",
    [PHASES.STORY]: "시나리오",
    [PHASES.RELIC_OFFER]: "전시품 선택",
    [PHASES.ENDLESS_BRIEFING]: `시즌 ${season} 브리핑`,
    [PHASES.ENDLESS_AUDIT]: `시즌 ${season} 감사`,
    [PHASES.DAY_OPENING]: `영업 개시 ${night} / ${length}`,
    [PHASES.RESERVATION]: `예약 ${night} / ${length}`,
    [PHASES.PLACEMENT]: `영업 ${night} / ${length}`,
    [PHASES.RESULT]: `정산 ${night} / ${length}`,
    [PHASES.RESULT_REVIEW]: `마감 확인 ${night} / ${length}`,
    [PHASES.UPGRADE]: "영업 준비",
    [PHASES.FINAL]: controller.isScenarioMode
      ? "캠페인 종료"
      : controller.isEndlessMode
        ? "무한 영업 종료"
        : "초청 영업 완료",
  }[phase];
}

function rankOf(data, rankId) {
  return data.indexes.ranks[rankId] ?? { id: rankId, name: rankId, symbol: "•", color: "#8B9099" };
}

function rankTag(data, rankId, extra = "") {
  const rank = rankOf(data, rankId);
  return `<span class="rank-tag rank-${rank.id.toLowerCase()} ${extra}" style="--rank-color:${escapeHtml(rank.color)}"><i>${escapeHtml(rank.symbol)}</i><b>${escapeHtml(rank.id)}</b><small>${escapeHtml(rank.name)}</small></span>`;
}

function speciesOf(data, speciesId) {
  return data.indexes.species[speciesId] ?? { id: speciesId, name: speciesId, icon: "◇" };
}

function renderHeader(controller) {
  const { state } = controller;
  const inRun = ![PHASES.TITLE, PHASES.NEW_GAME, PHASES.TUTORIAL].includes(state.phase);
  const progressNight = state.phase === PHASES.UPGRADE
    ? Math.min(controller.currentNightNumber + 1, controller.endlessSeasonLength)
    : controller.currentNightNumber;
  const modeLabel = controller.isScenarioMode
    ? "회색 상자 캠페인"
    : controller.isEndlessMode
      ? `무한 영업 · 시즌 ${state.endlessSeasonIndex + 1}`
      : "개장 전 초청 영업";
  const progressLabel = controller.isEndlessMode
    ? ` · ${progressNight}/${controller.endlessSeasonLength}`
    : ` · ${progressNight}/${controller.totalNights}`;
  return `
    <header class="topbar">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true">◆</span>
        <div><p class="eyebrow">HOTEL VESPERA</p><strong>베스페라 호텔</strong></div>
      </div>
      <div class="phase-stack">
        <div class="phase-pill">${escapeHtml(phaseLabel(controller))}</div>
        <span class="showcase-mini">${escapeHtml(modeLabel)}${inRun ? escapeHtml(progressLabel) : ""}</span>
      </div>
      <div class="resources" aria-label="현재 자원">
        <button class="handbook-trigger" data-action="open-handbook" aria-label="운영 수첩 열기" title="운영 수첩"><span class="handbook-icon" aria-hidden="true">▤</span><span class="handbook-label">운영 수첩</span></button>
        <span><small>골드</small><b>${state.gold}G</b></span>
        <span><small>평판</small><b>${signed(state.hotelReputation)}</b></span>
        ${controller.isEndlessMode ? `<span><small>런 명성</small><b>${state.endlessRunFame}</b></span>` : ""}
      </div>
    </header>`;
}

function renderTitle(controller) {
  if (controller.isScenarioMode) return renderCampaignTitle(controller);
  if (controller.isEndlessMode) return renderEndlessTitle(controller);
  const notice = controller.data.prototype_mode?.notice
    ?? "정식 개장 전 다섯 밤 동안 호텔의 운영을 점검하는 초청 행사입니다.";
  return `
    <section class="title-screen">
      <div class="title-copy invitation-letter" data-video-target="title-invitation">
        <span class="invitation-crest" aria-hidden="true">◆</span>
        <p class="invitation-hotel">HOTEL VESPERA</p>
        <p class="invitation-recipient">새 지배인 귀하</p>
        <h1>개장 전 초청 영업에<br /><em>귀하를 모십니다.</em></h1>
        <p class="lede">손님의 조건을 읽고, 제한된 객실과 시간 안에서 가장 가치 높은 밤을 준비해 주십시오.</p>
        <div class="showcase-notice"><b>PRE-OPENING INVITATIONAL · 5 NIGHTS</b><span>${escapeHtml(notice)}</span></div>
        <div class="invitation-signoff"><span>베스페라 호텔</span><b>총지배인실</b></div>
        <div class="invitation-actions">
          ${controller.hasCheckpoint() ? `<button class="button primary large" data-action="resume">지난 영업 이어하기</button>` : ""}
          <button class="button primary large" data-action="start">배치 연습 시작</button>
          <button class="button secondary" data-action="skip-tutorial">튜토리얼 건너뛰기</button>
        </div>
      </div>
      <div class="title-rules invitation-enclosure" aria-label="개장 전 초청 영업 안내" data-video-target="showcase-summary">
        <div class="enclosure-heading"><p class="eyebrow">PRE-OPENING PROGRAM</p><h2>다섯 밤의 시범 운영</h2></div>
        <article><span>01</span><div><strong>규칙을 익히고 배치</strong><p>시간 제한 없는 연습 뒤 실제 영업은 2분 안에 진행합니다.</p></div></article>
        <article><span>02</span><div><strong>평판으로 새 등급 발견</strong><p>N·R·SR·SSR 손님과 시설의 위험과 보상을 차례로 점검합니다.</p></div></article>
        <article><span>03</span><div><strong>시설·증축·객실 상태 누적</strong><p>선택한 호텔 구조와 연박 객실이 다음 영업에 그대로 이어집니다.</p></div></article>
      </div>
    </section>`;
}

function renderCampaignTitle(controller) {
  const notice = controller.data.prototype_mode?.notice ?? "캠페인 개발 모드";
  const objective = controller.data.campaign?.objective;
  return `<section class="title-screen campaign-title-screen"><div class="title-copy invitation-letter"><span class="invitation-crest" aria-hidden="true">◆</span><p class="invitation-hotel">HOTEL VESPERA · CAMPAIGN GREYBOX</p><p class="invitation-recipient">베스페라의 상속인 귀하</p><h1>호텔의 장부를 이어받을<br /><em>새 지배인을 기다립니다.</em></h1><p class="lede">새 게임부터 영업, 장면, 성공·실패 엔딩과 기록까지 연결하는 개발용 캠페인입니다.</p><div class="showcase-notice"><b>${escapeHtml(objective?.title ?? "임시 운영 목표")}</b><span>${escapeHtml(objective?.description ?? notice)}</span></div><div class="invitation-actions">${controller.hasCheckpoint() ? `<button class="button primary large" data-action="resume">캠페인 이어하기</button>` : ""}<button class="button primary large" data-action="start">새 캠페인 시작</button></div></div><div class="title-rules invitation-enclosure"><div class="enclosure-heading"><p class="eyebrow">FUNCTIONAL SPINE</p><h2>회색 상자 검증 범위</h2></div><article><span>01</span><div><strong>새 게임과 프로필 분리</strong><p>표현 설정과 공용 수첩을 현재 캠페인 자원과 분리합니다.</p></div></article><article><span>02</span><div><strong>장면과 영업 진행</strong><p>프롤로그·비서 장면·영업·챕터 장면을 데이터 순서로 연결합니다.</p></div></article><article><span>03</span><div><strong>성공과 실패 기록</strong><p>임시 상속 조건으로 두 엔딩과 재시작·불러오기를 검증합니다.</p></div></article></div></section>`;
}

function renderEndlessTitle(controller) {
  const config = controller.data.endless;
  const best = controller.profile.endless ?? {};
  return `<section class="title-screen endless-title-screen" data-screen="endless-title"><div class="title-copy invitation-letter"><span class="invitation-crest" aria-hidden="true">∞</span><p class="invitation-hotel">HOTEL VESPERA · ENDLESS GREYBOX</p><p class="invitation-recipient">운영 기록을 이어갈 지배인 귀하</p><h1>끝을 정하지 않은 영업을<br /><em>새 가능 세계에서 시작합니다.</em></h1><p class="lede">시즌 시작 전에 공개되는 감사 목표를 넘기고, 시드마다 달라지는 손님·공사·전시품 조합으로 호텔을 오래 유지하세요.</p><div class="showcase-notice"><b>PROVISIONAL · ${config.season_length} OPERATIONS PER SEASON</b><span>${escapeHtml(controller.data.prototype_mode?.notice)}</span></div><div class="invitation-actions">${controller.hasCheckpoint() ? `<button class="button primary large" data-action="resume">저장된 무한 영업 이어하기</button>` : ""}<button class="button primary large" data-action="start">새 무한 영업 시작</button></div></div><div class="title-rules invitation-enclosure"><div class="enclosure-heading"><p class="eyebrow">SURVIVAL OPERATIONS</p><h2>공개 목표와 누적 기록</h2></div><article><span>01</span><div><strong>시즌 목표 선공개</strong><p>영업 횟수·감사 공식·목표를 첫 선택 전에 확인합니다.</p></div></article><article><span>02</span><div><strong>런 내부 빌드 누적</strong><p>골드·시설·객실 상태·전시품은 현재 가능 세계 안에서만 이어집니다.</p></div></article><article><span>03</span><div><strong>폐업과 최고 기록</strong><p>목표 미달 시 런을 마감하고 생존 영업과 통과 시즌을 남깁니다.</p></div></article><div class="endless-best"><small>프로필 최고 기록</small><b>${Number(best.best_survived_nights ?? 0)}영업 · ${Number(best.best_cleared_seasons ?? 0)}시즌 통과</b></div></div></section>`;
}

function renderEndlessBriefing(controller) {
  const { state, data } = controller;
  const audit = data.endless.audit;
  const progress = endlessAuditProgress(data, state);
  return `<section class="screen-shell endless-briefing-screen" data-screen="endless-briefing"><div class="result-hero"><p class="eyebrow">ENDLESS SEASON ${state.endlessSeasonIndex + 1} · PRE-OPERATION BRIEFING</p><span class="result-glyph">∞</span><h1>이번 시즌의 감사 조건을 먼저 확인합니다.</h1><p>이 목표는 시즌 도중 바뀌지 않으며 마지막 영업 정산을 승인할 때 한 번만 판정됩니다.</p></div><div class="audit-contract-grid"><article><small>시즌 길이</small><strong>${data.endless.season_length}회 영업</strong><span>현재 회색 상자 표본</span></article><article><small>감사 목표</small><strong>${signed(state.endlessAuditTarget)}</strong><span>개발용 감사 점수 이상</span></article><article><small>위험 단계</small><strong>TIER ${state.endlessRiskTier}</strong><span>통과 시즌에 따라 상승</span></article><article><small>런 명성</small><strong>${state.endlessRunFame}</strong><span>현재 런 누적</span></article></div><article class="audit-policy-card"><div><p class="eyebrow">PROVISIONAL AUDIT POLICY</p><h2>${escapeHtml(audit.metric_id)}</h2></div><p>${escapeHtml(audit.description)}</p><span class="status-chip ${progress.reachable ? "clear" : "warning"}">${progress.reachable ? "개발 표본상 도달 가능" : "현재 표본상 도달 불가"}</span></article><p class="provisional-note">시즌 길이·공식·목표 곡선은 기능 검증용 임시값입니다. 정식 밸런스 결정 전까지 콘텐츠 규칙으로 고정하지 않습니다.</p><div class="center-action"><button class="button primary large" data-action="start-endless-season">조건 확인 · 시즌 영업 시작</button></div></section>`;
}

function selectedButton(selected) {
  return selected ? "button primary selected" : "button secondary";
}

function renderNewGame(controller) {
  const { state } = controller;
  const roleLabels = {
    RELATIONSHIP_HUMAN: "인족 관계 인물",
    RELATIONSHIP_VAMPIRE: "뱀파이어 관계 인물",
    RELATIONSHIP_WEREWOLF: "늑대인간 관계 인물",
    RELATIONSHIP_WITCH: "마녀 관계 인물",
    RELATIONSHIP_DREAM_DEMON: "몽마 관계 인물",
  };
  const roleChoices = state.relationshipGenderPreset === "PER_ROLE"
    ? `<div class="role-presentation-list">${(controller.data.campaign?.relationship_role_ids ?? []).map((roleId) => {
      const current = state.relationshipPresentationIds[roleId];
      const femaleOnly = roleId === "RELATIONSHIP_WITCH";
      return `<div><span>${escapeHtml(roleLabels[roleId] ?? roleId)}${femaleOnly ? " · 여성 고정" : ""}</span><div><button class="${selectedButton(current === "FEMALE")}" data-action="set-relationship-role" data-role-id="${roleId}" data-presentation-id="FEMALE">여성형</button>${femaleOnly ? "" : `<button class="${selectedButton(current === "MALE")}" data-action="set-relationship-role" data-role-id="${roleId}" data-presentation-id="MALE">남성형</button>`}</div></div>`;
    }).join("")}</div>`
    : "";
  const endingRoutes = controller.data.campaign?.ending_preview_routes ?? [];
  const selectedRoute = endingRoutes.find((route) => route.id === state.greyboxEndingRouteId);
  const endingRouteChoices = `<article class="ending-preview-setup"><small>ENDING BRANCH PREVIEW</small><h2>회색 상자 엔딩 검증 경로</h2><div class="ending-preview-choices">${endingRoutes.map((route) => `<button class="${selectedButton(route.id === state.greyboxEndingRouteId)}" data-action="set-greybox-ending-route" data-route-id="${escapeHtml(route.id)}">${escapeHtml(route.label)}</button>`).join("")}</div><p><b>${escapeHtml(selectedRoute?.label ?? "노말")}</b> · ${escapeHtml(selectedRoute?.description ?? "기본 운영 결말을 검증합니다.")} 이 선택은 개발용 대역이며 정식 분기 조건을 대신하지 않습니다.</p></article>`;
  return `<section class="screen-shell new-game-screen"><div class="scene-heading"><p class="eyebrow">NEW CAMPAIGN · GREYBOX SETTINGS</p><h1>새 인간 지배인과 호텔의 표현을 정합니다</h1><p>성별 선택은 호칭·외형·개인 장면 표현만 바꾸며 일반 손님과 운영 계산에는 영향을 주지 않습니다.</p></div><div class="new-game-grid"><article><small>PLAYER · HUMAN</small><h2>인간 지배인 성별</h2><div class="choice-row"><button class="${selectedButton(state.playerGenderId === "MALE")}" data-action="set-player-gender" data-gender-id="MALE">남성</button><button class="${selectedButton(state.playerGenderId === "FEMALE")}" data-action="set-player-gender" data-gender-id="FEMALE">여성</button></div></article><article><small>SECRETARY AUTOMATA</small><h2>비서 외형</h2><div class="choice-row"><button class="${selectedButton(state.secretaryPresentationId === "FEMALE")}" data-action="set-secretary-presentation" data-presentation-id="FEMALE">여성형</button><button class="${selectedButton(state.secretaryPresentationId === "MALE")}" data-action="set-secretary-presentation" data-presentation-id="MALE">남성형</button></div></article><article class="relationship-setup"><small>RELATIONSHIP CAST</small><h2>관계 인물 구성</h2><div class="choice-row three"><button class="${selectedButton(state.relationshipGenderPreset === "ALL_FEMALE")}" data-action="set-relationship-preset" data-preset-id="ALL_FEMALE">전원 여성</button><button class="${selectedButton(state.relationshipGenderPreset === "MALE_CENTERED")}" data-action="set-relationship-preset" data-preset-id="MALE_CENTERED">남성 중심</button><button class="${selectedButton(state.relationshipGenderPreset === "PER_ROLE")}" data-action="set-relationship-preset" data-preset-id="PER_ROLE">역할별 선택</button></div>${roleChoices}<p>관계 인물은 손님으로 시작해 단골·연락책·협력 NPC로 발전합니다. 마녀 관계 인물은 모든 구성에서 여성으로 고정됩니다.</p></article>${endingRouteChoices}</div><div class="center-action"><button class="button primary large" data-action="confirm-new-game">이 설정으로 상속 장부를 연다</button></div></section>`;
}

function renderStory(controller) {
  const node = controller.currentStoryNode;
  if (!node) return `<section class="screen-shell story-screen"><h1>장면 데이터를 찾을 수 없습니다.</h1></section>`;
  return `<section class="screen-shell story-screen"><article class="story-card"><p class="eyebrow">${escapeHtml(node.eyebrow)}</p><span class="story-glyph" aria-hidden="true">◆</span><h1>${escapeHtml(node.title)}</h1>${(node.paragraphs ?? []).map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}<button class="button primary large" data-action="continue-story">장부를 계속 읽는다</button></article></section>`;
}

function renderRuleRows(rules, sourceLabel, withPoints = false) {
  if (!rules?.length) return `<p><span class="rule-source">${escapeHtml(sourceLabel)}</span>추가 조건 없음</p>`;
  return rules.map((rule) => {
    const pointText = withPoints ? ` <b>${signed(rule.points)}</b>` : "";
    return `<p><span class="rule-source">${escapeHtml(sourceLabel)}</span>${escapeHtml(rule.label)}${pointText}</p>`;
  }).join("");
}

function renderGuestChip(data, guestId, controller, options = {}) {
  const guest = data.indexes.guests[guestId];
  const species = speciesOf(data, guest.species);
  const selected = options.selected ? " selected" : "";
  const invalid = options.invalid ? " invalid" : "";
  const locked = controller.isLockedGuest(guestId);
  const score = options.score ?? null;
  const history = controller.state.guestHistory[guestId];
  const drag = locked ? "" : `data-drag-guest="${guest.id}" draggable="true"`;
  return `
    <button class="guest-chip ${guest.species.toLowerCase()} rank-border-${guest.rank.toLowerCase()}${selected}${invalid}${locked ? " stayover" : ""}"
      data-guest-id="${guest.id}" ${drag} title="${escapeHtml(guest.name)} 선택">
      <span class="guest-symbol" aria-hidden="true">${escapeHtml(species.icon)}</span>
      <span class="guest-chip-copy"><b>${history?.visits && !locked ? "↻ " : ""}${escapeHtml(guest.name)}</b><small>${escapeHtml(species.name)} · ${guest.rank}${locked ? " · 연박 고정" : history?.visits ? ` · 재방문 ${history.visits + 1}회차` : ""}</small></span>
      ${score === null ? "" : `<span class="guest-score ${score < 0 ? "negative" : ""}">${signed(score)}</span>`}
    </button>`;
}

function renderElevatorLanding(floor, compact = false) {
  return `<div class="elevator-landing${compact ? " compact" : ""}" aria-label="${floor}층 엘리베이터, A열 객실과 바로 인접"><span class="elevator-indicator" aria-hidden="true">${floor}</span><div class="elevator-doors" aria-hidden="true"><i></i><i></i></div><small>${compact ? "EV" : "승강기"}</small><span class="elevator-noise" aria-hidden="true">)))</span></div>`;
}

function renderRoom(data, room, board, occupantId, controller, evaluation) {
  const blocked = board.blockedRooms.has(room.id);
  const selected = occupantId && occupantId === controller.state.selectedGuestId;
  const invalidGuestIds = new Set(evaluation.violations.map((item) => item.guestId));
  const attrs = [...room.attributes];
  const attrText = attrs.map(attributeLabel).join(" · ") || "일반";
  const condition = controller.state.roomConditions[room.id] ?? { cleanliness: 100, durability: 100 };
  const classes = ["room-card"];
  if (room.wing === 0) classes.push("elevator-adjacent");
  if (attrs.includes("noisy")) classes.push("noisy-room");
  if (blocked) classes.push("blocked");
  if (selected) classes.push("selected-room");
  if (occupantId && invalidGuestIds.has(occupantId)) classes.push("has-violation");
  if (controller.isLockedGuest(occupantId)) classes.push("stayover-room");
  const roomAction = blocked ? "" : `data-room-id="${room.id}"`;
  const bonuses = board.roomBonuses.filter((bonus) => bonus.room_id === room.id);
  return `
    <article class="${classes.join(" ")}" ${roomAction}>
      <div class="room-heading"><b>${room.id}</b><span>${escapeHtml(attrText)}</span></div>
      <div class="room-condition" title="청결 ${condition.cleanliness}, 내구도 ${condition.durability}"><span>C ${condition.cleanliness}</span><span>D ${condition.durability}</span></div>
      <div class="room-body">
        ${blocked
          ? `<div class="facility-in-room"><span>${board.unlockedRooms.has(room.id) ? "◇" : "＋"}</span><b>${escapeHtml(board.blockedReasons.get(room.id) ?? "사용 불가")}</b></div>`
          : occupantId
            ? renderGuestChip(data, occupantId, controller, { selected, invalid: invalidGuestIds.has(occupantId), score: evaluation.guestScores[occupantId]?.preferenceTotal ?? 0 })
            : `<span class="empty-room">빈 객실</span>`}
      </div>
      ${bonuses.length ? `<span class="room-bonus">${bonuses.map((item) => `${escapeHtml(item.label)} ${signed(item.points)}`).join(" · ")}</span>` : ""}
    </article>`;
}

function renderGuestDetail(controller, evaluation) {
  const { data, state } = controller;
  const guestId = state.selectedGuestId;
  if (!guestId) return `<div class="empty-detail"><span>◇</span><p>손님을 선택하면<br />등급과 개인 선호가 표시됩니다.</p></div>`;
  const guest = data.indexes.guests[guestId];
  const species = speciesOf(data, guest.species);
  const rules = getGuestRules(data, guestId);
  const score = evaluation.guestScores[guestId]?.preferenceTotal ?? 0;
  const placedRoom = state.placements[guestId];
  const guestViolations = evaluation.violations.filter((item) => item.guestId === guestId);
  const locked = controller.isLockedGuest(guestId);
  const history = state.guestHistory[guestId];
  const revisitBonus = revisitBonusFor(data, history);
  const hiddenPreferences = rules.hiddenPreferences ?? [];
  const knownHidden = hiddenPreferences.filter((rule, index) =>
    state.discoveredHiddenPreferenceIds.includes(rule.id ?? `${guestId}:hidden:${index}`));
  const unreadHiddenCount = hiddenPreferences.length - knownHidden.length;
  return `
    <div class="detail-heading">
      <span class="detail-symbol">${escapeHtml(species.icon)}</span>
      <div><p>${escapeHtml(species.name)} · ${guest.rank}${locked ? " · 연박" : ""}</p><h2>${escapeHtml(guest.name)}</h2></div>
      <strong class="detail-score ${score < 0 ? "negative" : ""}">${signed(score)}</strong>
    </div>
    <div class="detail-rank">${rankTag(data, guest.rank)}</div>
    <div class="mini-stats">
      <span><small>숙박비</small><b>${guest.base_fee}G</b></span>
      <span><small>숙박</small><b>${guest.stay_nights ?? 1}박</b></span>
      <span><small>객실</small><b>${placedRoom ?? "대기"}</b></span>
    </div>
    <div class="inheritance-strip">
      <button data-action="open-handbook" data-tab="species"><small>종족</small>${escapeHtml(species.name)} 규정 <span>↗</span></button>
      <button data-action="open-handbook" data-tab="rank"><small>등급</small>${guest.rank} 규정 <span>↗</span></button>
    </div>
    <section class="rule-group"><h3><span class="rule-dot soft"></span> 개인 선호 <small>손님 카드 정보</small></h3>${renderRuleRows(rules.personalPreferences, "개인", true)}</section>
    ${hiddenPreferences.length ? `<section class="rule-group hidden-preference-group"><h3><span class="rule-dot hidden"></span> ${escapeHtml(species.name)} ${guest.rank} 숨은 선호 <small>${unreadHiddenCount ? `결산 전 ${unreadHiddenCount}` : "열람 완료"}</small></h3>${knownHidden.length ? renderRuleRows(knownHidden, "열람", true) : `<p class="unread-preference">첫 투숙 결산 뒤 같은 종족·등급의 공통 선호로 열람됩니다.</p>`}</section>` : ""}
    ${locked ? `<p class="revisit-bonus">연박은 같은 예약으로 이어지며 재방문 보너스는 중복되지 않습니다.</p>` : history?.visits ? `<p class="revisit-bonus">↻ 지난 숙박 기록 · 재방문 보너스 ${signed(revisitBonus)}</p>` : ""}
    ${guestViolations.length
      ? `<section class="violation-box"><h3>객실을 배정할 수 없는 이유</h3>${guestViolations.map((item) => `<p>! ${escapeHtml(item.message)}</p>`).join("")}</section>`
      : `<p class="all-clear">✓ 수첩에 기록된 공통 규정에 맞는 객실입니다.</p>`}
    ${locked
      ? `<p class="stayover-lock">연박 중인 손님은 첫날 객실을 유지합니다.</p>`
      : `<p class="drag-instruction">${placedRoom ? "대기 명단으로 드래그하면 객실에서 뺄 수 있습니다." : "객실로 드래그해 배정합니다."}</p>`}`;
}

function renderGroupEffects(evaluation) {
  if (!evaluation.groupEffects.length) return "";
  return evaluation.groupEffects.map((effect) =>
    `<span class="effect-chip ${effect.type}"><b>${effect.type === "synergy" ? "시너지" : "상극"}</b>${escapeHtml(effect.label)} ${signed(effect.points)}</span>`,
  ).join("");
}

function renderDislikeRows(rules = []) {
  if (!rules.length) return `<p class="empty-rules">등급 공통 불호 없음</p>`;
  return rules.map((rule) => `<p class="rule-row"><span>불호</span><b>${escapeHtml(rule.label)}</b><small>호텔 격차 +${rule.ignored_at_prestige_gap}부터 관용</small></p>`).join("");
}

function renderPlacement(controller) {
  const { data, state } = controller;
  const evaluation = controller.currentEvaluation();
  const board = evaluation.board;
  const occupantByRoom = Object.fromEntries(Object.entries(state.placements).map(([guestId, roomId]) => [roomId, guestId]));
  const waiting = state.acceptedGuestIds.filter((id) => !state.placements[id]);
  const isTutorial = state.phase === PHASES.TUTORIAL;
  const remainingSeconds = Math.ceil((state.serviceTimerMs ?? 0) / 1000);
  const timerClass = remainingSeconds <= 10 ? "critical" : remainingSeconds <= 30 ? "urgent" : "";
  const operationEyebrow = controller.isEndlessMode
    ? `ENDLESS SEASON ${state.endlessSeasonIndex + 1} · OPERATION ${controller.currentNightNumber} OF ${controller.endlessSeasonLength}`
    : `INVITATIONAL NIGHT ${controller.currentNightNumber} OF ${controller.totalNights}`;
  const placementStatus = isTutorial
    ? `<div class="tutorial-status" data-video-target="tutorial-clock"><small>연습 모드</small><b>시간 제한 없음</b><span>두 손님을 유효하게 배치하세요</span></div>`
    : `<div class="service-timer ${timerClass}" aria-live="polite" data-video-target="service-timer"><small>체크인 마감</small><b>${String(Math.floor(remainingSeconds / 60)).padStart(2, "0")}:${String(remainingSeconds % 60).padStart(2, "0")}</b><span>객실 변경 ${state.relocationCount}회 · ${controller.ownedRelicWithEffect("FIRST_RELOCATION_TIME_REDUCTION") && state.relocationCount === 0 ? "첫 변경 -3초" : "변경 -5초"}</span></div>`;
  const floorRows = [...new Set(data.rooms.map((room) => room.floor))].sort((a, b) => b - a).map((floor) => {
    const rooms = data.rooms.filter((room) => room.floor === floor).sort((a, b) => a.wing - b.wing);
    return `<div class="floor-row"><div class="floor-label"><b>F${floor}</b><span>${floor === 1 ? "로비층" : `${floor}층`}</span></div>${renderElevatorLanding(floor)}${rooms.map((sourceRoom) => renderRoom(data, board.rooms[sourceRoom.id], board, occupantByRoom[sourceRoom.id], controller, evaluation)).join("")}</div>`;
  }).join("");
  return `
    <section class="screen-shell placement-screen">
      <div class="screen-heading">
        <div><p class="eyebrow">${isTutorial ? "ROOM ASSIGNMENT · PRACTICE" : operationEyebrow}</p><h1>${isTutorial ? "객실 배정을 연습하세요" : `${controller.currentScenario.name} · 손님을 배치하세요`}</h1></div>
        ${placementStatus}
      </div>
      <div class="effect-strip" data-video-target="species-effects">${renderGroupEffects(evaluation)}</div>
      <div class="placement-layout">
        <section class="board-panel" data-video-target="hotel-board">
          <div class="hotel-board">${floorRows}</div>
          <div class="waiting-zone" data-waiting-zone>
            <div class="waiting-label"><b>대기 중</b><span>${state.lockedGuestIds.length ? "연박 손님은 객실 고정 · 나머지는 드래그 배정" : "손님 카드를 객실로 드래그"}</span></div>
            <div class="waiting-guests">${waiting.length ? waiting.map((id) => renderGuestChip(data, id, controller, { selected: id === state.selectedGuestId, invalid: true, score: 0 })).join("") : `<span class="all-placed">모든 손님이 객실에 들어갔습니다.</span>`}</div>
          </div>
        </section>
        <aside class="detail-panel">${renderGuestDetail(controller, evaluation)}</aside>
      </div>
      <footer class="action-bar">
        <div class="score-cluster">
          <span class="status-chip ${evaluation.valid ? "clear" : "warning"}">${evaluation.valid ? "객실 배정 가능" : `배정 불가 ${evaluation.violations.length}건`}</span>
          <span><small>현재 선호 점수</small><b>${evaluation.placementScore}</b></span>
          <span><small>배치 인원</small><b>${Object.keys(state.placements).length} / ${state.acceptedGuestIds.length}</b></span>
        </div>
        <div class="placement-actions">${isTutorial ? `<button class="button secondary" data-action="skip-tutorial">연습 건너뛰기</button>` : ""}<button class="button primary" data-action="finish-night" ${evaluation.valid ? "" : "disabled"}>${isTutorial ? "연습 완료 · 첫 영업 시작" : "밤 마감하기"}</button></div>
      </footer>
    </section>`;
}

function renderOddsStrip(data, odds, target = "rank-odds") {
  return `<div class="odds-strip" data-video-target="${target}"><div><small>현재 평판 기준</small><b>일반 신청 확률</b></div>${data.ranks.map((rank) => `<span class="odds-rank rank-${rank.id.toLowerCase()}" style="--rank-color:${escapeHtml(rank.color)}"><i>${escapeHtml(rank.symbol)}</i><b>${rank.id}</b><strong>${odds[rank.id] ?? 0}%</strong></span>`).join("")}</div>`;
}

function resultBreakdown(controller, result) {
  const names = (ids) => ids.length ? ids.map((id) => controller.data.indexes.guests[id]?.name ?? id).join(", ") : "없음";
  const emergency = result.emergencyReport;
  return `
    ${emergency ? `<section class="emergency-report"><div><p class="eyebrow">CHECK-IN DEADLINE</p><h2>마감 후 프런트 긴급 배정</h2></div><p><b>자동 배정</b> ${escapeHtml(names(emergency.autoAssignedGuestIds))}<br /><b>강제 취소</b> ${escapeHtml(names(result.canceledGuestIds))}</p></section>` : ""}
    <div class="result-grid" data-video-target="night-result">
      <article><small>선호 점수 합계</small><strong>${result.placementScore}</strong><span>선호·시너지·상극 합산</span></article>
      <article><small>평판 변화</small><strong>${signed(result.reputationDelta)}</strong><span>후기·거절·취소 합산</span></article>
      <article><small>기본 숙박비</small><strong>${result.baseFees}G</strong><span>수용 손님</span></article>
      <article><small>팁</small><strong>${result.tips}G</strong><span>선호 점수 환산</span></article>
      <article class="featured"><small>총수입</small><strong>${result.income}G</strong><span>${result.relicBonusGold ? `전시품 보너스 +${result.relicBonusGold}G 포함` : "이번 영업"}</span></article>
      <article class="featured"><small>영업 평가</small><strong>${escapeHtml(result.grade)}</strong><span>손님별 후기 종합</span></article>
    </div>
    <div class="result-notes"><p><b>수용:</b> ${escapeHtml(names(result.acceptedGuestIds))}</p><p><b>거절:</b> ${escapeHtml(names(result.rejectedGuestIds))}</p>${result.canceledGuestIds?.length ? `<p class="canceled"><b>수용 후 취소:</b> ${escapeHtml(names(result.canceledGuestIds))}</p>` : ""}</div>`;
}

function renderGuestReviews(controller, result) {
  const reviews = result.guestReviews ?? [];
  if (!reviews.length) return "";
  const reactionLabel = {
    positive: "호평",
    neutral: "무난",
    negative: "아쉬움",
  };
  return `<section class="guest-review-section" data-video-target="guest-reviews"><div class="guest-review-heading"><p class="eyebrow">GUEST REVIEWS</p><h3>오늘의 투숙 후기</h3><p>내부 만족도 수치 대신 손님이 기억한 경험과 평판 영향을 확인합니다.</p></div><div class="guest-review-grid">${reviews.map((review) => {
    const guest = controller.data.indexes.guests[review.guestId];
    return `<article class="guest-review-card ${review.reaction}"><div><span>${escapeHtml(reactionLabel[review.reaction] ?? review.reaction)}</span>${rankTag(controller.data, guest.rank)}</div><h4>${escapeHtml(guest.name)} · ${escapeHtml(review.headline)}</h4><p>“${escapeHtml(review.comment)}”</p><small>평판 영향 ${signed(review.reputationImpact)} · ${escapeHtml(review.reputationInfluenceLabel)}</small></article>`;
  }).join("")}</div></section>`;
}

function renderRoomWear(controller) {
  const rows = controller.state.lastRoomWear.filter((item) => item.cleanlinessLoss || item.durabilityLoss);
  if (!rows.length) return "";
  return `<section class="wear-report"><div><p class="eyebrow">ROOM CONDITION</p><h3>오늘 밤 객실 상태 변화</h3></div><div>${rows.slice(0, 5).map((item) => `<span><b>${item.roomId}</b> 청결 -${item.cleanlinessLoss} · 내구 -${item.durabilityLoss}${controller.state.stayovers[item.guestId] ? " · 연박 고정" : ""}</span>`).join("")}</div></section>`;
}

function renderDiscoveries(controller) {
  const discoveries = controller.state.lastDiscoveries;
  if (!discoveries.length) return "";
  return `<section class="discovery-report" data-video-target="hidden-preference-discovery"><div><p class="eyebrow">SPECIES PREFERENCE REVEALED</p><h3>종족·등급 숨은 선호를 열람했습니다</h3></div><div>${discoveries.map((item) => `<span><b>${escapeHtml(controller.data.indexes.species[item.speciesId]?.name ?? item.speciesId)} · ${escapeHtml(item.rankId)}</b>${escapeHtml(item.label)} ${signed(item.points)}</span>`).join("")}</div></section>`;
}

function renderResultActions(controller, isLast) {
  if (controller.isScenarioMode) {
    return `<div class="center-action"><button class="button primary large" data-action="open-result-review">비서에게 마감 장부를 건넨다</button></div>`;
  }
  const continueLabel = isLast ? "초청 영업 종합 결과" : "객실 정비와 공사 준비";
  if (controller.isEndlessMode) {
    return `<div class="center-action split-actions"><button class="button secondary large" data-action="retry-stage">이번 영업 다시</button><button class="button primary large" data-action="continue-result">${isLast ? "시즌 감사 확인" : "객실 정비와 다음 영업"}</button></div>`;
  }
  return `<div class="center-action"><button class="button primary large" data-action="continue-result">${continueLabel}</button></div>`;
}

function renderResult(controller) {
  const result = controller.currentResult;
  const runLength = controller.isEndlessMode ? controller.endlessSeasonLength : controller.totalNights;
  const isLast = controller.currentNightNumber >= runLength;
  const nextOdds = isLast ? null : rankOddsFor(controller.data, controller.nextProgressionStage, controller.state.hotelReputation);
  const eyebrow = controller.isScenarioMode
    ? `CAMPAIGN DAY ${controller.currentNightNumber} COMPLETE`
    : controller.isEndlessMode
      ? `ENDLESS SEASON ${controller.state.endlessSeasonIndex + 1} · OPERATION ${controller.currentNightNumber} COMPLETE`
      : `PRE-OPENING NIGHT ${controller.currentNightNumber} COMPLETE`;
  const summary = controller.isScenarioMode
    ? (isLast ? "상속 유지 조건을 판정할 마지막 장부입니다." : "마감 서명 뒤 캠페인 장부와 다음 영업으로 진행합니다.")
    : controller.isEndlessMode
      ? (isLast ? "이 정산을 받아들이면 사전 공개된 시즌 감사를 판정합니다." : "정산을 받아들이면 현재 결과가 확정되고 다음 영업을 준비합니다.")
      : (isLast ? "개장 전 다섯 밤의 운영 기록을 확인합니다." : "수입과 평판이 다음 손님과 시설 제안의 범위를 바꿉니다.");
  return `
    <section class="screen-shell result-screen">
      <div class="result-hero"><p class="eyebrow">${escapeHtml(eyebrow)}</p><span class="result-glyph">✦</span><h1>${controller.currentNightNumber}번째 영업을 마쳤습니다.</h1><p>${escapeHtml(summary)}</p></div>
      ${resultBreakdown(controller, result)}
      ${renderGuestReviews(controller, result)}
      <div class="result-operational-reports">
        ${renderDiscoveries(controller)}
        ${renderRoomWear(controller)}
      </div>
      ${nextOdds ? renderOddsStrip(controller.data, nextOdds, "next-rank-odds") : ""}
      ${renderResultActions(controller, isLast)}
    </section>`;
}

function secretaryPortrait(controller) {
  const presentationId = controller.state.secretaryPresentationId;
  const presentationClass = presentationId === "MALE" ? "male" : "female";
  return `<div class="secretary-portrait ${presentationClass}" aria-label="비서 오토마타"><span aria-hidden="true">◇</span><small>SECRETARY AUTOMATA</small></div>`;
}

function renderFormalOperatingForecast(controller) {
  const forecast = controller.formalCampaignOperatingForecast();
  if (!forecast) return "";
  return `<section class="audit-contract-grid" data-formal-operating-forecast><article><small>다음 유지비</small><strong data-formal-operating-value="nextUpkeep">${forecast.nextUpkeep}G</strong><span>현재 시설 기준</span></article><article><small>가용 현금</small><strong data-formal-operating-value="cashOnHand">${forecast.cashOnHand}G</strong><span>선택 상환 반영</span></article><article><small>대기 비용</small><strong data-formal-operating-value="pendingExpense">${forecast.pendingExpense}G</strong><span>공사·객실 정비</span></article><article><small>최소 필요 수입</small><strong data-formal-operating-value="minimumIncomeRequired">${forecast.minimumIncomeRequired}G</strong><span>다음 영업 유지 조건</span></article></section>`;
}

function renderDayOpening(controller) {
  const repeated = controller.state.foresightRetryCount > 0;
  return `<section class="screen-shell secretary-scene day-opening-scene"><div class="scene-heading"><p class="eyebrow">MORNING BRIEFING · DAY ${controller.currentNightNumber}</p><h1>영업 개시 보고</h1></div><div class="secretary-dialogue">${secretaryPortrait(controller)}<article><small>비서 오토마타</small><p>${repeated ? "잠시만요. 처음 펼친 장부인데… 지배인님께서는 다음 항목을 이미 알고 계신 표정이군요." : "좋은 아침입니다, 지배인님. 오늘 접수된 예약과 객실 현황을 순서대로 읽어 드리겠습니다."}</p><p>준비가 끝나는 대로 예약 장부를 개방하겠습니다.</p></article></div>${renderFormalOperatingForecast(controller)}<div class="center-action"><button class="button primary large" data-action="start-day-business">오늘 영업을 개시한다</button></div></section>`;
}

function renderDisplayRelicOffer(controller) {
  const pending = controller.state.pendingDisplayRelicOffer;
  const relics = (pending?.relicIds ?? [])
    .map((id) => controller.data.indexes.displayRelics?.[id])
    .filter(Boolean);
  const heading = controller.isEndlessMode
    ? `시즌 ${controller.state.endlessSeasonIndex + 1} 영업에 앞서 전시품 후보를 확인합니다.`
    : "첫 영업에 앞서 전시품 하나를 개방합니다.";
  const duration = controller.isEndlessMode
    ? "선택한 전시품은 현재 무한 영업 런이 끝날 때까지 누적됩니다."
    : "선택한 전시품은 이번 캠페인이 끝날 때까지 로비에서 운영을 보조합니다.";
  return `<section class="screen-shell relic-offer-screen">
    <div class="scene-heading"><p class="eyebrow">INHERITED DISPLAY · ONE OF THREE</p><h1>${escapeHtml(heading)}</h1><p>${escapeHtml(duration)}</p></div>
    <div class="relic-offer-grid" data-video-target="display-relic-offer">${relics.map((relic) => `<article class="relic-offer-card"><span class="relic-icon">${escapeHtml(relic.icon)}</span><small>공용 전시품 · 임시 명세</small><h2>${escapeHtml(relic.name)}</h2><p>${escapeHtml(relic.description)}</p><div><b>발동 조건</b><span>${escapeHtml(relic.trigger_description)}</span></div><button class="button primary" data-action="select-display-relic" data-relic-id="${escapeHtml(relic.id)}">이 전시품을 개방한다</button></article>`).join("")}</div>
    <div class="relic-offer-footer"><p class="relic-offer-note">전시품은 필수 숙박 조건을 무시하거나 객실 배치를 자동 해결하지 않습니다.</p><button class="button secondary" data-action="skip-display-relic">전시품 없이 시작한다</button></div>
  </section>`;
}

function renderResultReview(controller) {
  const finance = controller.state.campaignFinance;
  const canRepay = controller.isFormalCampaignMode
    && finance?.pendingDayResult?.stageNumber <= 56;
  const repaymentLimit = canRepay ? Math.min(finance.cash, finance.remainingDebt) : 0;
  const repaymentForecast = canRepay ? controller.formalCampaignRepaymentForecast() : null;
  const repayment = canRepay
    ? `<section class="maintenance-panel" data-formal-repayment><div><p class="eyebrow">DEBT REPAYMENT</p><h2>추가 상환</h2><p>이번 정산에서 상환할 금액을 직접 정합니다.<span data-formal-repayment-forecast>${repaymentForecast ? ` 다음 허들 ${repaymentForecast.nextCheckpointStage}일 · 남은 목표 ${repaymentForecast.remainingAmount}G` : ""}</span></p></div><label>선택 상환액 <input type="number" min="0" max="${repaymentLimit}" step="1" value="${controller.state.campaignSelectedRepayment}" data-formal-repayment-input />G</label></section>`
    : "";
  return `<section class="screen-shell secretary-scene result-review-scene"><div class="scene-heading"><p class="eyebrow">CLOSING REPORT · DAY ${controller.currentNightNumber}</p><h1>마감 확인</h1></div><div class="secretary-dialogue">${secretaryPortrait(controller)}<article><small>비서 오토마타</small><p>오늘 장부의 수입, 평판과 객실 변동을 모두 정리했습니다.</p><p>이 내용으로 마감 서명을 남길까요, 지배인님?</p></article></div>${repayment}${renderFormalOperatingForecast(controller)}<div class="center-action split-actions"><button class="button secondary large" data-action="restart-day-through-secretary">아침 장부부터 다시 읽어 줘.</button><button class="button primary large" data-action="accept-secretary-report">이대로 서명하지.</button></div></section>`;
}

function renderMaintenance(controller) {
  const cost = controller.roomServiceCost();
  const baseCost = controller.data.balance?.room_service_cost ?? 8;
  const occupied = new Set(Object.values(controller.state.stayovers).map((entry) => entry.roomId));
  const structurallyBlocked = controller.structuralBoardState().blockedRooms;
  const worn = Object.entries(controller.state.roomConditions).filter(([roomId, condition]) =>
    !structurallyBlocked.has(roomId)
    && (condition.cleanliness < 100 || condition.durability < 100));
  if (!worn.length) return `<p class="maintenance-clear">모든 객실 상태가 양호합니다.</p>`;
  return `<div class="maintenance-list">${worn.slice(0, 6).map(([roomId, condition]) => {
    const disabled = occupied.has(roomId) || controller.state.gold < cost;
    return `<button data-action="service-room" data-room-id="${roomId}" ${disabled ? "disabled" : ""}><b>${roomId}</b><span>청결 ${condition.cleanliness} · 내구 ${condition.durability}</span><small>${occupied.has(roomId) ? "연박 중" : `${cost}G 정비${cost < baseCost ? ` · 전시품 -${baseCost - cost}G` : ""}`}</small></button>`;
  }).join("")}</div>`;
}

function renderRenovationCard(controller, upgrade) {
  const { data, state } = controller;
  const purchased = state.renovationPurchaseIds.includes(upgrade.id);
  const contractedKind = state.renovationPurchaseIds.some(
    (id) => data.indexes.upgrades[id]?.kind === upgrade.kind,
  );
  const affordable = state.gold >= upgrade.cost;
  const prerequisiteMet = purchased || canPurchaseUpgrade(data, upgrade.id, state.ownedUpgradeIds);
  const stayoverBlocked = !purchased && controller.upgradeBlockedByStayover(upgrade.id);
  const buildable = prerequisiteMet && !stayoverBlocked;
  const enabled = !purchased && !contractedKind && affordable && buildable;
  const prerequisite = (upgrade.requires ?? []).map((id) => data.indexes.upgrades[id]?.name ?? id).join(", ");
  const status = purchased
    ? "계약 완료"
    : contractedKind
      ? "이번 준비의 계약 완료"
      : stayoverBlocked
        ? "연박 객실은 공사 불가"
        : !prerequisiteMet
          ? "아래층 증축 필요"
          : affordable
            ? "계약 가능"
            : `${upgrade.cost - state.gold}G 부족`;
  const buttonLabel = purchased
    ? "계약 완료"
    : upgrade.kind === "EXPANSION"
      ? "증축 계약"
      : "설치 계약";
  return `<article class="facility-card rarity-${upgrade.rarity.toLowerCase()} ${enabled ? "" : "locked"} ${purchased ? "contracted" : ""}" style="--rank-color:${escapeHtml(rankOf(data, upgrade.rarity).color)}">
    <div class="facility-card-top"><span class="facility-icon">${escapeHtml(upgrade.icon ?? "◇")}</span>${rankTag(data, upgrade.rarity)}</div>
    <p class="eyebrow">${escapeHtml(upgrade.kind === "EXPANSION" ? "EAST WING EXPANSION" : "FACILITY & INTERIOR")}</p>
    <h2>${escapeHtml(upgrade.name)}</h2><p>${escapeHtml(upgrade.description)}</p>
    ${prerequisite ? `<p class="upgrade-prerequisite">선행 공사: ${escapeHtml(prerequisite)}</p>` : ""}
    <div class="facility-price"><b>${upgrade.cost}G</b>${status}</div>
    <button class="button ${enabled ? "primary" : "muted"}" data-action="buy-upgrade" data-upgrade-id="${upgrade.id}" ${enabled ? "" : "disabled"}>${buttonLabel}</button>
  </article>`;
}

function renderUpgrade(controller) {
  const { data, state } = controller;
  const nextStage = controller.nextProgressionStage;
  const nextOperation = controller.currentNightNumber + 1;
  const odds = rankOddsFor(data, nextStage, state.hotelReputation);
  const upgrades = state.currentUpgradeOfferIds.map((id) => data.indexes.upgrades[id]).filter(Boolean);
  const expansions = upgrades.filter((upgrade) => upgrade.kind === "EXPANSION");
  const interiors = upgrades.filter((upgrade) => upgrade.kind === "FACILITY");
  const builtExpansionCount = state.ownedUpgradeIds.filter((id) => data.indexes.upgrades[id]?.kind === "EXPANSION").length;
  const installedFacilityCount = state.ownedUpgradeIds.filter((id) => data.indexes.upgrades[id]?.kind === "FACILITY").length;
  const hasContracts = state.renovationPurchaseIds.length > 0;
  const nextServiceLabel = controller.isEndlessMode
    ? `SEASON ${state.endlessSeasonIndex + 1} · NEXT OPERATION ${nextOperation}/${controller.endlessSeasonLength} · RUN STAGE ${nextStage}`
    : `NEXT SERVICE ${nextStage}/${controller.totalNights}`;
  return `
    <section class="screen-shell shop-screen">
      <div class="screen-heading"><div><p class="eyebrow">HOTEL RENOVATION · ${escapeHtml(nextServiceLabel)}</p><h1>다음 영업을 위한 공사를 준비하세요.</h1></div><p>보유 골드 <b>${state.gold}G</b> · 증축 ${builtExpansionCount} · 시설 ${installedFacilityCount}</p></div>
      ${renderFormalOperatingForecast(controller)}
      ${renderOddsStrip(data, odds, "upgrade-rank-odds")}
      <section class="maintenance-panel"><div><p class="eyebrow">HOUSEKEEPING</p><h2>객실 정비</h2><p>연박 중인 객실은 이동하거나 정비할 수 없습니다.</p></div>${renderMaintenance(controller)}</section>
      <div class="renovation-layout" data-video-target="upgrade-offers">
        <section class="renovation-group expansion-group"><header><div><p class="eyebrow">BUILDING WORKS</p><h2>동관 증축</h2></div><span>이번 준비 최대 1건</span></header><p class="renovation-help">아래층부터 객실을 올려 객실 배정 선택지를 넓힙니다.</p><div class="renovation-cards">${expansions.length ? expansions.map((upgrade) => renderRenovationCard(controller, upgrade)).join("") : `<p class="renovation-empty">현재 계약 가능한 증축 공사가 없습니다.</p>`}</div></section>
        <section class="renovation-group interior-group"><header><div><p class="eyebrow">INTERIOR OFFICE</p><h2>시설·인테리어</h2></div><span>이번 준비 최대 1건</span></header><p class="renovation-help">기존 객실의 성격과 호텔 동선을 바꿉니다.</p><div class="renovation-cards interior-cards">${interiors.length ? interiors.map((upgrade) => renderRenovationCard(controller, upgrade)).join("") : `<p class="renovation-empty">현재 설치 가능한 시설 제안이 없습니다.</p>`}</div></section>
      </div>
      <div class="shop-footer"><p>공사업체 제안은 호텔 평판에 따라 달라집니다. 동관은 1층 → 2층 → 3층 순서로 증축합니다.</p><button class="button ${hasContracts ? "primary" : "secondary"}" data-action="finish-upgrade">${hasContracts ? "준비 완료 · 다음 영업" : "공사 없이 다음 영업"}</button></div>
    </section>`;
}

function renderReservationCard(controller, guestId) {
  const { data, state } = controller;
  const guest = data.indexes.guests[guestId];
  const species = speciesOf(data, guest.species);
  const decision = state.applicantDecisions[guestId];
  const rules = getGuestRules(data, guestId);
  const special = state.specialInviteGuestIds.includes(guestId);
  const history = state.guestHistory[guestId];
  const lastReactionLabel = { positive: "호평", neutral: "무난", negative: "아쉬움" }[history?.lastReaction] ?? "무난";
  const revisitBonus = revisitBonusFor(data, history);
  const wearScale = data.balance?.wear_scale ?? 1;
  const cleanlinessLoss = guest.room_wear?.cleanliness ?? (guest.cleanliness_impact ?? 1) * wearScale;
  const durabilityLoss = guest.room_wear?.durability ?? (guest.durability_impact ?? 0) * wearScale;
  return `
    <article class="reservation-card rarity-${guest.rank.toLowerCase()} ${decision ?? "pending"} ${special ? "special-invite" : ""}" style="--rank-color:${escapeHtml(rankOf(data, guest.rank).color)}" ${special ? "data-video-target=ssr-invite" : ""}>
      ${special ? `<div class="special-ribbon">왕실 특별 초청</div>` : ""}
      <div class="reservation-top"><span class="reservation-symbol">${escapeHtml(species.icon)}</span><div><p>${escapeHtml(species.name)} · ${guest.stay_nights ?? 1}박</p><h2>${escapeHtml(guest.name)}</h2></div>${rankTag(data, guest.rank, "compact")}</div>
      <div class="reservation-stats"><span><small>숙박비</small><b>${guest.base_fee}G</b></span><span><small>평판 영향</small><b>${escapeHtml(rankOf(data, guest.rank).reputation_influence_label)}</b></span><span><small>거절</small><b>${guest.reject_reputation}</b></span></div>
      <div class="reservation-rules"><p><b>공개 개인 선호 ${rules.personalPreferences.length}</b> · ${rules.personalPreferences.map((rule) => `${escapeHtml(rule.label)} ${signed(rule.points)}`).join(", ")}</p><p><b>등급 기대</b> · 선호 ${rules.rankPreferences.length}개, 불호 ${rules.rankDislikes.length}개</p>${(rules.hiddenPreferences ?? []).length ? `<p><b>${escapeHtml(species.name)} ${guest.rank} 숨은 선호</b> · ${(rules.hiddenPreferences ?? []).length}개 · 투숙 결산 후 열람</p>` : ""}${history?.visits ? `<p class="revisit-copy"><b>재방문</b> · 지난 후기 ${lastReactionLabel}, 이번 보너스 ${signed(revisitBonus)}</p>` : ""}<p><b>객실 영향</b> · 청결 -${cleanlinessLoss}, 내구 -${durabilityLoss}</p></div>
      <div class="decision-buttons"><button class="button small accept" data-action="accept" data-guest-id="${guestId}">수용</button><button class="button small reject" data-action="reject" data-guest-id="${guestId}">거절</button></div>
      ${decision ? `<div class="decision-stamp">${decision === "accept" ? "수용 예정" : "거절 예정"}</div>` : ""}
    </article>`;
}

function renderReservation(controller) {
  const { data, state } = controller;
  const summary = controller.reservationSummary();
  const fixedArrivalIds = state.currentFixedGuestIds.filter((id) => !controller.isLockedGuest(id));
  const fixedNames = fixedArrivalIds.map((id) => data.indexes.guests[id].name).join(", ") || "없음";
  const stayoverEntries = Object.entries(state.stayovers);
  const stayoverPreview = stayoverEntries.length
    ? stayoverEntries.map(([guestId, entry]) => `${data.indexes.guests[guestId]?.name ?? guestId} ${entry.roomId}`).join(", ")
    : "없음";
  const emptySelection = !summary.pending.length && summary.accepted.length === 0;
  const ready = !summary.pending.length
    && !summary.overCapacity
    && !summary.overPhysicalCapacity
    && !emptySelection;
  const guaranteedRank = controller.currentScenario.guaranteed_rank;
  const guaranteedRankInfo = guaranteedRank ? rankOf(data, guaranteedRank) : null;
  const operationEyebrow = controller.isEndlessMode
    ? `ENDLESS SEASON ${state.endlessSeasonIndex + 1} · OPERATION ${controller.currentNightNumber} OF ${controller.endlessSeasonLength} · GUEST APPLICATIONS`
    : `PRE-OPENING NIGHT ${controller.currentNightNumber} OF ${controller.totalNights} · GUEST APPLICATIONS`;
  const guaranteeLabel = controller.isEndlessMode ? "등급 신청 보장" : "등급 체험 초청";
  const guaranteeDescription = controller.isEndlessMode
    ? "현재 위험 단계의 손님 풀을 검증하기 위한 개발용 최소 등급 보장입니다. 일반 신청 확률과 별도로 도착합니다."
    : "해당 등급의 응대 규정을 점검하기 위한 별도 초청 1명입니다. 아래 일반 신청 확률과는 따로 도착합니다.";
  return `
    <section class="screen-shell reservation-screen">
      <div class="screen-heading"><div><p class="eyebrow">${escapeHtml(operationEyebrow)}</p><h1>${controller.currentScenario.name} · 누구를 맞이하시겠습니까?</h1></div><div class="reservation-fixed-summary"><span><small>사전 확정</small><b>${escapeHtml(fixedNames)}</b></span><span><small>연박 고정 객실</small><b>${escapeHtml(stayoverPreview)}</b></span><button data-action="open-reservation-board">현재 객실도 보기</button></div></div>
      ${state.specialInviteGuestIds.length ? `<div class="showcase-invite-banner"><b>♛ SSR 왕실 특별 초청</b><span>최종 등급의 까다로운 요청과 높은 보상이 함께 도착했습니다.</span></div>` : ""}
      ${guaranteedRankInfo && !state.specialInviteGuestIds.length ? `<div class="showcase-guarantee-banner"><b>${escapeHtml(guaranteedRankInfo.symbol)} ${escapeHtml(guaranteedRank)} ${escapeHtml(guaranteeLabel)}</b><span>${escapeHtml(guaranteeDescription)}</span></div>` : ""}
      ${renderOddsStrip(data, state.currentRankOdds, "reservation-rank-odds")}
      <div class="reservation-grid">${state.currentGuestOfferIds.map((id) => renderReservationCard(controller, id)).join("")}</div>
      <footer class="action-bar reservation-capacity-bar" data-video-target="reservation-capacity"><div class="score-cluster"><span class="status-chip ${summary.overCapacity || summary.overPhysicalCapacity ? "warning" : "clear"}">응대 ${summary.accepted.length} / ${summary.serviceLimit}</span><span><small>호텔 객실</small><b>${summary.builtRoomCount}실</b></span><span><small>사용 가능</small><b>${summary.physicalPlacementLimit}실</b></span><span><small>배정 여유</small><b>${summary.placementMargin}실</b></span><span><small>미결정</small><b>${summary.pending.length}</b></span></div><div class="reservation-confirm"><small>인원 여유는 필수 숙박 조건의 조합까지 보장하지 않습니다.</small><button class="button primary" data-action="confirm-reservation" ${ready ? "" : "disabled"}>명단 확정 · 2분 체크인</button></div></footer>
      ${summary.overCapacity ? `<p class="inline-warning">예약 응대 한도를 넘었습니다. 동관 객실을 한 실 증축할 때마다 한 명을 더 맞을 수 있습니다.</p>` : ""}
      ${summary.overPhysicalCapacity ? `<p class="inline-warning">현재 사용 가능한 객실보다 손님이 많습니다. 수용 손님을 줄이거나 객실을 정비하세요.</p>` : ""}
      ${emptySelection ? `<p class="inline-warning">호텔 문을 열려면 최소 한 명의 예약을 수용해야 합니다.</p>` : ""}
    </section>`;
}

function renderReservationBoard(controller) {
  if (!controller.state.reservationBoardOpen) return "";
  const { data, state } = controller;
  const metrics = controller.roomCapacitySummary();
  const stayoverByRoom = Object.fromEntries(
    Object.entries(state.stayovers).map(([guestId, entry]) => [entry.roomId, { guestId, ...entry }]),
  );
  const rows = [...new Set(data.rooms.map((room) => room.floor))].sort((a, b) => b - a).map((floor) => {
    const rooms = data.rooms.filter((room) => room.floor === floor).sort((a, b) => a.wing - b.wing);
    return `<div class="occupancy-floor"><b>F${floor}</b>${renderElevatorLanding(floor, true)}${rooms.map((room) => {
      const stayover = stayoverByRoom[room.id];
      const built = metrics.board.unlockedRooms.has(room.id);
      const unavailable = built && metrics.board.blockedRooms.has(room.id);
      const roomState = !built ? "unbuilt" : unavailable ? "unavailable" : stayover ? "stayover" : "empty";
      const label = !built
        ? "미증축"
        : unavailable
          ? metrics.board.blockedReasons.get(room.id) ?? "사용 불가"
          : stayover
            ? `${data.indexes.guests[stayover.guestId]?.name ?? stayover.guestId} · ${stayover.remainingNights}박 남음`
            : "빈 객실";
      return `<article class="occupancy-room ${roomState}" data-room-id="${escapeHtml(room.id)}" data-room-state="${roomState}"><span>${escapeHtml(room.id)}</span><b>${escapeHtml(label)}</b></article>`;
    }).join("")}</div>`;
  }).join("");
  return `<div class="reservation-board-overlay" role="dialog" aria-modal="true" aria-label="현재 객실 배치도"><section class="reservation-board-panel"><header><div><p class="eyebrow">CURRENT ROOM LEDGER</p><h1>현재 객실 배치도</h1><p>연박 손님의 객실은 고정됩니다. 사전 확정 손님은 체크인 단계에서 빈 객실에 배정합니다.</p></div><button class="handbook-close" data-action="close-reservation-board" aria-label="현재 객실 배치도 닫기">×</button></header><div class="occupancy-metrics"><span><small>완공 객실</small><b>${metrics.builtRoomCount}실</b></span><span><small>오늘 응대 한도</small><b>${metrics.serviceLimit}명</b></span><span><small>사용 가능 객실</small><b>${metrics.physicalPlacementLimit}실</b></span><span><small>연박 고정</small><b>${metrics.stayoverRoomIds.length}실</b></span></div><div class="reservation-mini-board" data-video-target="reservation-existing-layout">${rows}</div><div class="occupancy-legend"><span class="stayover">연박 고정</span><span class="unavailable">정비·시설로 사용 불가</span><span class="unbuilt">미증축</span><span class="empty">빈 객실</span></div><p class="occupancy-risk">응대 한도와 객실 수가 남아 있어도 종족·등급의 필수 숙박 조건 조합에 따라 전원 배정에 실패할 수 있습니다.</p></section></div>`;
}

function handbookTabs(controller) {
  const tabs = [["hotel", "호텔 규정"], ["species", "종족"], ["rank", "등급"]];
  if ((controller.data.display_relics ?? []).length) tabs.push(["relics", "전시품"]);
  tabs.push(["discoveries", "발견·해금"]);
  return tabs.map(([id, label]) => `<button class="handbook-tab ${controller.state.handbookTab === id ? "active" : ""}" data-action="handbook-tab" data-tab="${id}">${label}</button>`).join("");
}

function renderHotelRulesPage() {
  return `<div class="handbook-page"><div class="handbook-page-heading"><p class="eyebrow">FRONT DESK STANDARD</p><h2>호텔 공통 규정</h2><p>모든 영업과 손님에게 적용되는 기본 규칙입니다.</p></div><div class="manual-rule-grid">
    <article><span>01</span><div><h3>수용한 손님은 모두 배정</h3><p>모든 필수 조건을 맞춰야 밤을 마감할 수 있습니다.</p></div></article>
    <article><span>02</span><div><h3>객실 하나에 손님 한 명</h3><p>한 객실을 둘이 함께 사용할 수 없습니다.</p></div></article>
    <article><span>03</span><div><h3>연박 객실은 다음 날 고정</h3><p>연박 손님은 첫날 배정한 객실을 유지하며 수용 인원과 종족 효과에 포함됩니다.</p></div></article>
    <article><span>04</span><div><h3>SR·SSR의 공실 요청은 선호</h3><p>양옆 공실은 고득점 선택이지 필수 규정이 아닙니다. 증축 없이도 유효한 운영이 가능합니다.</p></div></article>
    <article><span>05</span><div><h3>증축 객실 한 실마다 응대 한 명 증가</h3><p>예약 응대 한도는 기본 5명이며, 동관 객실이 완공될 때마다 한 명씩 늘어납니다.</p></div></article>
    <article><span>06</span><div><h3>응대 한도와 유효 배치는 별도</h3><p>사용 가능한 객실이 남아도 필수 숙박 조건의 조합에 따라 전원 배정에 실패할 수 있습니다.</p></div></article>
  </div></div>`;
}

function renderSpeciesRulesPage(controller) {
  return `<div class="handbook-page"><div class="handbook-page-heading"><p class="eyebrow">SPECIES ACCOMMODATION</p><h2>종족별 숙박 조건</h2><p>같은 종족 인원은 시너지를 만들고, 상극은 같은 층에서 만족도를 낮춥니다.</p></div><div class="manual-entry-grid">${controller.data.species.map((species) => {
    const locked = !controller.state.seenSpeciesIds.includes(species.id);
    const hiddenRows = Object.entries(species.hidden_preferences_by_rank ?? {}).filter(([, rules]) => rules.length > 0).map(([rankId, rules]) => {
      const known = rules.filter((rule, index) => controller.state.discoveredHiddenPreferenceIds.includes(rule.id ?? `${species.id}:${rankId}:hidden:${index}`));
      return `<p class="species-hidden-row ${known.length ? "known" : "unread"}"><b>${rankId} 숨은 선호</b>${known.length ? known.map((rule) => `${escapeHtml(rule.label)} ${signed(rule.points)}`).join(", ") : "첫 투숙 결산 후 열람"}</p>`;
    }).join("");
    return `<article class="manual-entry ${locked ? "locked" : ""}"><div class="manual-entry-title"><span>${locked ? "?" : escapeHtml(species.icon)}</span><div><small>${locked ? "미열람 규칙 · 첫 예약 시 공개" : "열람 완료 · 종족 규정"}</small><h3>${locked ? "아직 만나지 않은 종족" : escapeHtml(species.name)}</h3></div></div>${locked ? `<div class="locked-copy"><b>미열람 규칙</b><p>해당 종족의 첫 예약이 도착하면 공통 숙박 조건과 관계를 읽을 수 있습니다.</p></div>` : `<div class="manual-section required"><b>필수 숙박 조건</b>${renderRuleRows(species.hard_constraints, "필수")}</div><div class="manual-section preference"><b>공통 선호</b>${renderRuleRows(species.soft_preferences, "선호", true)}</div>${hiddenRows ? `<div class="species-hidden-list"><b>등급별 숨은 선호</b>${hiddenRows}</div>` : ""}<p class="manual-description">${(species.synergy_thresholds ?? []).map((item) => `${escapeHtml(item.label)}: ${item.count}명부터 1인당 ${signed(item.points_per_guest ?? item.points)}`).join(" · ")}</p>`}</article>`;
  }).join("")}</div></div>`;
}

function renderRankRulesPage(controller) {
  return `<div class="handbook-page"><div class="handbook-page-heading"><p class="eyebrow">GUEST CLASS</p><h2>N·R·SR·SSR 투숙 기대</h2><p>등급이 높을수록 선호·불호가 많고 한 번의 후기가 평판에 더 크게 반영됩니다.</p></div><div class="manual-entry-grid" data-video-target="rank-handbook">${controller.data.ranks.map((rank) => {
    const locked = !controller.state.seenRankIds.includes(rank.id);
    const unlockCopy = controller.isEndlessMode
      ? `미열람 규칙 · 누적 영업 ${rank.unlock_stage}회차 이후`
      : `미열람 규칙 · 초청 영업 ${rank.unlock_stage}회차 이후`;
    return `<article class="manual-entry rarity-${rank.id.toLowerCase()} ${locked ? "locked" : ""}" style="--rank-color:${escapeHtml(rank.color)}"><div class="manual-entry-title"><span>${locked ? "?" : escapeHtml(rank.symbol)}</span><div><small>${locked ? escapeHtml(unlockCopy) : `평판 영향 ${escapeHtml(rank.reputation_influence_label)}`}</small><h3>${locked ? "아직 만나지 않은 등급" : `${rank.id} · ${escapeHtml(rank.name)}`}</h3></div></div>${locked ? `<div class="locked-copy"><b>미열람 규칙</b><p>평판과 영업 회차 조건을 만족해 첫 예약이 도착하면 투숙 기대를 읽을 수 있습니다.</p></div>` : `<div class="manual-section required"><b>필수 숙박 조건</b>${renderRuleRows(rank.hard_constraints, "필수")}</div><div class="manual-section preference"><b>등급 공통 선호</b>${renderRuleRows(rank.soft_preferences, "선호", true)}</div><div class="manual-section dislike"><b>등급 공통 불호</b>${renderDislikeRows(rank.soft_dislikes)}</div><p class="manual-description">${escapeHtml(rank.description)}</p>`}</article>`;
  }).join("")}</div></div>`;
}

function renderDiscoveriesPage(controller) {
  const owned = controller.state.ownedUpgradeIds.map((id) => controller.data.indexes.upgrades[id]?.name ?? id);
  const hiddenFindings = controller.data.species.flatMap((species) => Object.entries(species.hidden_preferences_by_rank ?? {}).flatMap(([rankId, rules]) => rules.map((rule, index) => ({ species, rankId, rule, id: rule.id ?? `${species.id}:${rankId}:hidden:${index}` })))).filter((item) => controller.state.discoveredHiddenPreferenceIds.includes(item.id));
  const modeDescription = controller.isEndlessMode ? "현재 무한 영업 런과 공용 프로필에서 확인한 운영 기록입니다." : "개장 전 초청 영업에서 확인한 호텔의 운영 기록입니다.";
  const progressCard = controller.isEndlessMode
    ? `<article><span class="unlock-state open">시즌 ${controller.state.endlessSeasonIndex + 1}</span><h3>${controller.state.nightResults.length}회 생존 영업</h3><p>통과 시즌 ${controller.state.endlessAuditPassedCount} · 런 명성 ${controller.state.endlessRunFame}</p></article>`
    : `<article><span class="unlock-state open">개장 전 진행</span><h3>5회 초청 영업</h3><p>정식 개장 전 다섯 밤 동안 손님 응대와 호텔 시설을 점검합니다.</p></article>`;
  return `<div class="handbook-page"><div class="handbook-page-heading"><p class="eyebrow">DISCOVERY LEDGER</p><h2>발견과 해금 기록</h2><p>${escapeHtml(modeDescription)}</p></div><div class="unlock-rules">
    ${progressCard}
    <article><span class="unlock-state open">${controller.state.seenRankIds.length}/4</span><h3>발견한 등급</h3><p>${escapeHtml(controller.state.seenRankIds.join(" · "))}</p></article>
    <article><span class="unlock-state ${owned.length ? "open" : "locked"}">${owned.length ? `${owned.length}개 보유` : "미설치"}</span><h3>시설과 증축</h3><p>${escapeHtml(owned.join(", ") || "정산 뒤 공사업체의 증축·인테리어 제안에서 계약합니다.")}</p></article>
    <article><span class="unlock-state ${hiddenFindings.length ? "open" : "locked"}">${hiddenFindings.length ? `${hiddenFindings.length}개 열람` : "결산 전"}</span><h3>종족·등급 숨은 선호</h3><p>${hiddenFindings.length ? escapeHtml(hiddenFindings.map((item) => `${item.species.name} ${item.rankId}: ${item.rule.label}`).join(" · ")) : "R 이상 손님의 첫 투숙 결산에서 같은 종족·등급의 숨은 선호를 열람합니다."}</p></article>
  </div></div>`;
}

function renderDisplayRelicsPage(controller) {
  const relicProfile = controller.profile.display_relics ?? {};
  const seenIds = new Set([
    ...(relicProfile.seen_ids ?? []),
    ...(controller.state.pendingDisplayRelicOffer?.relicIds ?? []),
    ...controller.state.ownedDisplayRelicIds,
  ]);
  const acquiredIds = new Set([
    ...(relicProfile.acquired_ids ?? []),
    ...controller.state.ownedDisplayRelicIds,
  ]);
  const triggeredIds = new Set([
    ...(relicProfile.triggered_ids ?? []),
    ...Object.entries(controller.state.displayRelicTriggerCounts)
      .filter(([, count]) => count > 0)
      .map(([id]) => id),
  ]);
  const ownedIds = new Set(controller.state.ownedDisplayRelicIds);
  const relics = controller.data.display_relics ?? [];
  const runLabel = controller.isEndlessMode ? "현재 런" : "이번 캠페인";
  return `<div class="handbook-page"><div class="handbook-page-heading"><p class="eyebrow">LOBBY DISPLAY CATALOG</p><h2>전시품 도감</h2><p>한 번의 런 동안 로비에 누적되어 조건부 패시브 효과를 제공하는 수집품입니다.</p></div><div class="relic-catalog">${relics.map((relic) => {
    const seen = seenIds.has(relic.id);
    const acquired = acquiredIds.has(relic.id);
    const triggered = triggeredIds.has(relic.id);
    const owned = ownedIds.has(relic.id);
    const stateLabel = triggered ? "발동 확인" : acquired ? "획득 기록" : seen ? "열람" : "미발견";
    return `<article class="relic-catalog-card ${seen ? "seen" : "hidden"} ${owned ? "owned" : ""}"><span class="relic-icon">${seen ? escapeHtml(relic.icon) : "?"}</span><div><small>${stateLabel}${owned ? ` · ${escapeHtml(runLabel)} 보유` : ""}</small><h3>${seen ? escapeHtml(relic.name) : "이름을 알 수 없는 전시품"}</h3><p>${seen ? escapeHtml(relic.description) : "전시품 제안에서 처음 마주치면 기록됩니다."}</p>${seen ? `<b>${escapeHtml(relic.trigger_description)}</b>` : ""}</div></article>`;
  }).join("") || `<p class="maintenance-clear">이 모드에는 등록된 전시품이 없습니다.</p>`}</div></div>`;
}

function renderHandbook(controller) {
  if (!controller.state.handbookOpen) return "";
  const tab = controller.state.handbookTab;
  const page = tab === "species" ? renderSpeciesRulesPage(controller) : tab === "rank" ? renderRankRulesPage(controller) : tab === "relics" ? renderDisplayRelicsPage(controller) : tab === "discoveries" ? renderDiscoveriesPage(controller) : renderHotelRulesPage();
  return `<div class="handbook-overlay" role="dialog" aria-modal="true" aria-label="베스페라 호텔 운영 수첩"><section class="handbook-panel"><header class="handbook-heading"><div><p class="eyebrow">HOTEL VESPERA · OPERATIONS HANDBOOK</p><h1>운영 수첩</h1></div><button class="handbook-close" data-action="close-handbook" aria-label="운영 수첩 닫기">×</button></header><nav class="handbook-tabs" aria-label="수첩 분류">${handbookTabs(controller)}</nav><div class="handbook-body">${page}</div></section></div>`;
}

function renderEndlessAudit(controller) {
  const report = controller.state.endlessAuditReport;
  if (!report) return `<section class="screen-shell endless-audit-screen" data-screen="endless-audit"><h1>감사 보고서를 찾을 수 없습니다.</h1></section>`;
  const passed = report.passed === true;
  const evidenceRows = report.evidence.map((entry) => {
    const scenarioName = controller.data.indexes.scenarios?.[entry.scenarioId]?.name
      ?? controller.data.scenarios.find((scenario) => scenario.id === entry.scenarioId)?.name
      ?? entry.scenarioId;
    const adjustment = Number(entry.reputationDelta) - Number(entry.emergencyPenalty ?? 0);
    return `<article><span>${entry.operationNumber}</span><div><b>${escapeHtml(scenarioName)}</b><small>수용 ${entry.acceptedGuests} · 거절 ${entry.rejectedGuests} · 취소 ${entry.canceledGuests}${entry.emergency ? " · 긴급 처리" : ""}</small></div><strong>${signed(adjustment)}</strong></article>`;
  }).join("");
  return `<section class="screen-shell endless-audit-screen" data-screen="endless-audit" data-audit-score="${escapeHtml(report.score)}" data-audit-target="${escapeHtml(report.target)}" data-audit-passed="${passed}"><div class="result-hero ${passed ? "" : "failure"}"><p class="eyebrow">ENDLESS SEASON ${report.seasonNumber} · AUDIT COMPLETE · TIER ${report.riskTier}</p><span class="result-glyph">${passed ? "◇" : "◆"}</span><h1>${passed ? "감사 목표를 넘겨 영업을 이어갑니다." : "감사 목표에 미달해 호텔을 폐업합니다."}</h1><p>${passed ? "이번 시즌 기록이 확정되었고 다음 위험 단계와 전시품 제안을 준비합니다." : "사전에 공개된 조건에 따라 이 가능 세계의 생존 기록을 마감합니다."}</p></div><div class="audit-contract-grid"><article><small>감사 점수</small><strong>${signed(report.score)}</strong><span>평판 ${signed(report.reputationDelta)} · 긴급 감점 -${report.emergencyPenalty}</span></article><article><small>공개 목표</small><strong>${signed(report.target)}</strong><span>${report.operations}/${controller.endlessSeasonLength}회 판정</span></article><article><small>목표 대비</small><strong>${signed(report.margin)}</strong><span>${passed ? "통과" : "미달"}</span></article><article><small>런 명성</small><strong>${controller.state.endlessRunFame}</strong><span>통과 시즌 ${controller.state.endlessAuditPassedCount}</span></article></div><section class="audit-evidence"><div><p class="eyebrow">AUDIT EVIDENCE</p><h2>영업별 감사 근거</h2></div><div>${evidenceRows}</div></section><p class="provisional-note">${escapeHtml(controller.data.endless.audit.description)} 현재 수치와 공식은 개발용 PROVISIONAL 표본입니다.</p><div class="center-action">${passed ? `<button class="button primary large" data-action="advance-endless-season">다음 시즌 브리핑</button>` : `<button class="button primary large danger" data-action="close-endless-run">폐업 기록 확정</button>`}</div></section>`;
}

function renderEndlessFinal(controller) {
  const { state } = controller;
  const record = state.runRecord;
  const metrics = record?.metrics ?? {};
  const relicNames = (record?.owned_display_relic_ids ?? []).map(
    (id) => controller.data.indexes.displayRelics?.[id]?.name ?? id,
  );
  const storedAuditHistory = record?.endless_audit_history ?? [];
  const visibleAuditHistory = storedAuditHistory.slice(-5);
  const omittedAuditCount = Number(record?.endless_audit_history_omitted_count ?? 0)
    + Math.max(0, storedAuditHistory.length - visibleAuditHistory.length);
  return `<section class="screen-shell final-screen endless-final-screen" data-screen="endless-closure"><div class="result-hero failure"><p class="eyebrow">ENDLESS RUN CLOSED · ${escapeHtml(record?.ending_tier ?? "ENDLESS_CLOSED")}</p><span class="result-glyph">◆</span><h1>${escapeHtml(record?.title ?? "무한 영업 기록을 마감했습니다.")}</h1><p>${escapeHtml(record?.description ?? "사전 공개된 감사 목표에 따라 런을 종료했습니다.")}</p></div><article class="run-record-card"><div><small>RUN RECORD · ${escapeHtml(record?.ending_id ?? "UNRESOLVED")}</small><h2>생존 ${Number(metrics.endless_survived_nights ?? state.endlessCompletedOperations)}영업 · ${Number(metrics.endless_seasons_cleared ?? 0)}시즌 통과</h2></div><span class="status-chip warning">폐업</span><p>원인 <b>${escapeHtml(record?.endless_closure_reason ?? "UNKNOWN")}</b> · 기록 ID <b>${escapeHtml(record?.record_id ?? "-")}</b></p>${relicNames.length ? `<p><b>이번 런의 전시품</b> — ${escapeHtml(relicNames.join(" · "))}</p>` : ""}</article><div class="final-summary"><article><small>생존 영업</small><strong>${Number(metrics.endless_survived_nights ?? 0)}</strong></article><article><small>통과 시즌</small><strong>${Number(metrics.endless_seasons_cleared ?? 0)}</strong></article><article><small>마지막 감사</small><strong>${signed(Number(metrics.endless_last_audit_score ?? 0))} / ${signed(Number(metrics.endless_last_audit_target ?? 0))}</strong></article><article><small>런 명성·위험</small><strong>${Number(metrics.endless_run_fame ?? 0)} · T${Number(metrics.endless_risk_tier ?? 1)}</strong></article><article><small>실행 시드</small><strong>${state.runSeed}</strong></article></div><section class="audit-evidence compact"><div><p class="eyebrow">AUDIT HISTORY</p><h2>최근 확정 감사</h2>${omittedAuditCount ? `<small>이전 ${omittedAuditCount}개 요약 생략</small>` : ""}</div><div>${visibleAuditHistory.map((report) => `<article><span>${report.seasonNumber}</span><div><b>시즌 ${report.seasonNumber} · TIER ${report.riskTier}</b><small>${report.operations}회 영업 · 목표 ${signed(report.target)}</small></div><strong>${signed(report.score)} · ${report.passed ? "통과" : "미달"}</strong></article>`).join("")}</div></section><div class="center-action"><button class="button primary large" data-action="restart">다른 시드로 새 무한 영업</button></div></section>`;
}

function renderFinal(controller) {
  if (controller.isEndlessMode) return renderEndlessFinal(controller);
  const { nightResults, ownedUpgradeIds } = controller.state;
  const totalIncome = nightResults.reduce((sum, result) => sum + result.income, 0);
  const totalRep = nightResults.reduce((sum, result) => sum + result.reputationDelta, 0);
  const expandedRooms = ownedUpgradeIds.filter((id) => (controller.data.indexes.upgrades[id]?.room_unlocks ?? []).length).length;
  const lastResult = nightResults.at(-1);
  const record = controller.state.runRecord;
  const relicNames = (record?.owned_display_relic_ids ?? []).map((id) => controller.data.indexes.displayRelics?.[id]?.name ?? id);
  const isComplete = record?.outcome === "COMPLETE";
  const campaign = controller.isScenarioMode;
  const heroEyebrow = campaign ? "CAMPAIGN GREYBOX COMPLETE" : "PRE-OPENING INVITATIONAL COMPLETE";
  const heroTitle = campaign
    ? (record?.title ?? (isComplete ? "베스페라의 상속을 지켜냈습니다." : "상속 조건을 채우지 못했습니다."))
    : "개장 전 다섯 영업을 마쳤습니다.";
  const heroDescription = campaign
    ? (record?.description ?? "캠페인 종료 기록입니다.")
    : "수용과 배치, 공사 계약으로 달라진 호텔의 운영 기록입니다.";
  const restartLabel = campaign ? "새 캠페인 준비" : "다른 시드로 다시 시작";
  const incomeLabel = campaign ? "현재 골드" : "누적 수입";
  const incomeValue = campaign ? controller.state.gold : totalIncome;
  const reputationLabel = campaign ? "현재 평판" : "누적 평판";
  const reputationValue = campaign ? controller.state.hotelReputation : totalRep;
  const epilogues = campaign && record?.relationship_epilogues?.length
    ? `<section class="relationship-epilogues"><div><p class="eyebrow">RELATIONSHIP EPILOGUES</p><h2>인연을 맺은 손님들의 이후</h2></div><div>${record.relationship_epilogues.map((epilogue) => `<article class="${epilogue.selected ? "selected" : ""}"><small>${escapeHtml(epilogue.npc_stage)}${epilogue.selected ? " · 선택한 동반자" : ""}</small><h3>${escapeHtml(epilogue.label)}</h3><p>${escapeHtml(epilogue.description)}</p></article>`).join("")}</div></section>`
    : "";
  const managerOutcome = campaign && record?.manager_outcome
    ? `<p><b>지배인의 이후 · ${escapeHtml(record.manager_outcome.title)}</b> — ${escapeHtml(record.manager_outcome.description)}</p>`
    : "";
  return `<section class="screen-shell final-screen"><div class="result-hero ${campaign && !isComplete ? "failure" : ""}" data-video-target="showcase-final"><p class="eyebrow">${escapeHtml(heroEyebrow)}${record?.ending_tier ? ` · ${escapeHtml(record.ending_tier)}` : ""}</p><span class="result-glyph">◆</span><h1>${escapeHtml(heroTitle)}</h1><p>${escapeHtml(heroDescription)}</p></div><article class="run-record-card" data-video-target="run-record"><div><small>ENDING · ${escapeHtml(record?.ending_id ?? "UNRESOLVED")}</small><h2>${escapeHtml(record?.title ?? "종료 판정 기록 없음")}</h2></div><span class="status-chip ${isComplete ? "clear" : "warning"}">${isComplete ? (campaign ? "성공" : "완료") : campaign ? "실패" : "미완료"}</span><p>기록 ID <b>${escapeHtml(record?.record_id ?? "-")}</b> · 이 브라우저에 보존된 실행 기록 ${controller.state.recordArchiveCount}개</p>${managerOutcome}${relicNames.length ? `<p><b>이번 실행의 전시품</b> — ${escapeHtml(relicNames.join(" · "))}</p>` : ""}</article><div class="final-summary"><article><small>완료 영업</small><strong>${nightResults.length} / ${controller.totalNights}</strong></article><article><small>${incomeLabel}</small><strong>${incomeValue}G</strong></article><article><small>${reputationLabel}</small><strong>${signed(reputationValue)}</strong></article><article><small>시설·증축</small><strong>${ownedUpgradeIds.length}개 · 증축 ${expandedRooms}</strong></article><article><small>실행 시드</small><strong>${controller.state.runSeed}</strong></article></div>${epilogues}${lastResult && !campaign ? resultBreakdown(controller, lastResult) : ""}<div class="center-action"><button class="button primary large" data-action="restart">${escapeHtml(restartLabel)}</button></div></section>`;
}

export function renderApp(app, controller) {
  const { phase } = controller.state;
  let content = "";
  if (phase === PHASES.TITLE) content = renderTitle(controller);
  else if (phase === PHASES.NEW_GAME) content = renderNewGame(controller);
  else if (phase === PHASES.ENDLESS_BRIEFING) content = renderEndlessBriefing(controller);
  else if (phase === PHASES.ENDLESS_AUDIT) content = renderEndlessAudit(controller);
  else if ([PHASES.TUTORIAL, PHASES.PLACEMENT].includes(phase)) content = renderPlacement(controller);
  else if (phase === PHASES.STORY) content = renderStory(controller);
  else if (phase === PHASES.RELIC_OFFER) content = renderDisplayRelicOffer(controller);
  else if (phase === PHASES.DAY_OPENING) content = renderDayOpening(controller);
  else if (phase === PHASES.RESERVATION) content = renderReservation(controller);
  else if (phase === PHASES.RESULT) content = renderResult(controller);
  else if (phase === PHASES.RESULT_REVIEW) content = renderResultReview(controller);
  else if (phase === PHASES.UPGRADE) content = renderUpgrade(controller);
  else if (phase === PHASES.FINAL) content = renderFinal(controller);
  app.innerHTML = `<div class="app-frame">${renderHeader(controller)}<div class="content-frame">${content}</div>${renderHandbook(controller)}${renderReservationBoard(controller)}</div>`;
}

export function renderFatalError(app, error) {
  const help = globalThis.vesperaDesktop
    ? "데스크톱 저장 파일과 설치 자산을 확인한 뒤 다시 실행하세요."
    : "파일을 직접 열지 말고 <code>python -m http.server 8000</code>으로 실행하세요.";
  app.innerHTML = `<section class="loading-card error-card"><p class="eyebrow">LOAD ERROR</p><h1>영업 준비에 실패했습니다.</h1><p>${escapeHtml(error.message)}</p><p class="error-help">${help}</p></section>`;
}
