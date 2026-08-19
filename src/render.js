import { getGuestRules } from "./data.js";
import { attributeLabel } from "./rules.js";
import { PHASES } from "./state.js";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function phaseLabel(phase) {
  return {
    [PHASES.TITLE]: "영업 준비",
    [PHASES.NIGHT1_PLACEMENT]: "첫 번째 영업",
    [PHASES.NIGHT1_RESULT]: "첫 영업 정산",
    [PHASES.FACILITY_SHOP]: "호텔 정비",
    [PHASES.NIGHT2_RESERVATION]: "두 번째 예약",
    [PHASES.NIGHT2_PLACEMENT]: "두 번째 영업",
    [PHASES.FINAL_RESULT]: "최종 평가",
  }[phase];
}

function renderHeader(controller) {
  const { state } = controller;
  return `
    <header class="topbar">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true">◆</span>
        <div>
          <p class="eyebrow">HOTEL VESPERA</p>
          <strong>베스페라 호텔</strong>
        </div>
      </div>
      <div class="phase-pill">${escapeHtml(phaseLabel(state.phase))}</div>
      <div class="resources" aria-label="현재 자원">
        <button class="handbook-trigger" data-action="open-handbook" aria-label="운영 수첩 열기" title="운영 수첩"><span class="handbook-icon" aria-hidden="true">▤</span><span class="handbook-label">운영 수첩</span></button>
        <span><small>골드</small><b>${state.gold}G</b></span>
        <span><small>평판</small><b>${state.hotelReputation >= 0 ? "+" : ""}${state.hotelReputation}</b></span>
      </div>
    </header>
  `;
}

function renderTitle() {
  return `
    <section class="title-screen">
      <div class="title-copy invitation-letter">
        <span class="invitation-crest" aria-hidden="true">◆</span>
        <p class="invitation-hotel">HOTEL VESPERA</p>
        <p class="invitation-recipient">새 지배인 귀하</p>
        <h1>베스페라 호텔의<br /><em>첫 영업에 초대합니다.</em></h1>
        <p class="lede">손님마다 필요한 숙박 조건을 확인하고, 제한된 객실 안에서 가장 만족스러운 투숙을 준비해 주십시오.</p>
        <div class="invitation-signoff"><span>베스페라 호텔</span><b>총지배인실</b></div>
        <button class="button primary large" data-action="start">초대 수락</button>
      </div>
      <div class="title-rules invitation-enclosure" aria-label="투숙 명부 안내">
        <div class="enclosure-heading"><p class="eyebrow">ENCLOSED · GUEST POLICY</p><h2>투숙 명부를 읽는 법</h2></div>
        <article><span>01</span><div><strong>종족별 숙박 조건</strong><p>같은 종족의 모든 손님에게 적용되며, 반드시 맞아야 합니다.</p></div></article>
        <article><span>02</span><div><strong>등급별 응대 규정</strong><p>귀빈처럼 특정 등급에 공통으로 적용되는 조건입니다.</p></div></article>
        <article><span>03</span><div><strong>개인 선호</strong><p>손님 카드에 적혀 있으며, 만족할수록 팁과 평가가 올라갑니다.</p></div></article>
      </div>
    </section>
  `;
}

function rankLabel(rank) {
  return rank === "VIP" ? "귀빈" : "일반";
}

function speciesIcon(species) {
  return species === "VAMPIRE" ? "☾" : "△";
}

function renderRuleRows(rules, sourceLabel, withPoints = false) {
  return rules
    .map(
      (rule) => `<p><span class="rule-source">${escapeHtml(sourceLabel)}</span>${escapeHtml(rule.label)}${withPoints ? ` <b>+${rule.points}</b>` : ""}</p>`,
    )
    .join("");
}

