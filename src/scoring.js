import { evaluatePlacement } from "./rules.js";

export function calculateNightResult(
  data,
  scenario,
  acceptedGuestIds,
  rejectedGuestIds,
  placements,
  facilityId,
  options = {},
) {
  const canceledGuestIds = options.canceledGuestIds ?? [];
  const placement = evaluatePlacement(data, acceptedGuestIds, placements, facilityId);
  const baseFees = acceptedGuestIds.reduce(
    (sum, guestId) => sum + data.indexes.guests[guestId].base_fee,
    0,
  );
  const income = baseFees + placement.placementScore;
  const reputationDelta =
    acceptedGuestIds.reduce(
      (sum, guestId) => sum + data.indexes.guests[guestId].satisfied_reputation,
      0,
    ) +
    rejectedGuestIds.reduce(
      (sum, guestId) => sum + data.indexes.guests[guestId].reject_reputation,
      0,
    ) +
    canceledGuestIds.reduce(
      (sum, guestId) => sum + data.indexes.guests[guestId].cancel_reputation,
      0,
    );
  const evaluationScore =
    placement.placementScore + 2 * reputationDelta + Math.floor(income / 5);
  const facilityKey = facilityId ?? "NONE";
  const maxPreference = scenario.validated_max_preference[facilityKey];
  const maxEvaluation = scenario.validated_max_evaluation[facilityKey];
  const goodThreshold = Math.ceil(maxEvaluation * 0.75);
  let grade = "영업 완료";
  if (evaluationScore >= maxEvaluation) grade = "훌륭한 운영";
  else if (evaluationScore >= goodThreshold) grade = "좋은 운영";

  return {
    ...placement,
    baseFees,
    income,
    reputationDelta,
    evaluationScore,
    maxPreference,
    maxEvaluation,
    goodThreshold,
    grade,
    acceptedGuestIds: [...acceptedGuestIds],
    rejectedGuestIds: [...rejectedGuestIds],
    canceledGuestIds: [...canceledGuestIds],
    placements: { ...placements },
    facilityId,
    emergencyReport: options.emergencyReport ?? null,
  };
}
