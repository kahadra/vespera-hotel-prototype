import { validateEndlessData } from "./endless.js";
import {
  validateCampaignCalendar,
  validateCampaignCalendarPrefix,
} from "./campaign-calendar.js";

const DATA_URL = "./data/prototype_v1.json";

function commonDisplayRelics() {
  return [
    {
      id: "DISPLAY_RELIC_DAWN_BELL",
      type: "DISPLAY_RELIC",
      pool_type: "COMMON",
      name: "새벽의 종",
      icon: "♢",
      description: "하루의 첫 객실 재배치에 드는 시간을 2초 줄입니다.",
      trigger_description: "영업 중 처음으로 배정을 바꿀 때 발동",
      effect_id: "FIRST_RELOCATION_TIME_REDUCTION",
      effect_params: { value: 2000 },
      stack_group: "RELOCATION_TIME",
      offer_weight: 1,
      status: "PROVISIONAL",
    },
    {
      id: "DISPLAY_RELIC_SILVER_MAINTENANCE_KIT",
      type: "DISPLAY_RELIC",
      pool_type: "COMMON",
      name: "은빛 정비함",
      icon: "▣",
      description: "막간의 객실 정비 비용을 3G 줄입니다.",
      trigger_description: "손상된 빈 객실을 실제로 정비할 때 발동",
      effect_id: "ROOM_SERVICE_COST_REDUCTION",
      effect_params: { value: 3 },
      stack_group: "ROOM_SERVICE_COST",
      offer_weight: 1,
      status: "PROVISIONAL",
    },
    {
      id: "DISPLAY_RELIC_UNBLEMISHED_LEDGER",
      type: "DISPLAY_RELIC",
      pool_type: "COMMON",
      name: "무흠 장부",
      icon: "▤",
      description: "수용한 손님을 한 명도 취소하지 않고 영업을 마치면 3G를 더 받습니다.",
      trigger_description: "손님을 수용한 유효 영업에서 취소가 없을 때 발동",
      effect_id: "NO_CANCELLATION_GOLD_BONUS",
      effect_params: { value: 3 },
      stack_group: "RESULT_GOLD",
      offer_weight: 1,
      status: "PROVISIONAL",
    },
  ];
}

function formalCampaignCalendar(includeTrueExtension = false) {
  const seasons = [
    { id: "SPRING", label: "봄", weight: 1, effects: {} },
    { id: "SUMMER", label: "여름", weight: 1, effects: {} },
    { id: "AUTUMN", label: "가을", weight: 1, effects: {} },
    { id: "WINTER", label: "겨울", weight: 1, effects: {} },
  ];
  if (includeTrueExtension) {
    seasons.push({
      id: "TRUE_EXTENSION_SEASON",
      label: "추가 계절",
      weight: 1,
      effects: {},
    });
  }
  return {
    calendar_id: includeTrueExtension ? "CAMPAIGN_TRUE_EXTENSION" : "CAMPAIGN_BASE_YEAR",
    calendar_version: 1,
    total_stages: includeTrueExtension ? 70 : 56,
    week_length: 7,
    weekend_days: [6, 7],
    weekend_effects: {
      applicant_bonus: 1,
      rank_multipliers: {},
      species_multipliers: {},
    },
    seasons,
    holidays: [],
    events: [],
  };
}

export async function loadGameData(options = {}) {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`데이터를 불러오지 못했습니다: ${DATA_URL} (${response.status})`);
  }
  const data = await response.json();
  const indexes = createIndexes(data);
  validateData(data, indexes);
  const loaded = { ...data, indexes };
  const mode = String(options.mode ?? "").toUpperCase();
  if (mode === "CAMPAIGN") return createCampaignGreyboxData(loaded);
  if (mode === "ENDLESS") return createEndlessGreyboxData(loaded);
  return loaded;
}