function renderGuestChip(data, guestId, options = {}) {
  const guest = data.indexes.guests[guestId];
  const selected = options.selected ? " selected" : "";
  const invalid = options.invalid ? " invalid" : "";
  const score = options.score ?? null;
  return `
    <button class="guest-chip ${guest.species.toLowerCase()}${selected}${invalid}"
      data-guest-id="${guest.id}" data-drag-guest="${guest.id}" draggable="true"
      title="${escapeHtml(guest.name)} 선택">
      <span class="guest-symbol" aria-hidden="true">${speciesIcon(guest.species)}</span>
      <span class="guest-chip-copy"><b>${escapeHtml(guest.name)}</b><small>${rankLabel(guest.rank)}</small></span>
      ${score === null ? "" : `<span class="guest-score">+${score}</span>`}
    </button>
  `;
}

function renderRoom(data, room, board, occupantId, controller, evaluation) {
  const blocked = board.blockedRooms.has(room.id);
  const selected = occupantId && occupantId === controller.state.selectedGuestId;
  const invalidGuestIds = new Set(evaluation.violations.map((item) => item.guestId));
  const attrs = [...room.attributes];
  const attrText = attrs.map(attributeLabel).join(" · ");
  const secretEndpoint = board.facility?.room_bonuses?.some((bonus) => bonus.room_id === room.id);
  const classes = ["room-card"];
  if (blocked) classes.push("blocked");
  if (selected) classes.push("selected-room");
  if (secretEndpoint) classes.push("secret-endpoint");
  if (occupantId && invalidGuestIds.has(occupantId)) classes.push("has-violation");
  const roomAction = blocked ? "" : `data-room-id="${room.id}"`;

  return `
    <article class="${classes.join(" ")}" ${roomAction}>
      <div class="room-heading"><b>${room.id}</b><span>${escapeHtml(attrText)}</span></div>
      <div class="room-body">
        ${
          blocked
            ? `<div class="facility-in-room"><span>◈</span><b>${escapeHtml(board.facility.name)}</b></div>`
            : occupantId
              ? renderGuestChip(data, occupantId, {
                  selected,
                  invalid: invalidGuestIds.has(occupantId),
                  score: evaluation.guestScores[occupantId]?.total ?? 0,
                })
              : `<span class="empty-room">빈 객실</span>`
        }
      </div>
      ${secretEndpoint ? `<span class="room-bonus">비밀 통로 +3</span>` : ""}
    </article>
  `;
}

function renderGuestDetail(controller, evaluation) {
  const { data, state } = controller;
  const guestId = state.selectedGuestId;
  if (!guestId) {
    return `<div class="empty-detail"><span>◇</span><p>손님을 선택하면<br />필수 조건과 선호 사항이 표시됩니다.</p></div>`;
  }
  const guest = data.indexes.guests[guestId];
  const species = data.indexes.species[guest.species];
  const rules = getGuestRules(data, guestId);
  const score = evaluation.guestScores[guestId]?.total ?? 0;
  const placedRoom = state.placements[guestId];
  const guestViolations = evaluation.violations.filter((item) => item.guestId === guestId);

  return `
    <div class="detail-heading">
      <span class="detail-symbol">${speciesIcon(guest.species)}</span>
      <div><p>${escapeHtml(species.name)} · ${rankLabel(guest.rank)}</p><h2>${escapeHtml(guest.name)}</h2></div>
      <strong class="detail-score">+${score}</strong>
    </div>
    <div class="mini-stats">
      <span><small>숙박비</small><b>${guest.base_fee}G</b></span>
      <span><small>만족 평판</small><b>+${guest.satisfied_reputation}</b></span>
      <span><small>객실</small><b>${placedRoom ?? "대기"}</b></span>
    </div>
    <div class="inheritance-strip">
      <button data-action="open-handbook"><small>종족</small>${escapeHtml(species.name)} 규정 <span>↗</span></button>
      <button data-action="open-handbook"><small>등급</small>${rankLabel(guest.rank)} 규정 <span>↗</span></button>
    </div>
    <section class="rule-group">
      <h3><span class="rule-dot soft"></span> 개인 선호 <small>손님 카드 정보</small></h3>
      ${renderRuleRows(rules.personalPreferences, "개인", true)}
    </section>
    ${
      guestViolations.length
        ? `<section class="violation-box"><h3>객실을 배정할 수 없는 이유</h3>${guestViolations.map((item) => `<p>! ${escapeHtml(item.message)}</p>`).join("")}</section>`
        : `<p class="all-clear">✓ 수첩에 기록된 공통 규정에 맞는 객실입니다.</p>`
    }
    ${placedRoom ? `<button class="text-button" data-action="unplace" data-guest-id="${guestId}">객실에서 빼기</button>` : ""}
  `;
}

