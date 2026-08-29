import { compileCampaignCalendar } from "./campaign-calendar.js";

export const CHAPTER_DEBT_SETTLEMENT_KINDS = Object.freeze([
  "CUMULATIVE_MINIMUM",
  "FINAL_CLEARANCE",
  "NONE",
]);

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid campaign chapter schedule: ${message}`);
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function validateDebtSettlement(value, owner) {
  assert(value && typeof value === "object" && !Array.isArray(value),
    `${owner}.debt_settlement must be an object`);
  assert(CHAPTER_DEBT_SETTLEMENT_KINDS.includes(value.kind),
    `${owner}.debt_settlement.kind is unknown`);
  if (value.kind === "NONE") {
    assert(value.target_id === undefined,
      `${owner}.debt_settlement.target_id cannot accompany NONE`);
    assert(value.recovery_eligible === false,
      `${owner}.debt_settlement.recovery_eligible must be false for NONE`);
    return;
  }
  assert(nonEmptyString(value.target_id),
    `${owner}.debt_settlement.target_id must be a non-empty string`);
  assert(typeof value.recovery_eligible === "boolean",
    `${owner}.debt_settlement.recovery_eligible must be boolean`);
  if (value.kind === "FINAL_CLEARANCE") {
    assert(value.recovery_eligible === false,
      `${owner}.debt_settlement.recovery_eligible must be false for FINAL_CLEARANCE`);
  }
}

export function validateCampaignChapterSchedule(schedule, calendarConfig, options = {}) {
  assert(schedule && typeof schedule === "object" && !Array.isArray(schedule),
    "schedule must be an object");
  assert(nonEmptyString(schedule.id), "id must be a non-empty string");
  assert(nonEmptyString(schedule.calendar_id), "calendar_id must be a non-empty string");
  assert(schedule.calendar_id === calendarConfig?.calendar_id,
    "calendar_id must match the referenced calendar");
  assert(positiveSafeInteger(schedule.version), "version must be a positive safe integer");
  assert(positiveSafeInteger(schedule.total_stages), "total_stages must be a positive safe integer");
  assert(schedule.total_stages === calendarConfig?.total_stages,
    "total_stages must match the referenced calendar");
  assert(Array.isArray(schedule.chapters) && schedule.chapters.length > 0,
    "chapters must be a non-empty array");

  const calendar = compileCampaignCalendar(calendarConfig, options.calendarValidationOptions ?? {});
  const ids = new Set();
  const targetIds = new Set();
  let expectedStart = 1;
  for (const [index, chapter] of schedule.chapters.entries()) {
    const owner = `chapters[${index}]`;
    assert(chapter && typeof chapter === "object" && !Array.isArray(chapter),
      `${owner} must be an object`);
    assert(nonEmptyString(chapter.id), `${owner}.id must be a non-empty string`);
    assert(!ids.has(chapter.id), `${owner}.id must be unique`);
    ids.add(chapter.id);
    assert(chapter.number === index + 1, `${owner}.number must be sequential`);
    assert(nonEmptyString(chapter.label), `${owner}.label must be a non-empty string`);
    assert(positiveSafeInteger(chapter.start_stage), `${owner}.start_stage must be positive`);
    assert(positiveSafeInteger(chapter.end_stage), `${owner}.end_stage must be positive`);
    assert(chapter.start_stage === expectedStart,
      `${owner}.start_stage must continue without a gap or overlap`);
    assert(chapter.end_stage >= chapter.start_stage,
      `${owner}.end_stage must not precede start_stage`);
    assert(chapter.end_stage <= schedule.total_stages,
      `${owner}.end_stage must be within the schedule`);
    assert(nonEmptyString(chapter.season_id), `${owner}.season_id must be a non-empty string`);
    const startDay = calendar.days[chapter.start_stage - 1];
    const endDay = calendar.days[chapter.end_stage - 1];
    assert(startDay.season.id === chapter.season_id,
      `${owner}.start_stage must belong to season_id`);
    assert(endDay.season.id === chapter.season_id,
      `${owner}.end_stage must belong to season_id`);
    assert(typeof chapter.hidden === "boolean", `${owner}.hidden must be boolean`);
    validateDebtSettlement(chapter.debt_settlement, owner);
    if (chapter.debt_settlement.target_id) {
      assert(!targetIds.has(chapter.debt_settlement.target_id),
        `${owner}.debt_settlement.target_id must be unique`);
      targetIds.add(chapter.debt_settlement.target_id);
    }
    if (chapter.entry_gate_id !== undefined) {
      assert(nonEmptyString(chapter.entry_gate_id),
        `${owner}.entry_gate_id must be a non-empty string`);
    }
    expectedStart = chapter.end_stage + 1;
  }
  assert(expectedStart === schedule.total_stages + 1,
    "chapters must cover every configured stage exactly once");
  return true;
}

function compileUnchecked(schedule, calendarConfig, options = {}) {
  const calendar = compileCampaignCalendar(calendarConfig, options.calendarValidationOptions ?? {});
  const chapters = schedule.chapters.map((chapter) => ({
    id: chapter.id,
    number: chapter.number,
    label: chapter.label,
    startStage: chapter.start_stage,
    endStage: chapter.end_stage,
    stageCount: chapter.end_stage - chapter.start_stage + 1,
    seasonId: chapter.season_id,
    hidden: chapter.hidden,
    entryGateId: chapter.entry_gate_id ?? null,
    debtSettlement: {
      kind: chapter.debt_settlement.kind,
      targetId: chapter.debt_settlement.target_id ?? null,
      recoveryEligible: chapter.debt_settlement.recovery_eligible,
    },
  }));
  const days = calendar.days.map((calendarDay) => {
    const chapter = chapters.find((candidate) => (
      calendarDay.stageNumber >= candidate.startStage
      && calendarDay.stageNumber <= candidate.endStage
    ));
    return {
      stageNumber: calendarDay.stageNumber,
      chapter: {
        id: chapter.id,
        number: chapter.number,
        label: chapter.label,
        day: calendarDay.stageNumber - chapter.startStage + 1,
        stageCount: chapter.stageCount,
        hidden: chapter.hidden,
      },
      isChapterStart: calendarDay.stageNumber === chapter.startStage,
      isChapterEnd: calendarDay.stageNumber === chapter.endStage,
      entryGateId: calendarDay.stageNumber === chapter.startStage
        ? chapter.entryGateId
        : null,
      debtSettlement: calendarDay.stageNumber === chapter.endStage
        ? { ...chapter.debtSettlement }
        : null,
    };
  });
  return {
    type: "COMPILED_CAMPAIGN_CHAPTER_SCHEDULE",
    id: schedule.id,
    version: schedule.version,
    calendarId: schedule.calendar_id,
    totalStages: schedule.total_stages,
    chapters,
    days,
  };
}

export function compileCampaignChapters(schedule, calendarConfig, options = {}) {
  validateCampaignChapterSchedule(schedule, calendarConfig, options);
  return compileUnchecked(schedule, calendarConfig, options);
}

export function campaignChapterForStage(schedule, calendarConfig, stageNumber, options = {}) {
  const compiled = compileCampaignChapters(schedule, calendarConfig, options);
  assert(Number.isSafeInteger(stageNumber) && stageNumber >= 1 && stageNumber <= compiled.totalStages,
    "stageNumber must be within the configured schedule");
  return compiled.days[stageNumber - 1];
}

export function validateCampaignChapterPrefix(
  baseSchedule,
  extendedSchedule,
  baseCalendar,
  extendedCalendar,
  options = {},
) {
  const base = compileCampaignChapters(baseSchedule, baseCalendar, options);
  const extended = compileCampaignChapters(extendedSchedule, extendedCalendar, options);
  assert(extended.totalStages > base.totalStages,
    "extended schedule must contain more stages than the base schedule");
  assert(extended.chapters.length > base.chapters.length,
    "extended schedule must add at least one chapter");
  assert(JSON.stringify(extended.chapters.slice(0, base.chapters.length))
    === JSON.stringify(base.chapters),
  "extended schedule must preserve every base chapter");
  assert(JSON.stringify(extended.days.slice(0, base.totalStages)) === JSON.stringify(base.days),
    "extended schedule must preserve every base chapter day");
  return true;
}