export function createCampaignGreyboxData(source) {
  const { indexes: _sourceIndexes, ...serializable } = source;
  const data = JSON.parse(JSON.stringify(serializable));
  const formalSpecies = [
    {
      id: "HUMAN",
      metric_id: "human",
      label: "인족",
      relationship_role_id: "RELATIONSHIP_HUMAN",
      ending_title: "인간의 등불을 지키는 베스페라",
      ending_description: "인간 사회와 이종족 사이의 안전한 관문으로 베스페라를 남겼습니다.",
      manager_outcome: {
        id: "REMAIN_HUMAN_STEWARD",
        title: "인간 지배인으로 남는다",
        description: "태어난 종족을 바꾸지 않고 두 세계를 잇는 인간 지배인으로 살아갈 수 있습니다.",
      },
    },
    {
      id: "VAMPIRE",
      metric_id: "vampire",
      label: "뱀파이어",
      relationship_role_id: "RELATIONSHIP_VAMPIRE",
      ending_title: "피와 밤의 베스페라",
      ending_description: "뱀파이어와의 가장 강한 협약 아래 밤의 손님을 위한 베스페라를 완성했습니다.",
      manager_outcome: {
        id: "OPTIONAL_VAMPIRE_TRANSFORMATION",
        title: "밤의 혈족이 될 선택",
        description: "인간으로 남거나, 합의된 전환을 받아 뱀파이어의 긴 밤을 함께 살아갈 수 있습니다.",
      },
    },
    {
      id: "WEREWOLF",
      metric_id: "werewolf",
      label: "늑대인간",
      relationship_role_id: "RELATIONSHIP_WEREWOLF",
      ending_title: "달과 무리의 베스페라",
      ending_description: "늑대인간 무리와의 가장 강한 협약 아래 달밤의 안식처를 완성했습니다.",
      manager_outcome: {
        id: "OPTIONAL_WEREWOLF_TRANSFORMATION",
        title: "무리의 일원이 될 선택",
        description: "인간으로 남거나, 합의된 물림과 의식을 거쳐 늑대인간 무리의 일원이 될 수 있습니다.",
      },
    },
    {
      id: "WITCH",
      metric_id: "witch",
      label: "마녀",
      relationship_role_id: "RELATIONSHIP_WITCH",
      ending_title: "약초와 마법의 베스페라",
      ending_description: "마녀회와의 가장 강한 협약 아래 약학과 마법이 보호받는 피난처를 완성했습니다.",
      manager_outcome: {
        id: "OPTIONAL_WITCH_AWAKENING",
        title: "인간으로 남거나 마녀로 각성할 선택",
        description: "인간인 채 약초학과 마법을 전수받거나 마녀로 각성할 수 있습니다. 여성 지배인은 그대로 마녀가 되고, 남성 지배인은 각성 의식에서 여성의 몸으로 다시 빚어집니다.",
      },
    },
    {
      id: "DREAM_DEMON",
      metric_id: "dream_demon",
      label: "몽마",
      relationship_role_id: "RELATIONSHIP_DREAM_DEMON",
      minimum_guest_rank_id: "SR",
      other_species_occupancy_preferences: {
        SR: 2,
        SSR: 3,
        UR: 4,
        provisional: true,
      },
      requires_cross_species_network: true,
      ending_title: "꿈이 순환하는 베스페라",
      ending_description: "몽마와 타종족이 합의한 꿈·정기 교류망을 바탕으로 공존하는 밤의 안식처를 완성했습니다.",
      manager_outcome: {
        id: "OPTIONAL_DREAM_DEMON_REINCARNATION",
        title: "꿈을 건너 다시 태어날 선택",
        description: "인간의 삶을 유지하거나, 특별한 의식과 동의를 거쳐 먼 훗날 몽마로 전생할 수 있습니다.",
      },
    },
  ];
  const relationshipRoles = formalSpecies.map((species) => ({
    id: species.relationship_role_id,
    species_id: species.id,
    label: `${species.label} 관계 인물`,
    starting_role: "GUEST",
  }));
  const progress = (npcStage, endingReady = false, options = {}) => ({
    epilogue_unlocked: true,
    npc_stage: npcStage,
    event_count: options.event_count ?? 1,
    ending_ready: endingReady,
    hotel_dependency: options.hotel_dependency ?? "INDEPENDENT",
  });
  const allRoleProgress = Object.fromEntries(relationshipRoles.map((role) => [
    role.id,
    progress("COLLABORATOR", true, { event_count: 5 }),
  ]));
  data.display_relics = commonDisplayRelics();
  data.prototype_mode = {
    ...data.prototype_mode,
    type: "CAMPAIGN",
    total_nights: data.scenarios.length,
    accelerated: false,
    notice: "정식 캠페인의 저장·장면·성공·실패 연결을 검증하는 회색 상자 개발 모드입니다.",
  };
  data.campaign = {
    id: "CAMPAIGN_GREYBOX_01",
    status: "GREYBOX",
    objective: {
      title: "상속 유지 조건",
      description: "다섯 번의 영업이 끝날 때 80G 이상과 호텔 평판 0 이상을 유지합니다.",
      target_gold: 80,
      minimum_reputation: 0,
      provisional: true,
    },
    new_game_defaults: {
      player_gender_id: "MALE",
      relationship_gender_preset: "ALL_FEMALE",
      secretary_presentation_id: "FEMALE",
      greybox_ending_route_id: "NORMAL",
    },
    formal_species: formalSpecies,
    formal_rank_ids: ["N", "R", "SR", "SSR", "UR"],
    relationship_roles: relationshipRoles,
    relationship_role_ids: relationshipRoles.map((role) => role.id),
    ending_thresholds: {
      species_affinity: 5,
      truth_evidence: 3,
      dream_demon_other_species_affinity: 3,
      dream_demon_other_species_count: 2,
      provisional: true,
    },
    calendar: {
      status: "PROVISIONAL",
      base_year: formalCampaignCalendar(false),
      true_extension: formalCampaignCalendar(true),
      notes: [
        "1스테이지는 하루이자 영업 1회입니다.",
        "주말 신청 손님 +1은 경제·수요 시뮬레이션 전의 개발 기준값입니다.",
        "공휴일·특별 행사일 데이터는 일정 생성기 연결 뒤 추가합니다.",
      ],
    },
    ending_preview_routes: [
      {
        id: "BAD",
        label: "배드",
        description: "챕터 핵심 허들을 넘지 못한 상태를 검증합니다.",
        chapter_hurdle_failures: 1,
        relationship_progress_by_role: {
          RELATIONSHIP_HUMAN: progress("REGULAR_GUEST"),
          RELATIONSHIP_VAMPIRE: progress("LIAISON", false, { event_count: 2 }),
        },
      },
      {
        id: "NORMAL",
        label: "노말",
        description: "호텔은 지키지만 특정 종족·진상 분기를 열지 않습니다.",
        relationship_progress_by_role: {
          RELATIONSHIP_HUMAN: progress("REGULAR_GUEST"),
          RELATIONSHIP_VAMPIRE: progress("REGULAR_GUEST"),
        },
      },
      {
        id: "SPECIES_VAMPIRE",
        label: "종족",
        description: "뱀파이어 우호도와 전용 호텔 협약을 검증합니다.",
        species_affinity_by_id: { VAMPIRE: 6 },
        species_ending_trigger_ids: ["VAMPIRE"],
        species_ending_commitment_id: "VAMPIRE",
        relationship_progress_by_role: {
          RELATIONSHIP_VAMPIRE: progress("LIAISON", false, { event_count: 3 }),
        },
      },
      {
        id: "SPECIES_HEROINE_VAMPIRE",
        label: "종족 히로인",
        description: "뱀파이어 종족 엔딩과 관계 인물의 모든 필수 사건 완료를 검증합니다.",
        species_affinity_by_id: { VAMPIRE: 6 },
        species_ending_trigger_ids: ["VAMPIRE"],
        species_ending_commitment_id: "VAMPIRE",
        selected_ending_relationship_role_id: "RELATIONSHIP_VAMPIRE",
        relationship_progress_by_role: {
          RELATIONSHIP_VAMPIRE: progress("COLLABORATOR", true, { event_count: 5 }),
        },
      },
      {
        id: "TRUE_VAMPIRE",
        label: "트루",
        description: "악신의 단서와 전 종족 평화 조건, 선택 가능한 관계 인물을 검증합니다.",
        truth_evidence_count: 3,
        peace_alliance_complete: true,
        selected_ending_relationship_role_id: "RELATIONSHIP_VAMPIRE",
        relationship_progress_by_role: {
          RELATIONSHIP_HUMAN: progress("COLLABORATOR", true, { event_count: 5 }),
          RELATIONSHIP_VAMPIRE: progress("COLLABORATOR", true, { event_count: 5 }),
          RELATIONSHIP_WEREWOLF: progress("LIAISON", false, { event_count: 3 }),
          RELATIONSHIP_WITCH: progress("LIAISON", false, { event_count: 3 }),
          RELATIONSHIP_DREAM_DEMON: progress("LIAISON", false, { event_count: 3 }),
        },
      },
      {
        id: "TRUE_HAREM",
        label: "트루 하렘",
        description: "트루 분기의 추가 기회로 모든 관계 인물 엔딩 조건을 채운 상태를 검증합니다.",
        truth_evidence_count: 3,
        peace_alliance_complete: true,
        relationship_progress_by_role: allRoleProgress,
      },
    ],
    story_nodes: [
      {
        id: "CAMPAIGN_PROLOGUE",
        eyebrow: "PROLOGUE · THE INHERITED HOTEL",
        title: "베스페라의 새 인간 지배인",
        paragraphs: [
          "선대의 유언은 호텔을 넘기는 대신 다섯 번의 시험 영업 기록을 요구했습니다.",
          "인간 지배인의 지시를 보좌하는 비서 오토마타가 첫 장부를 펼칩니다. 지금은 호텔을 지킬 수 있는지 증명해야 합니다.",
        ],
        continuation: { action: "BEGIN_DAY", night_index: 0 },
      },
      {
        id: "CAMPAIGN_CHAPTER_ONE_REVIEW",
        eyebrow: "CHAPTER 1 · OPERATIONS REVIEW",
        title: "첫 장부의 검토",
        paragraphs: [
          "두 번의 영업 기록이 선대의 봉인 장부에 추가되었습니다.",
          "호텔은 아직 불안정하지만 서로 다른 종족이 같은 규정 아래 머물 수 있다는 첫 증거가 남았습니다.",
        ],
        continuation: { action: "OPEN_UPGRADE" },
      },
      {
        id: "CAMPAIGN_CHAPTER_TWO_REVIEW",
        eyebrow: "CHAPTER 2 · TERMS OF SUCCESSION",
        title: "상속 조건의 마지막 조항",
        paragraphs: [
          "남은 영업은 한 번입니다. 장부의 자금과 평판이 상속 유지 조건을 결정합니다.",
          "마지막 투숙을 받기 전에 어떤 공사에 투자할지 선택해야 합니다.",
        ],
        continuation: { action: "OPEN_UPGRADE" },
      },
    ],
    story_after_nights: {
      "2": "CAMPAIGN_CHAPTER_ONE_REVIEW",
      "4": "CAMPAIGN_CHAPTER_TWO_REVIEW",
    },
    display_relic_offer_schedule: [
      {
        id: "CAMPAIGN_START_COMMON_RELIC",
        after_story_id: "CAMPAIGN_PROLOGUE",
        pool_ids: ["COMMON"],
        offer_size: 3,
      },
    ],
  };
  const calendarValidationOptions = {
    rankIds: data.campaign.formal_rank_ids,
    speciesIds: formalSpecies.map((species) => species.id),
  };
  validateCampaignCalendar(data.campaign.calendar.base_year, calendarValidationOptions);
  validateCampaignCalendar(data.campaign.calendar.true_extension, calendarValidationOptions);
  validateCampaignCalendarPrefix(
    data.campaign.calendar.base_year,
    data.campaign.calendar.true_extension,
    calendarValidationOptions,
  );
  data.run_completion = {
    record_namespace: "vespera.campaign.greybox.v2",
    ending_rules: [
      {
        id: "BAD_CHAPTER_HURDLE",
        ending_tier: "BAD",
        priority: 1000,
        outcome: "FAILURE",
        title: "상속 심사에서 퇴장하다",
        description: "챕터의 핵심 운영 허들을 회복하지 못해 베스페라의 상속권을 잃었습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "chapter_hurdle_failures", operator: "GTE", value: 1 },
        ],
      },
      {
        id: "TRUE_HAREM",
        ending_tier: "TRUE_HAREM",
        priority: 900,
        outcome: "COMPLETE",
        title: "모든 밤이 머무는 베스페라",
        description: "악신의 개입을 끝내고 모든 종족과 관계 인물의 미래를 하나의 호텔에 연결했습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "final_gold", operator: "GTE", value: 80 },
          { metric: "final_reputation", operator: "GTE", value: 0 },
          { metric: "truth_evidence", operator: "GTE", value: 3 },
          { metric: "peace_alliance", operator: "EQ", value: 1 },
          { metric: "all_relationship_endings_ready", operator: "EQ", value: 1 },
        ],
      },
      {
        id: "TRUE_PEACE",
        ending_tier: "TRUE",
        priority: 800,
        outcome: "COMPLETE",
        title: "다섯 종족의 밤을 잇다",
        description: "악신의 존재를 밝혀내고 베스페라를 모든 종족이 안심하고 찾는 평화의 협약지로 남겼습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "final_gold", operator: "GTE", value: 80 },
          { metric: "final_reputation", operator: "GTE", value: 0 },
          { metric: "truth_evidence", operator: "GTE", value: 3 },
          { metric: "peace_alliance", operator: "EQ", value: 1 },
        ],
      },
      ...formalSpecies.map((species) => ({
        id: `SPECIES_HEROINE_${species.id}`,
        ending_tier: "SPECIES_HEROINE",
        species_id: species.id,
        relationship_role_id: species.relationship_role_id,
        priority: 700,
        outcome: "COMPLETE",
        title: `${species.label} 관계 인물과 함께 지키는 베스페라`,
        description: `${species.ending_description} 관계 인물의 모든 필수 사건도 함께 완성했습니다.`,
        manager_outcome: species.manager_outcome,
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "final_gold", operator: "GTE", value: 80 },
          { metric: "final_reputation", operator: "GTE", value: 0 },
          { metric: `dominant_species_${species.metric_id}`, operator: "EQ", value: 1 },
          { metric: `relationship_ready_${species.metric_id}`, operator: "EQ", value: 1 },
          ...(species.requires_cross_species_network
            ? [{ metric: "dream_demon_other_species_network", operator: "EQ", value: 1 }]
            : []),
        ],
      })),
      ...formalSpecies.map((species) => ({
        id: `SPECIES_${species.id}`,
        ending_tier: "SPECIES",
        species_id: species.id,
        priority: 600,
        outcome: "COMPLETE",
        title: species.ending_title,
        description: species.ending_description,
        manager_outcome: species.manager_outcome,
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "final_gold", operator: "GTE", value: 80 },
          { metric: "final_reputation", operator: "GTE", value: 0 },
          { metric: `dominant_species_${species.metric_id}`, operator: "EQ", value: 1 },
          ...(species.requires_cross_species_network
            ? [{ metric: "dream_demon_other_species_network", operator: "EQ", value: 1 }]
            : []),
        ],
      })),
      {
        id: "NORMAL_STEWARDSHIP",
        ending_tier: "NORMAL",
        priority: 500,
        outcome: "COMPLETE",
        title: "베스페라의 평범한 인간 지배인",
        description: "목표 자금과 평판을 지켜냈지만 특정 종족 협약이나 숨은 진상에는 도달하지 않았습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
          { metric: "final_gold", operator: "GTE", value: 80 },
          { metric: "final_reputation", operator: "GTE", value: 0 },
        ],
      },
      {
        id: "BAD_OPERATIONAL",
        ending_tier: "BAD",
        priority: 100,
        outcome: "FAILURE",
        title: "상속 조건을 채우지 못하다",
        description: "시험 영업은 끝났지만 자금 또는 평판 조건을 충족하지 못해 호텔을 지키지 못했습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: data.scenarios.length },
        ],
      },
    ],
    fallback_ending: {
      id: "CAMPAIGN_INTERRUPTED",
      ending_tier: "BAD",
      priority: 0,
      outcome: "FAILURE",
      title: "상속 심사가 중단되다",
      description: "캠페인 종료 조건에 도달하지 못했습니다.",
    },
  };
  const indexes = createIndexes(data);
  return { ...data, indexes };
}