function renderPlacement(controller) {
  const { data, state } = controller;
  const evaluation = controller.currentEvaluation();
  const board = evaluation.board;
  const occupantByRoom = Object.fromEntries(
    Object.entries(state.placements).map(([guestId, roomId]) => [roomId, guestId]),
  );
  const waiting = state.acceptedGuestIds.filter((id) => !state.placements[id]);
  const scenario = controller.currentScenario;
  const facilityKey = state.selectedFacilityId ?? "NONE";
  const maxPreference = scenario.validated_max_preference[facilityKey];
  const floorRows = [3, 2, 1]
    .map((floor) => {
      const rooms = data.rooms.filter((room) => room.floor === floor);
      return `
        <div class="floor-row">
          <div class="floor-label"><b>F${floor}</b><span>${floor === 1 ? "로비층" : `${floor}층`}</span></div>
          ${rooms.map((sourceRoom) => renderRoom(data, board.rooms[sourceRoom.id], board, occupantByRoom[sourceRoom.id], controller, evaluation)).join("")}
        </div>`;
    })
    .join("");

  return `
    <section class="screen-shell placement-screen">
      <div class="screen-heading">
        <div><p class="eyebrow">ROOM ASSIGNMENT</p><h1>${state.phase === PHASES.NIGHT1_PLACEMENT ? "첫 손님을 맞이하세요" : "선택한 손님에게 객실을 주세요"}</h1></div>
        <p>${state.selectedFacilityId ? `${escapeHtml(data.indexes.facilities[state.selectedFacilityId].name)} 적용 중` : "시설 없음"}</p>
      </div>
      <div class="placement-layout">
        <section class="board-panel">
          <div class="hotel-board">${floorRows}</div>
          <div class="waiting-zone" data-waiting-zone>
            <div class="waiting-label"><b>대기 중</b><span>드래그하거나 손님 → 객실 순서로 클릭</span></div>
            <div class="waiting-guests">
              ${waiting.length ? waiting.map((id) => renderGuestChip(data, id, { selected: id === state.selectedGuestId, invalid: true, score: 0 })).join("") : `<span class="all-placed">모든 손님이 객실에 들어갔습니다.</span>`}
            </div>
          </div>
        </section>
        <aside class="detail-panel">${renderGuestDetail(controller, evaluation)}</aside>
      </div>
      <footer class="action-bar">
        <div class="score-cluster">
          <span class="status-chip ${evaluation.valid ? "clear" : "warning"}">${evaluation.valid ? "객실 배정 가능" : `배정 불가 ${evaluation.violations.length}건`}</span>
          <span><small>만족 점수</small><b>${evaluation.placementScore} / ${maxPreference}</b></span>
          <span><small>배치 인원</small><b>${Object.keys(state.placements).length} / ${state.acceptedGuestIds.length}</b></span>
        </div>
        <button class="button primary" data-action="finish-night" ${evaluation.valid ? "" : "disabled"}>밤 마감하기</button>
      </footer>
    </section>
  `;
}

