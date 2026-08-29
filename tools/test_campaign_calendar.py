from __future__ import annotations

import argparse
import json

from smoke_browser import CdpClient, debugger_target, wait_for


def run(base_url: str, debug_port: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Log.enable")
        client.command("Page.enable")
        client.command("Page.navigate", {"url": base_url})
        wait_for(client, "document.readyState === 'complete'")

        contracts = client.evaluate(
            """
            (async () => {
              const {
                validateCampaignCalendar,
                validateCampaignCalendarPrefix,
                campaignDayDescriptor,
                compileCampaignCalendar,
              } = await import('./src/campaign-calendar.js');
              const {
                loadGameData,
                createCampaignGreyboxData,
              } = await import('./src/data.js');

              const validationOptions = {
                rankIds: ['N', 'R', 'SR', 'SSR'],
                speciesIds: ['HUMAN', 'VAMPIRE', 'WITCH', 'DREAM_DEMON'],
              };

              const effects = (
                applicantBonus = 0,
                rankMultipliers = {},
                speciesMultipliers = {},
              ) => ({
                applicant_bonus: applicantBonus,
                rank_multipliers: rankMultipliers,
                species_multipliers: speciesMultipliers,
              });

              const seasons = [
                {
                  id: 'SPRING',
                  label: 'Spring',
                  weight: 1,
                  effects: effects(1, { R: 1.25 }, { HUMAN: 1.2 }),
                },
                {
                  id: 'SUMMER',
                  label: 'Summer',
                  weight: 1,
                  effects: effects(0, { SR: 1.1 }, { DREAM_DEMON: 1.25 }),
                },
                {
                  id: 'AUTUMN',
                  label: 'Autumn',
                  weight: 1,
                  effects: effects(-1, { N: 1.2 }, { WITCH: 1.1 }),
                },
                {
                  id: 'WINTER',
                  label: 'Winter',
                  weight: 1,
                  effects: effects(0, { SSR: 1.15 }, { VAMPIRE: 1.2 }),
                },
              ];

              const seasonEndEvents = seasons.map(season => ({
                id: `${season.id}_END_ANCHOR`,
                label: `${season.label} End`,
                season_id: season.id,
                season_anchors: [{ anchor: 'END', offset: 0 }],
                tags: ['SEASON_BOUNDARY'],
                effects: effects(),
              }));

              const config28 = {
                total_stages: 28,
                week_length: 7,
                weekend_days: [6, 7],
                weekend_effects: effects(5, { R: 1.2 }, { HUMAN: 1.1 }),
                seasons,
                holidays: [
                  {
                    id: 'SEVENTH_STAGE_HOLIDAY',
                    label: 'Seventh Stage Holiday',
                    stage_numbers: [7, 14, 21, 28],
                    tags: ['HOLIDAY', 'MARKET'],
                    effects: effects(2, { R: 1.5, N: 0.5 }, { HUMAN: 2 }),
                  },
                  {
                    id: 'SPRING_FAREWELL',
                    label: 'Spring Farewell',
                    season_id: 'SPRING',
                    season_days: [7],
                    tags: ['HOLIDAY', 'SEASON_END'],
                    effects: effects(4, { R: 2 }, { HUMAN: 0.5, VAMPIRE: 1.1 }),
                  },
                ],
                events: [
                  {
                    id: 'CHAPTER_SIGNAL',
                    label: 'Chapter Signal',
                    stage_numbers: [7],
                    tags: ['STORY', 'MARKET'],
                    effects: effects(3, { R: 0.8 }, { HUMAN: 1.25, VAMPIRE: 2 }),
                  },
                  {
                    id: 'WINTER_OPENING',
                    label: 'Winter Opening',
                    season_id: 'WINTER',
                    season_days: [1],
                    tags: ['STORY'],
                    effects: effects(),
                  },
                  ...seasonEndEvents,
                ],
              };

              const config30 = {
                ...config28,
                total_stages: 30,
                holidays: [],
                events: seasonEndEvents,
              };

              const compact = descriptor => ({
                stageNumber: descriptor.stageNumber,
                weekNumber: descriptor.weekNumber,
                dayOfWeek: descriptor.dayOfWeek,
                weekdayId: descriptor.weekdayId,
                isWeekend: descriptor.isWeekend,
                season: descriptor.season,
                holidayIds: descriptor.holidayIds,
                eventIds: descriptor.eventIds,
                tags: descriptor.tags,
                demand: descriptor.demand,
              });

              const boundaryStages = [1, 6, 7, 8, 14, 15, 21, 22, 28];
              const boundaries28 = Object.fromEntries(
                boundaryStages.map(stage => [
                  stage,
                  compact(campaignDayDescriptor(config28, stage, validationOptions)),
                ]),
              );
              const overlap = boundaries28[7];

              const compiled28 = compileCampaignCalendar(config28, validationOptions);
              const compiled30 = compileCampaignCalendar(config30, validationOptions);
              const compileMatchesSingles28 = compiled28.days.every((day, index) => (
                JSON.stringify(day) === JSON.stringify(
                  campaignDayDescriptor(config28, index + 1, validationOptions)
                )
              ));
              const compileMatchesSingles30 = compiled30.days.every((day, index) => (
                JSON.stringify(day) === JSON.stringify(
                  campaignDayDescriptor(config30, index + 1, validationOptions)
                )
              ));

              const anchorStages = (compiled, ids) => Object.fromEntries(ids.map(id => [
                id,
                compiled.days.filter(day => day.eventIds.includes(id)).map(day => day.stageNumber),
              ]));
              const anchorIds = seasonEndEvents.map(event => event.id);
              const anchorStages28 = anchorStages(compiled28, anchorIds);
              const anchorStages30 = anchorStages(compiled30, anchorIds);

              const all30 = Array.from(
                { length: config30.total_stages },
                (_, index) => campaignDayDescriptor(config30, index + 1, validationOptions),
              );
              const counts30 = Object.fromEntries(
                config30.seasons.map(season => [
                  season.id,
                  all30.filter(day => day.season.id === season.id).length,
                ]),
              );
              const transitions30 = all30
                .filter((day, index) => index === 0 || day.season.id !== all30[index - 1].season.id)
                .map(day => ({
                  stageNumber: day.stageNumber,
                  seasonId: day.season.id,
                  seasonIndex: day.season.index,
                  seasonDay: day.season.day,
                  stageCount: day.season.stageCount,
                }));
              const coverage30 = all30.map(day => ({
                stageNumber: day.stageNumber,
                seasonId: day.season.id,
                seasonDay: day.season.day,
                stageCount: day.season.stageCount,
              }));

              const deterministicBefore = JSON.stringify(config28);
              const deterministicA = campaignDayDescriptor(config28, 7, validationOptions);
              const deterministicB = campaignDayDescriptor(config28, 7, validationOptions);
              const deterministicAfter = JSON.stringify(config28);

              const formalBaseConfig = {
                ...config28,
                total_stages: 56,
                holidays: [],
                events: [],
              };
              const extendedSeason = {
                id: 'EXTENDED_SEASON',
                label: 'Extended Season',
                weight: 1,
                effects: effects(),
              };
              const formalTrueConfig = {
                ...formalBaseConfig,
                total_stages: 70,
                seasons: [...seasons, extendedSeason],
              };
              const formalBase = compileCampaignCalendar(formalBaseConfig, validationOptions);
              const formalTrue = compileCampaignCalendar(formalTrueConfig, validationOptions);
              const formalPrefixPreserved = formalBase.days.every((day, index) => (
                JSON.stringify(day) === JSON.stringify(formalTrue.days[index])
              ));
              const formalPrefixContract = validateCampaignCalendarPrefix(
                formalBaseConfig,
                formalTrueConfig,
                validationOptions,
              );

              const sourceData = await loadGameData();
              const actualCampaignData = createCampaignGreyboxData(sourceData);
              const actualCalendar = actualCampaignData.campaign.calendar;
              const actualValidationOptions = {
                rankIds: actualCampaignData.campaign.formal_rank_ids,
                speciesIds: actualCampaignData.campaign.formal_species.map(species => species.id),
              };
              const actualBaseCalendar = compileCampaignCalendar(
                actualCalendar.base_year,
                actualValidationOptions,
              );
              const actualTrueCalendar = compileCampaignCalendar(
                actualCalendar.true_extension,
                actualValidationOptions,
              );
              const compactRange = range => ({
                id: range.id,
                index: range.index,
                startStage: range.startStage,
                endStage: range.endStage,
                stageCount: range.stageCount,
              });
              const actualBaseRanges = actualBaseCalendar.seasonRanges.map(compactRange);
              const actualTrueRanges = actualTrueCalendar.seasonRanges.map(compactRange);
              const actualFirstFourRangesPreserved = (
                JSON.stringify(actualBaseRanges)
                === JSON.stringify(actualTrueRanges.slice(0, 4))
              );
              const actualFirst56DaysPreserved = actualBaseCalendar.days.every((day, index) => (
                JSON.stringify(day) === JSON.stringify(actualTrueCalendar.days[index])
              ));
              const actualWeekendDemand = Object.fromEntries([5, 6, 7].map(stage => {
                const day = campaignDayDescriptor(
                  actualCalendar.base_year,
                  stage,
                  actualValidationOptions,
                );
                return [stage, {
                  dayOfWeek: day.dayOfWeek,
                  weekdayId: day.weekdayId,
                  isWeekend: day.isWeekend,
                  applicantBonus: day.demand.applicantBonus,
                }];
              }));

              const numericConfig = (seasonMultiplier, eventMultiplier) => ({
                total_stages: 1,
                week_length: 7,
                weekend_days: [6, 7],
                seasons: [{
                  id: 'ONLY',
                  label: 'Only',
                  weight: 1,
                  effects: effects(0, { R: seasonMultiplier }),
                }],
                holidays: [],
                events: [{
                  id: 'NUMERIC_EVENT',
                  label: 'Numeric Event',
                  stage_numbers: [1],
                  effects: effects(0, { R: eventMultiplier }),
                }],
              });
              const applicantConfig = (seasonBonus, eventBonus) => ({
                total_stages: 1,
                week_length: 7,
                weekend_days: [6, 7],
                seasons: [{
                  id: 'ONLY',
                  label: 'Only',
                  weight: 1,
                  effects: effects(seasonBonus),
                }],
                holidays: [],
                events: [{
                  id: 'APPLICANT_EVENT',
                  label: 'Applicant Event',
                  stage_numbers: [1],
                  effects: effects(eventBonus),
                }],
              });
              const neutralMultiplierConfig = {
                ...applicantConfig(0, 0),
                seasons: [{
                  id: 'ONLY',
                  label: 'Only',
                  weight: 1,
                  effects: effects(0, { R: 1 }, { HUMAN: 1 }),
                }],
              };
              const neutralMultiplierDay = campaignDayDescriptor(
                neutralMultiplierConfig,
                1,
                validationOptions,
              );

              const rejects = callback => {
                try {
                  callback();
                  return false;
                } catch {
                  return true;
                }
              };

              const invalidCases = {
                nullConfig: null,
                zeroStages: { ...config28, total_stages: 0 },
                fractionalStages: { ...config28, total_stages: 28.5 },
                stagesAboveSafeInteger: {
                  ...config28,
                  total_stages: Number.MAX_SAFE_INTEGER + 1,
                },
                stagesAboveProductLimit: { ...config28, total_stages: 10_001 },
                zeroWeek: { ...config28, week_length: 0 },
                nonStandardWeek: { ...config28, week_length: 6, weekend_days: [5, 6] },
                weekendBelowRange: { ...config28, weekend_days: [0] },
                weekendAboveRange: { ...config28, weekend_days: [8] },
                duplicateWeekend: { ...config28, weekend_days: [6, 6] },
                nonStandardWeekend: { ...config28, weekend_days: [5, 6] },
                reversedWeekend: { ...config28, weekend_days: [7, 6] },
                calendarIdWithoutVersion: { ...config28, calendar_id: 'BAD' },
                calendarVersionWithoutId: { ...config28, calendar_version: 1 },
                noSeasons: { ...config28, seasons: [] },
                zeroSeasonWeight: {
                  ...config28,
                  seasons: config28.seasons.map((season, index) => (
                    index === 0 ? { ...season, weight: 0 } : season
                  )),
                },
                duplicateSeasonId: {
                  ...config28,
                  seasons: config28.seasons.map((season, index) => (
                    index === 1 ? { ...season, id: 'SPRING' } : season
                  )),
                },
                holidayWithoutSchedule: {
                  ...config28,
                  holidays: [{ id: 'BAD', label: 'Bad', effects: effects() }],
                },
                holidayWithBothSchedules: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    season_id: 'SPRING',
                    season_days: [1],
                    effects: effects(),
                  }],
                },
                holidayWrongSelectorType: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: '1',
                    effects: effects(),
                  }],
                },
                holidayWithHiddenWrongSelector: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    season_days: '1',
                    effects: effects(),
                  }],
                },
                holidayNullAnchorOffset: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    season_id: 'SPRING',
                    season_anchors: [{ anchor: 'END', offset: null }],
                    effects: effects(),
                  }],
                },
                holidayStageOutOfRange: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [29],
                    effects: effects(),
                  }],
                },
                holidayUnknownSeason: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    season_id: 'MONSOON',
                    season_days: [1],
                    effects: effects(),
                  }],
                },
                holidaySeasonDayOutOfRange: {
                  ...config28,
                  holidays: [{
                    id: 'BAD',
                    label: 'Bad',
                    season_id: 'SPRING',
                    season_days: [8],
                    effects: effects(),
                  }],
                },
                duplicateHolidayId: {
                  ...config28,
                  holidays: [
                    { id: 'SAME', label: 'One', stage_numbers: [1], effects: effects() },
                    { id: 'SAME', label: 'Two', stage_numbers: [2], effects: effects() },
                  ],
                },
                invalidApplicantBonus: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: { ...effects(), applicant_bonus: '1' },
                  }],
                },
                applicantBonusAboveSafeInteger: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: effects(Number.MAX_SAFE_INTEGER + 1),
                  }],
                },
                unknownRankMultiplier: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: effects(0, { UR: 1.1 }),
                  }],
                },
                unknownSpeciesMultiplier: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: effects(0, {}, { WEREWOLF: 1.1 }),
                  }],
                },
                zeroRankMultiplier: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: effects(0, { R: 0 }),
                  }],
                },
                negativeSpeciesMultiplier: {
                  ...config28,
                  events: [{
                    id: 'BAD',
                    label: 'Bad',
                    stage_numbers: [1],
                    effects: effects(0, {}, { HUMAN: -1 }),
                  }],
                },
              };

              const invalidRejected = Object.fromEntries(
                Object.entries(invalidCases).map(([name, config]) => {
                  try {
                    validateCampaignCalendar(config, validationOptions);
                    return [name, false];
                  } catch {
                    return [name, true];
                  }
                }),
              );
              const invalidStagesRejected = Object.fromEntries(
                [0, 29, 1.5, Number.MAX_SAFE_INTEGER + 1].map(stage => {
                  try {
                    campaignDayDescriptor(config28, stage, validationOptions);
                    return [String(stage), false];
                  } catch {
                    return [String(stage), true];
                  }
                }),
              );

              const compositionRejected = {
                overflowDescriptor: rejects(() => campaignDayDescriptor(
                  numericConfig(1e308, 1e308),
                  1,
                  validationOptions,
                )),
                overflowCompile: rejects(() => compileCampaignCalendar(
                  numericConfig(1e308, 1e308),
                  validationOptions,
                )),
                roundToZeroDescriptor: rejects(() => campaignDayDescriptor(
                  numericConfig(0.0001, 0.0001),
                  1,
                  validationOptions,
                )),
                roundToZeroCompile: rejects(() => compileCampaignCalendar(
                  numericConfig(0.0001, 0.0001),
                  validationOptions,
                )),
                applicantOverflowDescriptor: rejects(() => campaignDayDescriptor(
                  applicantConfig(Number.MAX_SAFE_INTEGER, 1),
                  1,
                  validationOptions,
                )),
                applicantOverflowCompile: rejects(() => compileCampaignCalendar(
                  applicantConfig(Number.MAX_SAFE_INTEGER, 1),
                  validationOptions,
                )),
                prefixDrift: rejects(() => validateCampaignCalendarPrefix(
                  formalBaseConfig,
                  { ...formalTrueConfig, weekend_effects: effects(1) },
                  validationOptions,
                )),
              };

              return {
                valid28: validateCampaignCalendar(config28, validationOptions),
                valid30: validateCampaignCalendar(config30, validationOptions),
                boundaries28,
                overlap,
                compiled28Meta: {
                  type: compiled28.type,
                  totalStages: compiled28.totalStages,
                  weekLength: compiled28.weekLength,
                  weekendDays: compiled28.weekendDays,
                },
                compileMatchesSingles28,
                compileMatchesSingles30,
                anchorStages28,
                anchorStages30,
                counts30,
                transitions30,
                coverage30,
                formalBaseRanges: formalBase.seasonRanges,
                formalTrueRanges: formalTrue.seasonRanges,
                formalPrefixPreserved,
                formalPrefixContract,
                actualCampaignCalendar: {
                  status: actualCalendar.status,
                  baseCalendarId: actualBaseCalendar.calendarId,
                  trueCalendarId: actualTrueCalendar.calendarId,
                  baseCalendarVersion: actualBaseCalendar.calendarVersion,
                  trueCalendarVersion: actualTrueCalendar.calendarVersion,
                  baseTotalStages: actualCalendar.base_year.total_stages,
                  trueTotalStages: actualCalendar.true_extension.total_stages,
                  baseWeekendDays: actualCalendar.base_year.weekend_days,
                  trueWeekendDays: actualCalendar.true_extension.weekend_days,
                  baseWeekendApplicantBonus:
                    actualCalendar.base_year.weekend_effects?.applicant_bonus,
                  trueWeekendApplicantBonus:
                    actualCalendar.true_extension.weekend_effects?.applicant_bonus,
                  baseRanges: actualBaseRanges,
                  trueRanges: actualTrueRanges,
                  firstFourRangesPreserved: actualFirstFourRangesPreserved,
                  first56DaysPreserved: actualFirst56DaysPreserved,
                  weekendDemand: actualWeekendDemand,
                  baseValid: validateCampaignCalendar(
                    actualCalendar.base_year,
                    actualValidationOptions,
                  ),
                  trueValid: validateCampaignCalendar(
                    actualCalendar.true_extension,
                    actualValidationOptions,
                  ),
                  prefixValid: validateCampaignCalendarPrefix(
                    actualCalendar.base_year,
                    actualCalendar.true_extension,
                    actualValidationOptions,
                  ),
                },
                neutralMultiplierSources: neutralMultiplierDay.demand.sources,
                deterministic: JSON.stringify(deterministicA) === JSON.stringify(deterministicB),
                inputUnchanged: deterministicBefore === deterministicAfter,
                invalidRejected,
                invalidStagesRejected,
                compositionRejected,
              };
            })()
            """
        )

        assert contracts["valid28"] is True, contracts
        assert contracts["valid30"] is True, contracts

        boundaries = contracts["boundaries28"]
        assert boundaries["1"]["weekNumber"] == 1
        assert boundaries["1"]["dayOfWeek"] == 1
        assert boundaries["1"]["weekdayId"] == "MONDAY"
        assert boundaries["1"]["isWeekend"] is False
        assert boundaries["1"]["season"] == {
            "id": "SPRING",
            "label": "Spring",
            "index": 0,
            "day": 1,
            "stageCount": 7,
        }
        assert boundaries["6"]["dayOfWeek"] == 6
        assert boundaries["6"]["weekdayId"] == "SATURDAY"
        assert boundaries["6"]["isWeekend"] is True
        assert boundaries["7"]["weekNumber"] == 1
        assert boundaries["7"]["dayOfWeek"] == 7
        assert boundaries["7"]["weekdayId"] == "SUNDAY"
        assert boundaries["7"]["isWeekend"] is True
        assert boundaries["7"]["season"]["id"] == "SPRING"
        assert boundaries["7"]["season"]["day"] == 7
        assert boundaries["8"]["weekNumber"] == 2
        assert boundaries["8"]["dayOfWeek"] == 1
        assert boundaries["8"]["weekdayId"] == "MONDAY"
        assert boundaries["8"]["season"] == {
            "id": "SUMMER",
            "label": "Summer",
            "index": 1,
            "day": 1,
            "stageCount": 7,
        }
        assert boundaries["15"]["season"]["id"] == "AUTUMN"
        assert boundaries["15"]["season"]["day"] == 1
        assert boundaries["22"]["season"]["id"] == "WINTER"
        assert boundaries["22"]["season"]["day"] == 1
        assert boundaries["28"]["weekNumber"] == 4
        assert boundaries["28"]["dayOfWeek"] == 7
        assert boundaries["28"]["weekdayId"] == "SUNDAY"
        assert boundaries["28"]["season"]["id"] == "WINTER"
        assert boundaries["28"]["season"]["day"] == 7

        overlap = contracts["overlap"]
        assert overlap["holidayIds"] == ["SEVENTH_STAGE_HOLIDAY", "SPRING_FAREWELL"], overlap
        assert overlap["eventIds"] == ["CHAPTER_SIGNAL", "SPRING_END_ANCHOR"], overlap
        assert overlap["tags"] == [
            "SEASON:SPRING",
            "WEEKEND",
            "HOLIDAY:SEVENTH_STAGE_HOLIDAY",
            "HOLIDAY",
            "MARKET",
            "HOLIDAY:SPRING_FAREWELL",
            "SEASON_END",
            "EVENT:CHAPTER_SIGNAL",
            "STORY",
            "EVENT:SPRING_END_ANCHOR",
            "SEASON_BOUNDARY",
        ], overlap
        demand = overlap["demand"]
        assert demand["applicantBonus"] == 15, demand
        assert abs(demand["rankMultipliers"]["R"] - 3.6) < 1e-9, demand
        assert abs(demand["rankMultipliers"]["N"] - 0.5) < 1e-9, demand
        assert abs(demand["speciesMultipliers"]["HUMAN"] - 1.65) < 1e-9, demand
        assert abs(demand["speciesMultipliers"]["VAMPIRE"] - 2.2) < 1e-9, demand
        source_json = json.dumps(demand["sources"], ensure_ascii=False)
        for source_id in [
            "SPRING",
            "WEEKEND_DAY_7",
            "SEVENTH_STAGE_HOLIDAY",
            "SPRING_FAREWELL",
            "CHAPTER_SIGNAL",
            "SPRING_END_ANCHOR",
        ]:
            assert source_id in source_json, (source_id, demand["sources"])

        assert contracts["compiled28Meta"] == {
            "type": "COMPILED_CAMPAIGN_CALENDAR",
            "totalStages": 28,
            "weekLength": 7,
            "weekendDays": [6, 7],
        }, contracts["compiled28Meta"]
        assert contracts["compileMatchesSingles28"] is True, contracts
        assert contracts["compileMatchesSingles30"] is True, contracts
        assert contracts["anchorStages28"] == {
            "SPRING_END_ANCHOR": [7],
            "SUMMER_END_ANCHOR": [14],
            "AUTUMN_END_ANCHOR": [21],
            "WINTER_END_ANCHOR": [28],
        }, contracts["anchorStages28"]
        assert contracts["anchorStages30"] == {
            "SPRING_END_ANCHOR": [8],
            "SUMMER_END_ANCHOR": [16],
            "AUTUMN_END_ANCHOR": [23],
            "WINTER_END_ANCHOR": [30],
        }, contracts["anchorStages30"]

        assert contracts["counts30"] == {
            "SPRING": 8,
            "SUMMER": 8,
            "AUTUMN": 7,
            "WINTER": 7,
        }, contracts["counts30"]
        assert contracts["transitions30"] == [
            {"stageNumber": 1, "seasonId": "SPRING", "seasonIndex": 0, "seasonDay": 1, "stageCount": 8},
            {"stageNumber": 9, "seasonId": "SUMMER", "seasonIndex": 1, "seasonDay": 1, "stageCount": 8},
            {"stageNumber": 17, "seasonId": "AUTUMN", "seasonIndex": 2, "seasonDay": 1, "stageCount": 7},
            {"stageNumber": 24, "seasonId": "WINTER", "seasonIndex": 3, "seasonDay": 1, "stageCount": 7},
        ], contracts["transitions30"]
        coverage = contracts["coverage30"]
        assert [item["stageNumber"] for item in coverage] == list(range(1, 31)), coverage
        for season_id, expected_count in contracts["counts30"].items():
            season_days = [item["seasonDay"] for item in coverage if item["seasonId"] == season_id]
            assert season_days == list(range(1, expected_count + 1)), (season_id, season_days)
            assert all(
                item["stageCount"] == expected_count
                for item in coverage
                if item["seasonId"] == season_id
            )

        assert contracts["formalBaseRanges"] == [
            {"id": "SPRING", "label": "Spring", "index": 0, "startStage": 1, "endStage": 14, "stageCount": 14},
            {"id": "SUMMER", "label": "Summer", "index": 1, "startStage": 15, "endStage": 28, "stageCount": 14},
            {"id": "AUTUMN", "label": "Autumn", "index": 2, "startStage": 29, "endStage": 42, "stageCount": 14},
            {"id": "WINTER", "label": "Winter", "index": 3, "startStage": 43, "endStage": 56, "stageCount": 14},
        ], contracts["formalBaseRanges"]
        assert contracts["formalTrueRanges"] == [
            {"id": "SPRING", "label": "Spring", "index": 0, "startStage": 1, "endStage": 14, "stageCount": 14},
            {"id": "SUMMER", "label": "Summer", "index": 1, "startStage": 15, "endStage": 28, "stageCount": 14},
            {"id": "AUTUMN", "label": "Autumn", "index": 2, "startStage": 29, "endStage": 42, "stageCount": 14},
            {"id": "WINTER", "label": "Winter", "index": 3, "startStage": 43, "endStage": 56, "stageCount": 14},
            {"id": "EXTENDED_SEASON", "label": "Extended Season", "index": 4, "startStage": 57, "endStage": 70, "stageCount": 14},
        ], contracts["formalTrueRanges"]
        assert contracts["formalPrefixPreserved"] is True, contracts
        assert contracts["formalPrefixContract"] is True, contracts

        actual = contracts["actualCampaignCalendar"]
        assert actual["status"] == "PROVISIONAL", actual
        assert actual["baseCalendarId"] == "CAMPAIGN_BASE_YEAR", actual
        assert actual["trueCalendarId"] == "CAMPAIGN_TRUE_EXTENSION", actual
        assert actual["baseCalendarVersion"] == 1, actual
        assert actual["trueCalendarVersion"] == 1, actual
        assert actual["baseTotalStages"] == 56, actual
        assert actual["trueTotalStages"] == 70, actual
        assert actual["baseWeekendDays"] == [6, 7], actual
        assert actual["trueWeekendDays"] == [6, 7], actual
        assert actual["baseWeekendApplicantBonus"] == 1, actual
        assert actual["trueWeekendApplicantBonus"] == 1, actual
        assert actual["baseValid"] is True, actual
        assert actual["trueValid"] is True, actual
        assert actual["prefixValid"] is True, actual
        assert actual["baseRanges"] == [
            {"id": "SPRING", "index": 0, "startStage": 1, "endStage": 14, "stageCount": 14},
            {"id": "SUMMER", "index": 1, "startStage": 15, "endStage": 28, "stageCount": 14},
            {"id": "AUTUMN", "index": 2, "startStage": 29, "endStage": 42, "stageCount": 14},
            {"id": "WINTER", "index": 3, "startStage": 43, "endStage": 56, "stageCount": 14},
        ], actual["baseRanges"]
        assert actual["trueRanges"] == [
            {"id": "SPRING", "index": 0, "startStage": 1, "endStage": 14, "stageCount": 14},
            {"id": "SUMMER", "index": 1, "startStage": 15, "endStage": 28, "stageCount": 14},
            {"id": "AUTUMN", "index": 2, "startStage": 29, "endStage": 42, "stageCount": 14},
            {"id": "WINTER", "index": 3, "startStage": 43, "endStage": 56, "stageCount": 14},
            {"id": "TRUE_EXTENSION_SEASON", "index": 4, "startStage": 57, "endStage": 70, "stageCount": 14},
        ], actual["trueRanges"]
        assert actual["firstFourRangesPreserved"] is True, actual
        assert actual["first56DaysPreserved"] is True, actual
        assert actual["weekendDemand"] == {
            "5": {
                "dayOfWeek": 5,
                "weekdayId": "FRIDAY",
                "isWeekend": False,
                "applicantBonus": 0,
            },
            "6": {
                "dayOfWeek": 6,
                "weekdayId": "SATURDAY",
                "isWeekend": True,
                "applicantBonus": 1,
            },
            "7": {
                "dayOfWeek": 7,
                "weekdayId": "SUNDAY",
                "isWeekend": True,
                "applicantBonus": 1,
            },
        }, actual["weekendDemand"]

        assert contracts["neutralMultiplierSources"] == [
            {"type": "SEASON", "id": "ONLY", "label": "Only", "hasEffect": False},
            {"type": "EVENT", "id": "APPLICANT_EVENT", "label": "Applicant Event", "hasEffect": False},
        ], contracts["neutralMultiplierSources"]

        assert contracts["deterministic"] is True, contracts
        assert contracts["inputUnchanged"] is True, contracts
        assert all(contracts["invalidRejected"].values()), contracts["invalidRejected"]
        assert all(contracts["invalidStagesRejected"].values()), contracts["invalidStagesRejected"]
        assert all(contracts["compositionRejected"].values()), contracts["compositionRejected"]

        exception_events = [
            event
            for event in client.events
            if event.get("method") in {"Runtime.exceptionThrown", "Log.entryAdded"}
            and (
                event.get("method") == "Runtime.exceptionThrown"
                or event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        if exception_events:
            raise AssertionError(f"Browser errors detected: {exception_events}")

        return {
            "status": "PASS",
            "calendar": "COMPRESSED_STAGE_CALENDAR",
            "stages_28": {
                "season_counts": {season_id: 7 for season_id in ["SPRING", "SUMMER", "AUTUMN", "WINTER"]},
                "weekend_days": [6, 7],
            },
            "stages_30": {
                "season_counts": contracts["counts30"],
                "transitions": contracts["transitions30"],
            },
            "season_end_anchors": {
                "stages_28": contracts["anchorStages28"],
                "stages_30": contracts["anchorStages30"],
            },
            "formal_extension": {
                "base_stages": 56,
                "true_stages": 70,
                "prefix_preserved": contracts["formalPrefixPreserved"],
            },
            "actual_campaign_calendar": {
                "status": actual["status"],
                "base_stages": actual["baseTotalStages"],
                "true_stages": actual["trueTotalStages"],
                "first_56_days_preserved": actual["first56DaysPreserved"],
                "weekend_applicant_bonus": actual["baseWeekendApplicantBonus"],
            },
            "overlap_stage_7": {
                "holidays": overlap["holidayIds"],
                "events": overlap["eventIds"],
                "applicant_bonus": demand["applicantBonus"],
                "rank_multipliers": demand["rankMultipliers"],
                "species_multipliers": demand["speciesMultipliers"],
            },
            "invalid_cases": (
                len(contracts["invalidRejected"])
                + len(contracts["invalidStagesRejected"])
                + len(contracts["compositionRejected"])
            ),
            "deterministic": contracts["deterministic"],
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8767/index.html")
    parser.add_argument("--debug-port", type=int, default=9230)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