export function createEndlessGreyboxData(source) {
  const { indexes: _sourceIndexes, ...serializable } = source;
  const data = JSON.parse(JSON.stringify(serializable));
  const endlessGuestIds = new Set(
    data.guests.filter((guest) => guest.showcase_only !== true).map((guest) => guest.id),
  );
  data.scenarios = data.scenarios.map((scenario) => ({
    ...scenario,
    name: scenario.special_invite_showcase_only
      ? "다섯 번째 영업 · 높은 기대"
      : scenario.name,
    fixed_guests: (scenario.fixed_guests ?? []).filter((id) => endlessGuestIds.has(id)),
    applicants: (scenario.applicants ?? []).filter((id) => endlessGuestIds.has(id)),
    applicant_pool: (scenario.applicant_pool ?? []).filter((id) => endlessGuestIds.has(id)),
    special_invite_guest_ids: [],
    special_invite_showcase_only: false,
  }));
  data.display_relics = commonDisplayRelics();
  data.prototype_mode = {
    ...data.prototype_mode,
    type: "ENDLESS",
    total_nights: 5,
    accelerated: false,
    notice: "다섯 번의 영업마다 공개된 감사 평판을 넘겨 호텔 운영을 이어가는 무한 영업 회색 상자입니다.",
  };
  data.endless = {
    id: "ENDLESS_GREYBOX_01",
    status: "GREYBOX",
    season_length: 5,
    result_history_limit: 20,
    audit_history_limit: 12,
    audit: {
      policy_id: "PROVISIONAL_REPUTATION_WITH_EMERGENCY_PENALTY",
      metric_id: "DEVELOPMENT_AUDIT_SCORE",
      initial_target: 0,
      target_step_per_cleared_season: 2,
      max_target: 4,
      reachability_gain_per_remaining_operation: 4,
      emergency_penalty: 1,
      provisional: true,
      description: "이번 시즌 평판 변화 합계에서 마감 긴급 처리 1회당 1점을 차감하는 개발용 감사 점수입니다.",
    },
    run_fame: {
      policy_id: "PROVISIONAL_CLEARED_SEASON_COUNT",
      fame_per_cleared_season: 1,
      provisional: true,
    },
    risk: {
      policy_id: "PROVISIONAL_CLEARED_SEASON_TIER",
      initial_tier: 1,
      tier_per_cleared_season: 1,
      provisional: true,
    },
    relic_offer: {
      id: "ENDLESS_COMMON_RELIC",
      pool_ids: ["COMMON"],
      offer_size: 3,
    },
  };
  data.run_completion = {
    record_namespace: "vespera.endless.greybox.v1",
    ending_rules: [
      {
        id: "ENDLESS_HOTEL_CLOSED",
        ending_tier: "ENDLESS_CLOSED",
        priority: 100,
        outcome: "FAILURE",
        title: "베스페라의 무한 영업이 끝나다",
        description: "시즌 감사 목표에 미달해 이번 가능 세계의 호텔 운영 기록을 마감했습니다.",
        conditions: [
          { metric: "completed_nights", operator: "GTE", value: 1 },
          { metric: "endless_closed", operator: "EQ", value: 1 },
        ],
      },
    ],
    fallback_ending: {
      id: "ENDLESS_RUN_INTERRUPTED",
      ending_tier: "ENDLESS_INCOMPLETE",
      priority: 0,
      outcome: "INCOMPLETE",
      title: "무한 영업 기록이 중단되다",
      description: "폐업 또는 자발적 마감 조건에 도달하지 않은 실행 기록입니다.",
    },
  };
  const indexes = createIndexes(data);
  validateEndlessData(data);
  return { ...data, indexes };
}