function resultBreakdown(controller, result) {
  const acceptedNames = result.acceptedGuestIds.map((id) => controller.data.indexes.guests[id].name).join(", ");
  const rejectedNames = result.rejectedGuestIds.length
    ? result.rejectedGuestIds.map((id) => controller.data.indexes.guests[id].name).join(", ")
    : "없음";
  return `
    <div class="result-grid">
      <article><small>만족 점수</small><strong>${result.placementScore}</strong><span>최고 ${result.maxPreference}</span></article>
      <article><small>평판 변화</small><strong>${result.reputationDelta >= 0 ? "+" : ""}${result.reputationDelta}</strong><span>수용과 거절 합산</span></article>
      <article><small>기본 숙박비</small><strong>${result.baseFees}G</strong><span>수용 손님</span></article>
      <article><small>팁</small><strong>${result.placementScore}G</strong><span>선호 점수 환산</span></article>
      <article class="featured"><small>총수입</small><strong>${result.income}G</strong><span>이번 영업</span></article>
      <article class="featured"><small>영업 평가</small><strong>${result.evaluationScore}</strong><span>${result.grade}</span></article>
    </div>
    <div class="result-notes">
      <p><b>수용:</b> ${escapeHtml(acceptedNames)}</p>
      <p><b>거절:</b> ${escapeHtml(rejectedNames)}</p>
    </div>
  `;
}

function renderNight1Result(controller) {
  return `
    <section class="screen-shell result-screen">
      <div class="result-hero"><p class="eyebrow">NIGHT COMPLETE</p><span class="result-glyph">✦</span><h1>첫 영업을 마쳤습니다.</h1><p>벌어들인 돈으로 호텔의 규칙을 하나 바꿀 수 있습니다.</p></div>
      ${resultBreakdown(controller, controller.state.night1Result)}
      <div class="center-action"><button class="button primary large" data-action="continue-shop">시설 제안 보기</button></div>
    </section>
  `;
}

function renderShop(controller) {
  const { data, state } = controller;
  return `
    <section class="screen-shell shop-screen">
      <div class="screen-heading">
        <div><p class="eyebrow">HOTEL IMPROVEMENT</p><h1>다음 영업의 규칙을 고르세요.</h1></div>
        <p>보유 골드 <b>${state.gold}G</b></p>
      </div>
      <div class="facility-grid">
        ${data.facilities
          .map((facility) => {
            const affordable = state.gold >= facility.cost;
            const icon = facility.id === "SOUNDPROOFING" ? "▤" : facility.id === "LOUNGE" ? "◉" : "⇄";
            return `
              <article class="facility-card ${affordable ? "" : "locked"}">
                <span class="facility-icon">${icon}</span>
                <p class="eyebrow">${facility.id.replaceAll("_", " ")}</p>
                <h2>${escapeHtml(facility.name)}</h2>
                <p>${escapeHtml(facility.description)}</p>
                <div class="facility-price"><b>${facility.cost}G</b>${affordable ? "구매 가능" : `${facility.cost - state.gold}G 부족`}</div>
                <button class="button ${affordable ? "primary" : "muted"}" data-action="buy-facility" data-facility-id="${facility.id}" ${affordable ? "" : "disabled"}>선택하기</button>
              </article>`;
          })
          .join("")}
      </div>
      <p class="shop-note">시설은 이번 런 동안 유지되며 두 번째 영업의 이웃 관계와 점수를 바꿉니다.</p>
    </section>
  `;
}

function renderReservationCard(controller, guestId) {
  const { data, state } = controller;
  const guest = data.indexes.guests[guestId];
  const species = data.indexes.species[guest.species];
  const decision = state.applicantDecisions[guestId];
  const rules = getGuestRules(data, guestId);
  return `
    <article class="reservation-card ${decision ?? "pending"}">
      <div class="reservation-top">
        <span class="reservation-symbol">${speciesIcon(guest.species)}</span>
        <div><p>${escapeHtml(species.name)} · ${rankLabel(guest.rank)}</p><h2>${escapeHtml(guest.name)}</h2></div>
        <span class="rank-crown">${guest.rank === "VIP" ? "♛" : "•"}</span>
      </div>
      <div class="reservation-stats">
        <span><small>숙박비</small><b>${guest.base_fee}G</b></span>
        <span><small>만족</small><b>+${guest.satisfied_reputation}</b></span>
        <span><small>거절</small><b>${guest.reject_reputation}</b></span>
      </div>
      <div class="reservation-rules">
        <p><b>개인 선호 ${rules.personalPreferences.length}</b> · ${rules.personalPreferences.map((rule) => `${escapeHtml(rule.label)} +${rule.points}`).join(", ")}</p>
      </div>
      <div class="decision-buttons">
        <button class="button small accept" data-action="accept" data-guest-id="${guestId}">수용</button>
        <button class="button small reject" data-action="reject" data-guest-id="${guestId}">거절</button>
      </div>
      ${decision ? `<div class="decision-stamp">${decision === "accept" ? "수용 예정" : "거절 예정"}</div>` : ""}
    </article>
  `;
}

