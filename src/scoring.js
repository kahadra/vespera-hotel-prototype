import { evaluatePlacement } from "./rules.js";

export function calculateNightResult(
  data,
  scenario,
  acceptedGuestIds,
  rejectedGuestIds,
  placements,
  hotelContext = {},
  options = {},
) {
  const canceledGuestIds = options.canceledGuestIds ?? [];
  const placement = evaluatePlacement(data, acceptedGuestIds, placements, hotelContext);
  const baseFees = acceptedGuestIds.reduce(
    (sum, guestId) => sum + (data.indexes.guests[guestId]?.base_fee ?? 0),
    0,
  );
  const tips = Math.max(0, placement.placementScore);
  const income = baseFees + tips;
  const reputationDelta =
    acceptedGuestIds.reduce(
      (sum, guestId) => sum + (data.indexes.guests[guestId]?.satisfied_reputation ?? 0),
      0,
    )
    + rejectedGuestIds.reduce(
      (sum, guestId) => sum + (data.indexes.guests[guestId]?.reject_reputation ?? 0),
      0,
    )
    + canceledGuestIds.reduce(
      (sum, guestId) => sum + (data.indexes.guests[guestId]?.cancel_reputation ?? 0),
      0,
    );
  const evaluationScore = placement.placementScore + 2 * reputationDelta + Math.floor(income / 5);
  const thresholds = scenario.grade_thresholds ?? { good: 20, excellent: 34 };
  let grade = "영업 완료";
  if (evaluationScore >= thresholds.excellent) grade = "훌륭한 운영";
  else if (evaluationScore >= thresholds.good) grade = "좋은 운영";

  return {
    ...placement,
    baseFees,
    tips,
    income,
    reputationDelta,
    evaluationScore,
    grade,
    acceptedGuestIds: [...acceptedGuestIds],
    rejectedGuestIds: [...rejectedGuestIds],
    canceledGuestIds: [...canceledGuestIds],
    placements: { ...placements },
    facilityIds: [...(hotelContext.ownedFacilityIds ?? [])],
    emergencyReport: options.emergencyReport ?? null,
  };
}
