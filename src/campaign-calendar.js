const DEFAULT_EFFECTS = Object.freeze({
  applicant_bonus: 0,
  rank_multipliers: Object.freeze({}),
  species_multipliers: Object.freeze({}),
});

export const CAMPAIGN_WEEK_LENGTH = 7;
export const CAMPAIGN_WEEKEND_DAYS = Object.freeze([6, 7]);
export const CAMPAIGN_CALENDAR_STAGE_LIMIT = 10_000;
export const CAMPAIGN_WEEKDAY_IDS = Object.freeze([
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
  "SUNDAY",
]);

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid campaign calendar: ${message}`);
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function round6(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1_000_000) / 1_000_000;
}

function validateMultiplierMap(value, owner, field, allowedIds = null) {
  assert(value && typeof value === "object" && !Array.isArray(value), `${owner}.${field} must be an object`);
  for (const [id, multiplier] of Object.entries(value)) {
    assert(nonEmptyString(id), `${owner}.${field} contains an empty id`);
    assert(finiteNumber(multiplier) && multiplier > 0, `${owner}.${field}.${id} must be greater than 0`);
    if (allowedIds) assert(allowedIds.has(id), `${owner}.${field}.${id} is not a known id`);
  }
}

function validateEffects(effects = DEFAULT_EFFECTS, owner, knownIds = {}) {
  assert(effects && typeof effects === "object" && !Array.isArray(effects), `${owner}.effects must be an object`);
  const applicantBonus = effects.applicant_bonus ?? 0;
  assert(Number.isSafeInteger(applicantBonus), `${owner}.effects.applicant_bonus must be a safe integer`);
  validateMultiplierMap(
    effects.rank_multipliers ?? {},
    `${owner}.effects`,
    "rank_multipliers",
    knownIds.rankIds,
  );
  validateMultiplierMap(
    effects.species_multipliers ?? {},
    `${owner}.effects`,
    "species_multipliers",
    knownIds.speciesIds,
  );
}

function allocateSeasonStageCounts(config) {
  const totalStages = Number(config.total_stages);
  const seasons = config.seasons ?? [];
  const remaining = totalStages - seasons.length;
  const weightTotal = seasons.reduce((sum, season) => sum + Number(season.weight), 0);
  assert(finiteNumber(weightTotal) && weightTotal > 0, "season weight total must be finite");
  const shares = seasons.map((season, index) => {
    const raw = remaining * Number(season.weight) / weightTotal;
    const floor = Math.floor(raw);
    return {
      index,
      count: 1 + floor,
      remainder: raw - floor,
    };
  });
  let unassigned = totalStages - shares.reduce((sum, share) => sum + share.count, 0);
  const remainderOrder = shares.slice().sort((left, right) =>
    right.remainder - left.remainder || left.index - right.index
  );
  for (let index = 0; index < unassigned; index += 1) {
    remainderOrder[index].count += 1;
  }
  return shares.sort((left, right) => left.index - right.index).map((share) => share.count);
}

function seasonRangesUnchecked(config) {
  const stageCounts = allocateSeasonStageCounts(config);
  let startStage = 1;
  return config.seasons.map((season, index) => {
    const stageCount = stageCounts[index];
    const range = {
      id: season.id,
      label: season.label,
      index,
      startStage,
      endStage: startStage + stageCount - 1,
      stageCount,
    };
    startStage = range.endStage + 1;
    return range;
  });
}

export function campaignSeasonRanges(config, options = {}) {
  validateCampaignCalendar(config, options);
  return seasonRangesUnchecked(config);
}

function validateSeasonAnchor(anchor, owner, range) {
  assert(anchor && typeof anchor === "object" && !Array.isArray(anchor), `${owner} must be an object`);
  assert(["START", "END"].includes(anchor.anchor), `${owner}.anchor must be START or END`);
  const offset = anchor.offset === undefined ? 0 : anchor.offset;
  assert(Number.isSafeInteger(offset) && offset >= 0 && offset < range.stageCount,
    `${owner}.offset must resolve inside the season`);
}

function seasonAnchorDay(anchor, range) {
  const offset = anchor.offset === undefined ? 0 : anchor.offset;
  return anchor.anchor === "START" ? 1 + offset : range.stageCount - offset;
}

function validateScheduledEntry(entry, owner, config, ranges, knownIds) {
  assert(entry && typeof entry === "object" && !Array.isArray(entry), `${owner} must be an object`);
  assert(nonEmptyString(entry.id), `${owner}.id must be a non-empty string`);
  assert(nonEmptyString(entry.label), `${owner}.label must be a non-empty string`);
  const hasStages = hasOwn(entry, "stage_numbers");
  const hasSeasonDays = hasOwn(entry, "season_days");
  const hasSeasonAnchors = hasOwn(entry, "season_anchors");
  const selectorCount = [hasStages, hasSeasonDays, hasSeasonAnchors].filter(Boolean).length;
  assert(selectorCount === 1, `${owner} must use exactly one schedule selector`);
  if (hasStages) {
    assert(Array.isArray(entry.stage_numbers), `${owner}.stage_numbers must be an array`);
    assert(entry.season_id === undefined, `${owner}.season_id cannot accompany stage_numbers`);
    assert(entry.stage_numbers.length > 0, `${owner}.stage_numbers must not be empty`);
    const uniqueStages = new Set(entry.stage_numbers);
    assert(uniqueStages.size === entry.stage_numbers.length, `${owner}.stage_numbers must be unique`);
    for (const stage of entry.stage_numbers) {
      assert(Number.isSafeInteger(stage) && stage >= 1 && stage <= config.total_stages,
        `${owner}.stage_numbers contains an out-of-range stage`);
    }
  } else {
    assert(nonEmptyString(entry.season_id), `${owner}.season_id must accompany a season selector`);
    const range = ranges.find((candidate) => candidate.id === entry.season_id);
    assert(Boolean(range), `${owner}.season_id does not reference a configured season`);
    if (hasSeasonDays) {
      assert(Array.isArray(entry.season_days), `${owner}.season_days must be an array`);
      assert(entry.season_days.length > 0, `${owner}.season_days must not be empty`);
      const uniqueDays = new Set(entry.season_days);
      assert(uniqueDays.size === entry.season_days.length, `${owner}.season_days must be unique`);
      for (const day of entry.season_days) {
        assert(Number.isSafeInteger(day) && day >= 1 && day <= range.stageCount,
          `${owner}.season_days contains an out-of-range day`);
      }
    } else {
      assert(Array.isArray(entry.season_anchors), `${owner}.season_anchors must be an array`);
      assert(entry.season_anchors.length > 0, `${owner}.season_anchors must not be empty`);
      for (const [index, anchor] of entry.season_anchors.entries()) {
        validateSeasonAnchor(anchor, `${owner}.season_anchors[${index}]`, range);
      }
      const resolvedDays = entry.season_anchors.map((anchor) => seasonAnchorDay(anchor, range));
      assert(new Set(resolvedDays).size === resolvedDays.length,
        `${owner}.season_anchors must resolve to unique days`);
    }
  }
  assert(entry.tags === undefined || (Array.isArray(entry.tags) && entry.tags.every(nonEmptyString)),
    `${owner}.tags must contain only non-empty strings`);
  validateEffects(entry.effects ?? {}, owner, knownIds);
}

export function validateCampaignCalendar(config, options = {}) {
  const knownIds = {
    rankIds: Array.isArray(options.rankIds) ? new Set(options.rankIds) : null,
    speciesIds: Array.isArray(options.speciesIds) ? new Set(options.speciesIds) : null,
  };
  assert(config && typeof config === "object" && !Array.isArray(config), "config must be an object");
  assert(positiveSafeInteger(config.total_stages), "total_stages must be a positive safe integer");
  assert(config.total_stages <= CAMPAIGN_CALENDAR_STAGE_LIMIT,
    `total_stages must not exceed ${CAMPAIGN_CALENDAR_STAGE_LIMIT}`);
  const hasCalendarId = hasOwn(config, "calendar_id");
  const hasCalendarVersion = hasOwn(config, "calendar_version");
  assert(hasCalendarId === hasCalendarVersion,
    "calendar_id and calendar_version must be configured together");
  if (hasCalendarId) {
    assert(nonEmptyString(config.calendar_id), "calendar_id must be a non-empty string");
    assert(positiveSafeInteger(config.calendar_version), "calendar_version must be a positive safe integer");
  }
  assert(config.week_length === CAMPAIGN_WEEK_LENGTH, "week_length must use the seven-day campaign week");
  assert(Array.isArray(config.weekend_days), "weekend_days must be an array");
  assert(new Set(config.weekend_days).size === config.weekend_days.length,
    "weekend_days must be unique");
  for (const day of config.weekend_days) {
    assert(Number.isSafeInteger(day) && day >= 1 && day <= config.week_length,
      "weekend_days contains an out-of-range day");
  }
  assert(config.weekend_days.length === 2
    && config.weekend_days.every((day, index) => day === CAMPAIGN_WEEKEND_DAYS[index]),
  "weekend_days must be the sixth and seventh day");
  validateEffects(config.weekend_effects ?? {}, "weekend", knownIds);

  assert(Array.isArray(config.seasons) && config.seasons.length > 0,
    "seasons must be a non-empty array");
  assert(config.total_stages >= config.seasons.length,
    "total_stages must provide at least one day per season");
  const seasonIds = new Set();
  for (const [index, season] of config.seasons.entries()) {
    const owner = `seasons[${index}]`;
    assert(season && typeof season === "object" && !Array.isArray(season), `${owner} must be an object`);
    assert(nonEmptyString(season.id), `${owner}.id must be a non-empty string`);
    assert(!seasonIds.has(season.id), `${owner}.id must be unique`);
    seasonIds.add(season.id);
    assert(nonEmptyString(season.label), `${owner}.label must be a non-empty string`);
    assert(finiteNumber(season.weight) && season.weight > 0, `${owner}.weight must be greater than 0`);
    validateEffects(season.effects ?? {}, owner, knownIds);
  }

  const stageCounts = allocateSeasonStageCounts(config);
  let startStage = 1;
  const ranges = config.seasons.map((season, index) => {
    const range = {
      id: season.id,
      stageCount: stageCounts[index],
      startStage,
      endStage: startStage + stageCounts[index] - 1,
    };
    startStage = range.endStage + 1;
    return range;
  });
  assert(startStage === config.total_stages + 1, "season allocation must cover every stage exactly once");

  const scheduledIds = new Set();
  for (const [collectionName, entries] of [
    ["holidays", config.holidays ?? []],
    ["events", config.events ?? []],
  ]) {
    assert(Array.isArray(entries), `${collectionName} must be an array`);
    for (const [index, entry] of entries.entries()) {
      const owner = `${collectionName}[${index}]`;
      validateScheduledEntry(entry, owner, config, ranges, knownIds);
      assert(!scheduledIds.has(entry.id), `${owner}.id must be unique across scheduled entries`);
      scheduledIds.add(entry.id);
    }
  }
  return true;
}

function effectHasImpact(effects = {}) {
  return Number(effects.applicant_bonus ?? 0) !== 0
    || Object.values(effects.rank_multipliers ?? {}).some((value) => Number(value) !== 1)
    || Object.values(effects.species_multipliers ?? {}).some((value) => Number(value) !== 1);
}

function mergeEffects(target, effects, source) {
  target.applicantBonus += Number(effects?.applicant_bonus ?? 0);
  for (const [id, multiplier] of Object.entries(effects?.rank_multipliers ?? {})) {
    target.rankMultipliers[id] = (target.rankMultipliers[id] ?? 1) * multiplier;
  }
  for (const [id, multiplier] of Object.entries(effects?.species_multipliers ?? {})) {
    target.speciesMultipliers[id] = (target.speciesMultipliers[id] ?? 1) * multiplier;
  }
  target.sources.push({ ...source, hasEffect: effectHasImpact(effects) });
}

function finalizeMultiplierMap(values, owner) {
  return Object.fromEntries(Object.entries(values).map(([id, value]) => {
    assert(finiteNumber(value) && value > 0, `${owner}.${id} must remain finite and greater than 0`);
    const rounded = round6(value);
    assert(rounded > 0, `${owner}.${id} is too small after effect composition`);
    return [id, rounded];
  }));
}

function finalizeApplicantBonus(value) {
  assert(Number.isSafeInteger(value), "applicantBonus must remain a safe integer after effect composition");
  return value;
}

function matchesSchedule(entry, stageNumber, season) {
  if (Array.isArray(entry.stage_numbers)) return entry.stage_numbers.includes(stageNumber);
  if (entry.season_id !== season.id) return false;
  if (Array.isArray(entry.season_days)) return entry.season_days.includes(season.day);
  return entry.season_anchors.some((anchor) => seasonAnchorDay(anchor, season) === season.day);
}

function buildCampaignDayDescriptor(config, ranges, stageNumber) {
  assert(Number.isSafeInteger(stageNumber) && stageNumber >= 1 && stageNumber <= config.total_stages,
    "stageNumber must be within the configured campaign");
  const range = ranges.find((candidate) =>
    stageNumber >= candidate.startStage && stageNumber <= candidate.endStage
  );
  const seasonConfig = config.seasons[range.index];
  const season = {
    id: range.id,
    label: range.label,
    index: range.index,
    day: stageNumber - range.startStage + 1,
    stageCount: range.stageCount,
  };
  const dayOfWeek = ((stageNumber - 1) % config.week_length) + 1;
  const weekNumber = Math.floor((stageNumber - 1) / config.week_length) + 1;
  const isWeekend = config.weekend_days.includes(dayOfWeek);
  const holidays = (config.holidays ?? []).filter((entry) => matchesSchedule(entry, stageNumber, season));
  const events = (config.events ?? []).filter((entry) => matchesSchedule(entry, stageNumber, season));
  const demand = {
    applicantBonus: 0,
    rankMultipliers: {},
    speciesMultipliers: {},
    sources: [],
  };
  mergeEffects(demand, seasonConfig.effects ?? {}, {
    type: "SEASON",
    id: season.id,
    label: season.label,
  });
  if (isWeekend) {
    mergeEffects(demand, config.weekend_effects ?? {}, {
      type: "WEEKEND",
      id: `WEEKEND_DAY_${dayOfWeek}`,
      label: "주말",
    });
  }
  for (const holiday of holidays) {
    mergeEffects(demand, holiday.effects ?? {}, {
      type: "HOLIDAY",
      id: holiday.id,
      label: holiday.label,
    });
  }
  for (const event of events) {
    mergeEffects(demand, event.effects ?? {}, {
      type: "EVENT",
      id: event.id,
      label: event.label,
    });
  }
  const tags = [
    `SEASON:${season.id}`,
    ...(isWeekend ? ["WEEKEND"] : []),
    ...holidays.flatMap((entry) => [`HOLIDAY:${entry.id}`, ...(entry.tags ?? [])]),
    ...events.flatMap((entry) => [`EVENT:${entry.id}`, ...(entry.tags ?? [])]),
  ];
  return {
    stageNumber,
    weekNumber,
    dayOfWeek,
    weekdayId: CAMPAIGN_WEEKDAY_IDS[dayOfWeek - 1],
    isWeekend,
    season,
    holidayIds: holidays.map((entry) => entry.id),
    eventIds: events.map((entry) => entry.id),
    tags: [...new Set(tags)],
    demand: {
      ...demand,
      applicantBonus: finalizeApplicantBonus(demand.applicantBonus),
      rankMultipliers: finalizeMultiplierMap(demand.rankMultipliers, "rankMultipliers"),
      speciesMultipliers: finalizeMultiplierMap(demand.speciesMultipliers, "speciesMultipliers"),
    },
  };
}

export function campaignDayDescriptor(config, stageNumber, options = {}) {
  validateCampaignCalendar(config, options);
  return buildCampaignDayDescriptor(config, seasonRangesUnchecked(config), stageNumber);
}

export function compileCampaignCalendar(config, options = {}) {
  validateCampaignCalendar(config, options);
  const seasonRanges = seasonRangesUnchecked(config);
  const days = Array.from(
    { length: config.total_stages },
    (_, index) => buildCampaignDayDescriptor(config, seasonRanges, index + 1),
  );
  return {
    type: "COMPILED_CAMPAIGN_CALENDAR",
    calendarId: config.calendar_id ?? null,
    calendarVersion: config.calendar_version ?? null,
    totalStages: config.total_stages,
    weekLength: config.week_length,
    weekendDays: [...config.weekend_days],
    seasonRanges,
    days,
  };
}

export function validateCampaignCalendarPrefix(baseConfig, extendedConfig, options = {}) {
  const base = compileCampaignCalendar(baseConfig, options);
  const extended = compileCampaignCalendar(extendedConfig, options);
  assert(extended.totalStages > base.totalStages,
    "extended calendar must contain more stages than the base calendar");
  assert(extended.seasonRanges.length > base.seasonRanges.length,
    "extended calendar must add at least one season");
  assert(JSON.stringify(extended.seasonRanges.slice(0, base.seasonRanges.length))
    === JSON.stringify(base.seasonRanges),
  "extended calendar must preserve every base season boundary");
  assert(JSON.stringify(extended.days.slice(0, base.totalStages)) === JSON.stringify(base.days),
    "extended calendar must preserve every base day descriptor");
  return true;
}