function renderReservation(controller) {
  const { data, state } = controller;
  const summary = controller.reservationSummary();
  const rejectionDelta = summary.rejected.reduce(
    (sum, id) => sum + data.indexes.guests[id].reject_reputation,
    0,
  );
  const fixedNames = controller.night2.fixed_guests.map((id) => data.indexes.guests[id].name).join(", ");
  const ready = !summary.pending.length && !summary.overCapacity;
  return `
    <section class="screen-shell reservation-screen">
      <div class="screen-heading">
        <div><p class="eyebrow">GUEST APPLICATIONS</p><h1>누구를 맞이하시겠습니까?</h1></div>
        <p>고정 예약 <b>${escapeHtml(fixedNames)}</b></p>
      </div>
      <div class="reservation-grid">
        ${controller.night2.applicants.map((id) => renderReservationCard(controller, id)).join("")}
      </div>
      <footer class="action-bar">
        <div class="score-cluster">
          <span class="status-chip ${summary.overCapacity ? "warning" : "clear"}">응대 ${summary.accepted.length} / ${controller.night2.capacity}</span>
          <span><small>미결정</small><b>${summary.pending.length}</b></span>
          <span><small>거절 평판</small><b>${rejectionDelta}</b></span>
        </div>
        <button class="button primary" data-action="confirm-reservation" ${ready ? "" : "disabled"}>명단 확정</button>
      </footer>
      ${summary.overCapacity ? `<p class="inline-warning">응대 한도를 넘었습니다. 수용 손님을 한 명 줄이세요.</p>` : ""}
    </section>
  `;
}

function handbookTabs(activeTab) {
  const tabs = [
    ["hotel", "호텔 규정"],
    ["species", "종족"],
    ["rank", "등급"],
    ["discoveries", "발견·해금"],
  ];
  return tabs
    .map(
      ([id, label]) => `<button class="handbook-tab ${activeTab === id ? "active" : ""}" data-action="handbook-tab" data-tab="${id}">${label}</button>`,
    )
    .join("");
}

function renderHotelRulesPage() {
  return `
    <div class="handbook-page">
      <div class="handbook-page-heading"><p class="eyebrow">FRONT DESK STANDARD</p><h2>호텔 공통 규정</h2><p>모든 영업과 모든 손님에게 적용되는 가장 기본적인 규칙입니다.</p></div>
      <div class="manual-rule-grid">
        <article><span>01</span><div><h3>수용한 손님은 모두 배정</h3><p>명단을 확정한 뒤에는 모든 손님에게 객실이 있어야 밤을 마감할 수 있습니다.</p></div></article>
        <article><span>02</span><div><h3>객실 하나에 손님 한 명</h3><p>같은 객실을 두 손님이 함께 사용할 수 없습니다.</p></div></article>
        <article><span>03</span><div><h3>공통 조건은 반드시 적용</h3><p>손님 카드의 종족과 등급을 수첩에서 찾아 두 규정을 모두 적용합니다.</p></div></article>
        <article><span>04</span><div><h3>개인 선호는 추가 점수</h3><p>충족하지 않아도 배정할 수 있지만, 팁과 영업 평가를 얻지 못합니다.</p></div></article>
      </div>
    </div>`;
}