export function createIndexes(data) {
  const byId = (items) => Object.fromEntries(items.map((item) => [item.id, item]));
  const facilities = byId(data.facilities);
  const upgrades = Object.fromEntries(
    data.upgrades.map((upgrade) => {
      const facility = upgrade.facility_id ? facilities[upgrade.facility_id] : null;
      return [
        upgrade.id,
        {
          ...(facility ?? {}),
          ...upgrade,
          id: upgrade.id,
        },
      ];
    }),
  );
  return {
    rooms: byId(data.rooms),
    species: byId(data.species),
    ranks: byId(data.ranks),
    guests: byId(data.guests),
    facilities,
    upgrades,
    scenarios: byId(data.scenarios),
    displayRelics: byId(data.display_relics ?? []),
  };
}

function assertUnique(items, label) {
  const ids = items.map((item) => item.id);
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${label} 데이터에 중복 ID가 있습니다.`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertReferences(ids, index, owner, label) {
  for (const id of ids) {
    if (!index[id]) throw new Error(`${owner}가 존재하지 않는 ${label} ${id}을 참조합니다.`);
  }
}

function validateUpgradeGraph(data, indexes) {
  const visiting = new Set();
  const visited = new Set();

  function visit(upgradeId) {
    if (visited.has(upgradeId)) return;
    if (visiting.has(upgradeId)) throw new Error(`개선 선행조건에 순환이 있습니다: ${upgradeId}`);
    visiting.add(upgradeId);
    for (const requiredId of indexes.upgrades[upgradeId].requires ?? []) visit(requiredId);
    visiting.delete(upgradeId);
    visited.add(upgradeId);
  }

  for (const upgrade of data.upgrades) visit(upgrade.id);
}

function validateHiddenPreference(rule, owner, indexes, seenIds) {
  const supportedTypes = new Set([
    "ROOM_HAS",
    "ROOM_NOT_HAS",
    "FLOOR_IS",
    "FLOOR_AT_LEAST",
    "FLOOR_AT_MOST",
    "ELEVATOR_DISTANCE_AT_LEAST",
    "ELEVATOR_DISTANCE_AT_MOST",
    "ADJACENT_GUEST",
    "NO_OCCUPIED_ADJACENT",
    "ADJACENT_SPECIES",
    "SAME_FLOOR_SPECIES",
    "NEAR_FACILITY",
  ]);
  assert(typeof rule.id === "string" && rule.id.length > 0, `${owner}의 숨은 선호에 ID가 없습니다.`);
  assert(!seenIds.has(rule.id), `숨은 선호 ID가 중복되었습니다: ${rule.id}`);
  seenIds.add(rule.id);
  assert(supportedTypes.has(rule.type), `${owner}의 숨은 선호 ${rule.id}에 지원하지 않는 규칙 ${rule.type}이 있습니다.`);
  assert(Number.isFinite(rule.points) && rule.points > 0, `${owner}의 숨은 선호 ${rule.id}는 양의 점수여야 합니다.`);
  assert(typeof rule.label === "string" && rule.label.length > 0, `${owner}의 숨은 선호 ${rule.id}에 설명이 없습니다.`);
  assert(rule.required !== true && rule.hard !== true && rule.kind !== "HARD", `${owner}의 숨은 선호는 필수 조건이 될 수 없습니다.`);

  if (["ROOM_HAS", "ROOM_NOT_HAS"].includes(rule.type)) {
    assert(typeof rule.attribute === "string" && rule.attribute.length > 0, `${rule.id}에 객실 속성이 필요합니다.`);
  } else if (["FLOOR_IS", "FLOOR_AT_LEAST", "FLOOR_AT_MOST"].includes(rule.type)) {
    assert(Number.isInteger(rule.floor), `${rule.id}에 층 정보가 필요합니다.`);
  } else if (["ELEVATOR_DISTANCE_AT_LEAST", "ELEVATOR_DISTANCE_AT_MOST"].includes(rule.type)) {
    assert(Number.isInteger(rule.distance) && rule.distance >= 0, `${rule.id}에 거리 정보가 필요합니다.`);
  } else if (rule.type === "ADJACENT_GUEST") {
    assertReferences([rule.guest_id], indexes.guests, rule.id, "손님");
  } else if (["ADJACENT_SPECIES", "SAME_FLOOR_SPECIES"].includes(rule.type)) {
    assertReferences([rule.species_id], indexes.species, rule.id, "종족");
  } else if (rule.type === "NEAR_FACILITY") {
    assertReferences([rule.facility_id], indexes.facilities, rule.id, "시설");
  }
}

function validateDislike(rule, owner, indexes) {
  const supportedTypes = new Set([
    "ROOM_HAS",
    "ROOM_NOT_HAS",
    "FLOOR_IS",
    "FLOOR_AT_LEAST",
    "FLOOR_AT_MOST",
    "ELEVATOR_DISTANCE_AT_LEAST",
    "ELEVATOR_DISTANCE_AT_MOST",
    "ADJACENT_GUEST",
    "NO_OCCUPIED_ADJACENT",
    "ADJACENT_SPECIES",
    "SAME_FLOOR_SPECIES",
    "NEAR_FACILITY",
  ]);
  assert(supportedTypes.has(rule.type), `${owner}의 불호에 지원하지 않는 규칙 ${rule.type}이 있습니다.`);
  assert(Number.isFinite(rule.points) && rule.points < 0, `${owner}의 불호는 음의 만족도여야 합니다.`);
  assert(
    Number.isInteger(rule.ignored_at_prestige_gap) && rule.ignored_at_prestige_gap >= 1,
    `${owner}의 불호에 호텔 격차 무시 기준이 필요합니다.`,
  );
  assert(typeof rule.label === "string" && rule.label.length > 0, `${owner}의 불호에 설명이 없습니다.`);
  if (rule.guest_id) assertReferences([rule.guest_id], indexes.guests, owner, "손님");
  if (rule.species_id) assertReferences([rule.species_id], indexes.species, owner, "종족");
  if (rule.facility_id) assertReferences([rule.facility_id], indexes.facilities, owner, "시설");
}

export function validateData(data, indexes = createIndexes(data)) {
  const rankIds = ["N", "R", "SR", "SSR"];
  const expectedRanks = new Set(rankIds);
  assert(data.schema_version === 4, "쇼케이스 데이터는 schema_version 4여야 합니다.");
  assert(data.prototype_mode?.type === "SHOWCASE", "프로토타입 모드는 SHOWCASE여야 합니다.");
  assert(data.prototype_mode?.total_nights === 5, "쇼케이스는 정확히 5회 영업이어야 합니다.");
  assert(data.prototype_mode?.accelerated === true, "쇼케이스의 압축 성장 표시가 필요합니다.");
  assert(Boolean(data.prototype_mode?.notice), "쇼케이스 안내 문구가 필요합니다.");
  assert(typeof data.run_completion?.record_namespace === "string", "실행 기록 네임스페이스가 필요합니다.");
  assert(Array.isArray(data.run_completion?.ending_rules) && data.run_completion.ending_rules.length > 0, "종료 규칙이 필요합니다.");
  const endingMetrics = new Set([
    "completed_nights",
    "total_income",
    "reputation_delta",
    "final_gold",
    "final_reputation",
    "accepted_guests",
    "rejected_guests",
    "canceled_guests",
    "purchased_upgrades",
    "emergency_nights",
    "foresight_retries",
    "expected_nights",
  ]);
  const endingIds = new Set();
  for (const ending of data.run_completion.ending_rules) {
    assert(typeof ending.id === "string" && !endingIds.has(ending.id), `종료 ID가 없거나 중복되었습니다: ${ending.id}`);
    endingIds.add(ending.id);
    assert(Number.isFinite(ending.priority), `${ending.id}의 우선순위가 필요합니다.`);
    assert(["COMPLETE", "FAILURE"].includes(ending.outcome), `${ending.id}의 결과 유형이 잘못되었습니다.`);
    assert(typeof ending.title === "string" && typeof ending.description === "string", `${ending.id}의 표시 문구가 필요합니다.`);
    assert(Array.isArray(ending.conditions) && ending.conditions.length > 0, `${ending.id}의 종료 조건이 필요합니다.`);
    for (const condition of ending.conditions) {
      assert(["GTE", "LTE", "EQ"].includes(condition.operator), `${ending.id}의 비교 연산자가 잘못되었습니다.`);
      assert(endingMetrics.has(condition.metric) && Number.isFinite(condition.value), `${ending.id}의 조건 값이 잘못되었습니다.`);
    }
  }
  const fallbackEnding = data.run_completion?.fallback_ending;
  assert(typeof fallbackEnding?.id === "string", "종료 규칙 누락 시 대체 결말이 필요합니다.");
  assert(!endingIds.has(fallbackEnding.id), "대체 결말 ID는 종료 규칙과 달라야 합니다.");
  assert(["INCOMPLETE", "FAILURE"].includes(fallbackEnding.outcome), "대체 결말의 결과 유형이 잘못되었습니다.");
  assert(typeof fallbackEnding.title === "string" && typeof fallbackEnding.description === "string", "대체 결말의 표시 문구가 필요합니다.");
  assert(data.prototype_mode?.upgrade_offer_sizes?.EXPANSION === 1, "영업 준비에는 증축 제안 1개가 필요합니다.");
  assert(data.prototype_mode?.upgrade_offer_sizes?.FACILITY >= 2, "영업 준비에는 시설·인테리어 제안이 최소 2개 필요합니다.");
  assert(data.stayover_rules?.locks_initial_room === true, "연박 손님은 첫 배정 객실을 유지해야 합니다.");
  assert(Number.isFinite(data.balance?.room_service_cost) && data.balance.room_service_cost >= 0, "객실 정비 비용이 잘못되었습니다.");
  assert(Number.isFinite(data.balance?.minimum_cleanliness), "최소 청결 기준이 필요합니다.");
  assert(Number.isFinite(data.balance?.minimum_durability), "최소 내구 기준이 필요합니다.");
  assert(data.balance?.booking_capacity_per_expansion_room === 1, "증축 객실당 응대 한도는 1명씩 늘어야 합니다.");
  assert(Number.isFinite(data.balance?.prestige_satisfaction_per_tier), "호텔 격차 만족도 계수가 필요합니다.");
  assert(Number.isFinite(data.balance?.evaluation_grade_thresholds?.good), "좋은 운영 평가 기준이 필요합니다.");
  assert(Number.isFinite(data.balance?.evaluation_grade_thresholds?.excellent), "훌륭한 운영 평가 기준이 필요합니다.");

  [
    [data.rooms, "객실"],
    [data.species, "종족"],
    [data.ranks, "등급"],
    [data.guests, "손님"],
    [data.facilities, "시설"],
    [data.upgrades, "개선"],
    [data.scenarios, "영업"],
  ].forEach(([items, label]) => assertUnique(items, label));

  assert(data.species.length === 4, "쇼케이스에는 정확히 4개 종족이 필요합니다.");
  assert(data.guests.length >= 12, "쇼케이스에는 손님이 최소 12명 필요합니다.");
  assert(data.upgrades.length >= 8, "쇼케이스에는 시설·증축 개선이 최소 8개 필요합니다.");
  assert(Array.isArray(data.prototype_mode.tutorial_guest_ids) && data.prototype_mode.tutorial_guest_ids.length === 2, "튜토리얼 손님은 두 명이어야 합니다.");
  assertReferences(data.prototype_mode.tutorial_guest_ids, indexes.guests, "튜토리얼", "손님");
  assert(
    data.ranks.length === 4 && data.ranks.every((rank) => expectedRanks.has(rank.id)),
    "등급은 N, R, SR, SSR 네 종류만 사용할 수 있습니다.",
  );

  const orderedRanks = [...data.ranks].sort((left, right) => left.order - right.order);
  orderedRanks.forEach((rank, index) => {
    assert(rank.id === rankIds[index], `등급 순서가 올바르지 않습니다: ${rank.id}`);
    assert(Number.isInteger(rank.unlock_stage) && rank.unlock_stage >= 1 && rank.unlock_stage <= 5, `${rank.id} unlock_stage가 잘못되었습니다.`);
    assert(Number.isInteger(rank.min_reputation) && rank.min_reputation >= 0, `${rank.id} min_reputation이 잘못되었습니다.`);
    assert(Boolean(rank.symbol), `${rank.id} 등급 기호가 없습니다.`);
    assert(/^#[0-9a-f]{6}$/i.test(rank.color), `${rank.id} 등급 색상이 잘못되었습니다.`);
    assert(Number.isFinite(rank.reputation_influence) && rank.reputation_influence > 0, `${rank.id} 평판 영향력이 잘못되었습니다.`);
    assert(Boolean(rank.reputation_influence_label), `${rank.id} 평판 영향 설명이 없습니다.`);
    assert(Number.isFinite(rank.positive_satisfaction_threshold) && rank.positive_satisfaction_threshold > 0, `${rank.id} 호평 만족도 기준이 잘못되었습니다.`);
    assert(Array.isArray(rank.soft_dislikes), `${rank.id} 불호 규칙 배열이 필요합니다.`);
    rank.soft_dislikes.forEach((rule) => validateDislike(rule, rank.id, indexes));
    if (index > 0) {
      assert(rank.unlock_stage >= orderedRanks[index - 1].unlock_stage, "상위 등급의 단계 잠금이 하위 등급보다 빨라서는 안 됩니다.");
      assert(rank.min_reputation >= orderedRanks[index - 1].min_reputation, "상위 등급의 평판 조건이 하위 등급보다 낮아서는 안 됩니다.");
      assert(rank.reputation_influence > orderedRanks[index - 1].reputation_influence, "상위 등급의 평판 영향력은 더 커야 합니다.");
      assert(
        rank.soft_preferences.length + rank.soft_dislikes.length
          >= orderedRanks[index - 1].soft_preferences.length + orderedRanks[index - 1].soft_dislikes.length,
        "상위 등급의 선호·불호 조건 수가 하위 등급보다 적어서는 안 됩니다.",
      );
    }
  });

  assert(Array.isArray(data.rank_odds) && data.rank_odds.length > 0, "평판별 등장 확률표가 필요합니다.");
  let previousThreshold = -1;
  for (const row of data.rank_odds) {
    assert(Number.isInteger(row.min_reputation) && row.min_reputation > previousThreshold, "등장 확률표의 평판 구간은 오름차순이어야 합니다.");
    previousThreshold = row.min_reputation;
    assert(Object.keys(row.odds).length === 4 && rankIds.every((rankId) => rankId in row.odds), "등장 확률표에는 네 등급이 모두 있어야 합니다.");
    const total = rankIds.reduce((sum, rankId) => {
      const value = row.odds[rankId];
      assert(Number.isFinite(value) && value >= 0, `${row.min_reputation} 평판의 ${rankId} 확률이 잘못되었습니다.`);
      return sum + value;
    }, 0);
    assert(total === 100, `${row.min_reputation} 평판의 등급 확률 합은 100이어야 합니다.`);
  }

  const hiddenPreferenceIds = new Set();
  for (const species of data.species) {
    assert(Boolean(species.icon), `${species.id}의 아이콘이 없습니다.`);
    assert(Array.isArray(species.synergy_thresholds) && species.synergy_thresholds.length > 0, `${species.id}의 종족 시너지가 없습니다.`);
    let previousCount = 1;
    for (const threshold of species.synergy_thresholds) {
      assert(Number.isInteger(threshold.count) && threshold.count > previousCount, `${species.id}의 시너지 인원 구간이 잘못되었습니다.`);
      assert(Number.isFinite(threshold.points) && threshold.points > 0, `${species.id}의 시너지 점수가 잘못되었습니다.`);
      previousCount = threshold.count;
    }
    const forbiddenHiddenFields = Object.keys(species).filter(
      (field) => field.startsWith("hidden_") && field !== "hidden_preferences_by_rank",
    );
    assert(forbiddenHiddenFields.length === 0, `${species.id}에 필수 또는 비선호 형태의 숨은 데이터가 있습니다: ${forbiddenHiddenFields.join(", ")}`);
    const hiddenByRank = species.hidden_preferences_by_rank;
    assert(hiddenByRank && typeof hiddenByRank === "object", `${species.id}의 종족·등급별 숨은 선호가 없습니다.`);
    assert(Object.keys(hiddenByRank).length === 4 && rankIds.every((rankId) => rankId in hiddenByRank), `${species.id}의 숨은 선호에는 N, R, SR, SSR 키가 모두 필요합니다.`);
    for (const rankId of rankIds) {
      const hiddenPreferences = hiddenByRank[rankId];
      assert(Array.isArray(hiddenPreferences), `${species.id}:${rankId} 숨은 선호는 배열이어야 합니다.`);
      if (rankId === "N") assert(hiddenPreferences.length === 0, `${species.id}:N에는 숨은 선호를 두지 않습니다.`);
      else assert(hiddenPreferences.length > 0, `${species.id}:${rankId}에는 숨은 선호가 필요합니다.`);
      for (const rule of hiddenPreferences) {
        validateHiddenPreference(rule, `${species.id}:${rankId}`, indexes, hiddenPreferenceIds);
      }
    }
  }

  for (const conflict of data.species_conflicts ?? []) {
    assert(conflict.species?.length === 2, "종족 상극은 두 종족을 참조해야 합니다.");
    assertReferences(conflict.species, indexes.species, conflict.label ?? "종족 상극", "종족");
    assert(Number.isFinite(conflict.points) && conflict.points < 0, `${conflict.label}의 상극 점수는 음수여야 합니다.`);
  }

  for (const guest of data.guests) {
    if (!indexes.species[guest.species]) {
      throw new Error(`${guest.id}의 종족 ${guest.species}이 존재하지 않습니다.`);
    }
    if (!indexes.ranks[guest.rank]) {
      throw new Error(`${guest.id}의 등급 ${guest.rank}이 존재하지 않습니다.`);
    }
    assert(guest.satisfied_reputation === undefined, `${guest.id}는 유효 배치만으로 고정 평판을 얻을 수 없습니다.`);
    if (Math.abs(guest.cancel_reputation) <= Math.abs(guest.reject_reputation)) {
      throw new Error(`${guest.id}의 막판 취소 손실은 거절 손실보다 커야 합니다.`);
    }
    assert(Number.isInteger(guest.stay_nights) && guest.stay_nights >= 1, `${guest.id}의 stay_nights가 잘못되었습니다.`);
    assert(guest.stayover_locks_initial_room === true, `${guest.id}는 연박 시 첫 객실을 유지해야 합니다.`);
    for (const field of ["cleanliness_impact", "durability_impact"]) {
      assert(Number.isInteger(guest[field]) && guest[field] >= 0, `${guest.id}의 ${field}가 잘못되었습니다.`);
    }
    for (const rule of [...guest.hard_constraints, ...guest.soft_preferences, ...(guest.soft_dislikes ?? [])]) {
      if (rule.guest_id) assertReferences([rule.guest_id], indexes.guests, guest.id, "손님");
      if (rule.facility_id) assertReferences([rule.facility_id], indexes.facilities, guest.id, "시설");
    }
    (guest.soft_dislikes ?? []).forEach((rule) => validateDislike(rule, guest.id, indexes));
    const hiddenFields = Object.keys(guest).filter((field) => field.startsWith("hidden_"));
    assert(hiddenFields.length === 0, `${guest.id}에는 개인 숨은 규칙을 둘 수 없습니다: ${hiddenFields.join(", ")}`);
  }

  for (const facility of data.facilities) {
    assert(expectedRanks.has(facility.rarity), `${facility.id}의 시설 등급이 잘못되었습니다.`);
    assert(facility.stackable === true, `${facility.id}는 다른 시설과 함께 보유 가능해야 합니다.`);
    assertReferences(facility.blocked_rooms ?? [], indexes.rooms, facility.id, "객실");
    assertReferences((facility.room_attribute_changes ?? []).map((change) => change.room_id), indexes.rooms, facility.id, "객실");
    assertReferences((facility.room_bonuses ?? []).map((bonus) => bonus.room_id), indexes.rooms, facility.id, "객실");
    for (const link of facility.adjacency_links ?? []) {
      assert(link.length === 2, `${facility.id}의 이웃 연결은 객실 두 개여야 합니다.`);
      assertReferences(link, indexes.rooms, facility.id, "객실");
    }
  }

  const upgradeRarities = new Set();
  const roomUnlockOwner = {};
  for (const upgrade of data.upgrades) {
    upgradeRarities.add(upgrade.rarity);
    assert(expectedRanks.has(upgrade.rarity), `${upgrade.id}의 개선 등급이 잘못되었습니다.`);
    assert(["FACILITY", "EXPANSION"].includes(upgrade.kind), `${upgrade.id}의 개선 종류가 잘못되었습니다.`);
    assert(Number.isFinite(upgrade.cost) && upgrade.cost >= 0, `${upgrade.id}의 비용이 잘못되었습니다.`);
    assert(Number.isInteger(upgrade.unlock_stage) && upgrade.unlock_stage >= 2 && upgrade.unlock_stage <= 5, `${upgrade.id}의 등장 단계가 잘못되었습니다.`);
    assert(Number.isInteger(upgrade.minimum_reputation) && upgrade.minimum_reputation >= 0, `${upgrade.id}의 평판 조건이 잘못되었습니다.`);
    assert(upgrade.unlock_stage >= indexes.ranks[upgrade.rarity].unlock_stage, `${upgrade.id}가 등급 단계보다 일찍 등장합니다.`);
    assert(upgrade.minimum_reputation >= indexes.ranks[upgrade.rarity].min_reputation, `${upgrade.id}가 등급 평판 조건보다 일찍 등장합니다.`);
    assertReferences(upgrade.requires ?? [], indexes.upgrades, upgrade.id, "선행 개선");
    if (upgrade.kind === "FACILITY") {
      assertReferences([upgrade.facility_id], indexes.facilities, upgrade.id, "시설");
      assert(upgrade.stackable === true, `${upgrade.id} 시설 개선은 누적 보유 가능해야 합니다.`);
    } else {
      assert(Array.isArray(upgrade.room_unlocks) && upgrade.room_unlocks.length > 0, `${upgrade.id}의 증축 객실이 없습니다.`);
      assertReferences(upgrade.room_unlocks, indexes.rooms, upgrade.id, "객실");
      for (const roomId of upgrade.room_unlocks) {
        assert(!roomUnlockOwner[roomId], `${roomId}를 두 개선이 동시에 해금합니다.`);
        assert(indexes.rooms[roomId].built_from_start === false, `${upgrade.id}는 이미 건설된 객실을 해금할 수 없습니다.`);
        roomUnlockOwner[roomId] = upgrade.id;
      }
    }
  }
  assert(rankIds.every((rankId) => upgradeRarities.has(rankId)), "개선 제안에는 N, R, SR, SSR 등급이 모두 있어야 합니다.");
  validateUpgradeGraph(data, indexes);

  const f1Expansion = roomUnlockOwner["F1-D"];
  const f2Expansion = roomUnlockOwner["F2-D"];
  const f3Expansion = roomUnlockOwner["F3-D"];
  assert(Boolean(f1Expansion && f2Expansion && f3Expansion), "F1-D, F2-D, F3-D 증축이 모두 필요합니다.");
  assert(indexes.upgrades[f2Expansion].requires.includes(f1Expansion), "F2-D 증축은 F1-D 증축을 선행조건으로 가져야 합니다.");
  assert(indexes.upgrades[f3Expansion].requires.includes(f2Expansion), "F3-D 증축은 F2-D 증축을 선행조건으로 가져야 합니다.");

  assert(data.scenarios.length === 5, "쇼케이스에는 정확히 5개 영업 시나리오가 필요합니다.");
  const stages = [...data.scenarios].map((scenario) => scenario.stage).sort((left, right) => left - right);
  assert(stages.every((stage, index) => stage === index + 1), "영업 단계는 1부터 5까지 한 번씩 있어야 합니다.");
  for (const scenario of data.scenarios) {
    const allGuestReferences = [
      ...scenario.fixed_guests,
      ...(scenario.applicants ?? []),
      ...(scenario.applicant_pool ?? []),
      ...(scenario.special_invite_guest_ids ?? []),
    ];
    assertReferences(allGuestReferences, indexes.guests, scenario.id, "손님");
    assertReferences((scenario.facility_options ?? []).filter(Boolean), indexes.facilities, scenario.id, "시설");
    assert(Number.isInteger(scenario.capacity) && scenario.capacity > 0, `${scenario.id}의 기본 예약 응대 한도가 잘못되었습니다.`);
    assert(Number.isInteger(scenario.offer_size) && scenario.offer_size >= 0, `${scenario.id}의 제안 인원이 잘못되었습니다.`);
    for (const guestId of scenario.applicant_pool ?? []) {
      const rank = indexes.ranks[indexes.guests[guestId].rank];
      assert(rank.unlock_stage <= scenario.stage, `${scenario.id} 후보 ${guestId}의 등급이 단계보다 먼저 등장합니다.`);
    }
    if (scenario.guaranteed_rank) {
      assert(expectedRanks.has(scenario.guaranteed_rank), `${scenario.id}의 보장 등급이 잘못되었습니다.`);
      assert(indexes.ranks[scenario.guaranteed_rank].unlock_stage <= scenario.stage, `${scenario.id}의 보장 등급이 단계 잠금을 위반합니다.`);
    }
  }

  const firstScenario = data.scenarios.find((scenario) => scenario.stage === 1);
  assert(firstScenario.fixed_guests.every((guestId) => indexes.guests[guestId].rank === "N"), "첫 영업의 고정 손님은 모두 N 등급이어야 합니다.");
  const secondScenario = data.scenarios.find((scenario) => scenario.stage === 2);
  assert(secondScenario.guaranteed_rank === "R", "두 번째 영업은 R 손님을 보장해야 합니다.");
  const srScenario = data.scenarios.find((scenario) => [3, 4].includes(scenario.stage) && scenario.guaranteed_rank === "SR");
  assert(Boolean(srScenario), "세 번째 또는 네 번째 영업은 SR 손님을 보장해야 합니다.");
  const fifthScenario = data.scenarios.find((scenario) => scenario.stage === 5);
  assert(fifthScenario.guaranteed_rank === "SSR", "다섯 번째 영업은 SSR 손님을 보장해야 합니다.");
  assert(fifthScenario.special_invite_showcase_only === true, "다섯 번째 SSR은 쇼케이스 전용 초청이어야 합니다.");
  assert((fifthScenario.special_invite_guest_ids ?? []).length > 0, "다섯 번째 영업의 특별 초청 손님이 없습니다.");
  for (const guestId of fifthScenario.special_invite_guest_ids) {
    const guest = indexes.guests[guestId];
    assert(guest.rank === "SSR" && guest.showcase_only === true, `${guestId}는 쇼케이스 전용 SSR이어야 합니다.`);
  }
}

export function getGuestRules(data, guestId) {
  const guest = data.indexes.guests[guestId];
  const species = data.indexes.species[guest.species];
  const rank = data.indexes.ranks[guest.rank];
  const commonRequired = [...species.hard_constraints];
  const rankRequired = [...rank.hard_constraints];
  const personalRequired = [...guest.hard_constraints];
  const commonPreferences = [...species.soft_preferences];
  const rankPreferences = [...rank.soft_preferences];
  const personalPreferences = [...guest.soft_preferences];
  const commonDislikes = [...(species.soft_dislikes ?? [])];
  const rankDislikes = [...(rank.soft_dislikes ?? [])];
  const personalDislikes = [...(guest.soft_dislikes ?? [])];
  const hiddenPreferences = [...(species.hidden_preferences_by_rank?.[guest.rank] ?? [])];
  return {
    commonRequired,
    rankRequired,
    personalRequired,
    commonPreferences,
    rankPreferences,
    personalPreferences,
    commonDislikes,
    rankDislikes,
    personalDislikes,
    hiddenPreferences,
    hard: [...commonRequired, ...rankRequired, ...personalRequired],
    soft: [...commonPreferences, ...rankPreferences, ...personalPreferences],
    dislikes: [...commonDislikes, ...rankDislikes, ...personalDislikes],
  };
}