function renderSpeciesRulesPage(controller) {
  return `
    <div class="handbook-page">
      <div class="handbook-page-heading"><p class="eyebrow">SPECIES ACCOMMODATION</p><h2>종족별 숙박 조건</h2><p>손님 카드의 종족 표식을 확인한 뒤 아래 공통 규정을 적용합니다.</p></div>
      <div class="manual-entry-grid">
        ${controller.data.species
          .map(
            (species) => `<article class="manual-entry">
              <div class="manual-entry-title"><span>${speciesIcon(species.id)}</span><div><small>확인됨 · 종족 규정</small><h3>${escapeHtml(species.name)}</h3></div></div>
              <div class="manual-section required"><b>필수 숙박 조건</b>${species.hard_constraints.map((rule) => `<p>${escapeHtml(rule.label)}</p>`).join("")}</div>
              <div class="manual-section preference"><b>공통 선호</b>${species.soft_preferences.map((rule) => `<p>${escapeHtml(rule.label)} <strong>+${rule.points}</strong></p>`).join("")}</div>
            </article>`,
          )
          .join("")}
      </div>
    </div>`;
}

function renderRankRulesPage(controller) {
  const vipUnlocked = Boolean(controller.state.selectedFacilityId);
  return `
    <div class="handbook-page">
      <div class="handbook-page-heading"><p class="eyebrow">SERVICE CLASS</p><h2>등급별 응대 규정</h2><p>등급 규정은 같은 등급의 모든 손님에게 공통으로 적용됩니다.</p></div>
      <div class="manual-entry-grid">
        ${controller.data.ranks
          .map((rank) => {
            const locked = rank.id === "VIP" && !vipUnlocked;
            return `<article class="manual-entry ${locked ? "locked" : ""}">
              <div class="manual-entry-title"><span>${locked ? "?" : rank.id === "VIP" ? "♛" : "•"}</span><div><small>${locked ? "미해금 · 귀빈 첫 등장 시" : "확인됨 · 등급 규정"}</small><h3>${locked ? "아직 만나지 않은 등급" : escapeHtml(rank.name)}</h3></div></div>
              ${locked ? `<div class="locked-copy"><b>기록 없음</b><p>해당 등급의 예약 신청을 받으면 응대 규정이 수첩에 추가됩니다.</p></div>` : `<div class="manual-section required"><b>필수 응대 조건</b>${rank.hard_constraints.length ? rank.hard_constraints.map((rule) => `<p>${escapeHtml(rule.label)}</p>`).join("") : `<p>추가 조건 없음</p>`}</div><p class="manual-description">${escapeHtml(rank.description)}</p>`}
            </article>`;
          })
          .join("")}
      </div>
    </div>`;
}

function renderDiscoveriesPage(controller) {
  const shopSeen = Boolean(controller.state.night1Result);
  const selected = controller.state.selectedFacilityId;
  return `
    <div class="handbook-page">
      <div class="handbook-page-heading"><p class="eyebrow">DISCOVERY LEDGER</p><h2>발견과 해금 기록</h2><p>새 규칙은 처음부터 모두 주어지지 않으며, 만나는 순간 수첩에 기록됩니다.</p></div>
      <div class="unlock-rules">
        <article><span class="unlock-state open">기본 지급</span><h3>호텔 공통 규정</h3><p>첫 초대장과 함께 지급됩니다.</p></article>
        <article><span class="unlock-state open">확인됨</span><h3>종족별 숙박 조건</h3><p>해당 종족의 첫 손님을 만나면 기록됩니다.</p></article>
        <article><span class="unlock-state ${selected ? "open" : "locked"}">${selected ? "확인됨" : "미해금"}</span><h3>귀빈 응대 규정</h3><p>귀빈 등급의 예약 신청을 받으면 기록됩니다.</p></article>
        <article><span class="unlock-state ${shopSeen ? "open" : "locked"}">${shopSeen ? "제안 확인" : "미해금"}</span><h3>시설 기록</h3><p>${selected ? `${escapeHtml(controller.data.indexes.facilities[selected].name)} 설치 기록이 추가되었습니다.` : "첫 영업 정산 후 시설 제안을 확인하면 추가됩니다."}</p></article>
        <article><span class="unlock-state locked">프로토타입 미포함</span><h3>숨은 성향</h3><p>정식 버전에서는 시험 숙박과 반응 관찰로 단서를 확정할 때 기록됩니다.</p></article>
      </div>
    </div>`;
}

function renderHandbook(controller) {
  if (!controller.state.handbookOpen) return "";
  const tab = controller.state.handbookTab;
  const page = tab === "species"
    ? renderSpeciesRulesPage(controller)
    : tab === "rank"
      ? renderRankRulesPage(controller)
      : tab === "discoveries"
        ? renderDiscoveriesPage(controller)
        : renderHotelRulesPage();
  return `
    <div class="handbook-overlay" role="dialog" aria-modal="true" aria-label="베스페라 호텔 운영 수첩">
      <section class="handbook-panel">
        <header class="handbook-heading">
          <div><p class="eyebrow">HOTEL VESPERA · OPERATIONS HANDBOOK</p><h1>운영 수첩</h1></div>
          <button class="handbook-close" data-action="close-handbook" aria-label="운영 수첩 닫기">×</button>
        </header>
        <nav class="handbook-tabs" aria-label="수첩 분류">${handbookTabs(tab)}</nav>
        <div class="handbook-body">${page}</div>
      </section>
    </div>`;
}

function renderFinal(controller) {
  const { night1Result, night2Result, selectedFacilityId } = controller.state;
  const facility = controller.data.indexes.facilities[selectedFacilityId];
  const totalIncome = night1Result.income + night2Result.income;
  const totalRep = night1Result.reputationDelta + night2Result.reputationDelta;
  return `
    <section class="screen-shell final-screen">
      <div class="result-hero"><p class="eyebrow">PROTOTYPE COMPLETE</p><span class="result-glyph">◆</span><h1>두 번의 영업을 마쳤습니다.</h1><p>${escapeHtml(facility.name)}이 두 번째 밤의 해법을 바꿨습니다.</p></div>
      <div class="final-summary">
        <article><small>선택 시설</small><strong>${escapeHtml(facility.name)}</strong></article>
        <article><small>총수입</small><strong>${totalIncome}G</strong></article>
        <article><small>총 평판</small><strong>${totalRep >= 0 ? "+" : ""}${totalRep}</strong></article>
        <article><small>마지막 평가</small><strong>${night2Result.evaluationScore} / ${night2Result.maxEvaluation}</strong></article>
      </div>
      ${resultBreakdown(controller, night2Result)}
      <div class="center-action split-actions">
        <button class="button secondary large" data-action="retry-night2">두 번째 영업 재도전</button>
        <button class="button primary large" data-action="restart">처음부터 다시</button>
      </div>
    </section>
  `;
}

export function renderApp(app, controller) {
  const { phase } = controller.state;
  let content = "";
  if (phase === PHASES.TITLE) content = renderTitle();
  else if ([PHASES.NIGHT1_PLACEMENT, PHASES.NIGHT2_PLACEMENT].includes(phase)) content = renderPlacement(controller);
  else if (phase === PHASES.NIGHT1_RESULT) content = renderNight1Result(controller);
  else if (phase === PHASES.FACILITY_SHOP) content = renderShop(controller);
  else if (phase === PHASES.NIGHT2_RESERVATION) content = renderReservation(controller);
  else if (phase === PHASES.FINAL_RESULT) content = renderFinal(controller);
  app.innerHTML = `<div class="app-frame">${renderHeader(controller)}<div class="content-frame">${content}</div>${renderHandbook(controller)}</div>`;
}

export function renderFatalError(app, error) {
  app.innerHTML = `
    <section class="loading-card error-card">
      <p class="eyebrow">LOAD ERROR</p>
      <h1>영업 준비에 실패했습니다.</h1>
      <p>${escapeHtml(error.message)}</p>
      <p class="error-help">파일을 직접 열지 말고 <code>python -m http.server 8000</code>으로 실행하세요.</p>
    </section>`;
}
