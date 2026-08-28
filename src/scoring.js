import { evaluatePlacement } from "./rules.js";

function roundReputation(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function satisfactionReview(data, guestId, score) {
  const guest = data.indexes.guests[guestId];
  const rank = data.indexes.ranks[guest.rank];
  const satisfaction = score?.total ?? 0;
  const positiveThreshold = rank.positive_satisfaction_threshold;
  const reaction = satisfaction < 0
    ? "negative"
    : satisfaction >= positiveThreshold
      ? "positive"
      : "neutral";
  const reputationSignal = reaction === "positive" ? 1 : reaction === "negative" ? -1 : 0;
  const reputationImpact = roundReputation(reputationSignal * rank.reputation_influence);
  const positiveCauses = (score?.items ?? [])
    .filter((item) => item.points > 0)
    .sort((left, right) => right.points - left.points)
    .slice(0, 2)
    .map((item) => item.label);
  const negativeCauses = (score?.items ?? [])
    .filter((item) => item.points < 0)
    .sort((left, right) => left.points - right.points)
    .slice(0, 2)
    .map((item) => item.label);
  let headline = "무난한 숙박";
  let comment = "숙박 조건은 충족했지만 특별히 기억에 남을 요소는 없었다.";
  if (reaction === "positive") {
    headline = "기대 이상의 숙박";
    comment = positiveCauses.length
      ? `${positiveCauses.join(" · ")} 덕분에 좋은 기억이 남았다.`
      : "기대했던 수준보다 만족스러운 숙박이었다.";
  } else if (reaction === "negative") {
    headline = "기대에 못 미친 숙박";
    comment = negativeCauses.length
      ? `${negativeCauses.join(" · ")} 때문에 아쉬움이 남았다.`
      : "필수 조건은 지켜졌지만 기대한 수준에는 미치지 못했다.";
  } else if (positiveCauses.length) {
    comment = `${positiveCauses.join(" · ")}은 좋았지만 전체적으로는 무난한 숙박이었다.`;
  }
  return {
    guestId,
    reaction,
    headline,
    comment,
    satisfaction,
    positiveThreshold,
    reputationImpact,
    reputationInfluence: rank.reputation_influence,
    reputationInfluenceLabel: rank.reputation_influence_label,
    prestigeGap: score?.prestigeGap ?? 0,
    activeDislikeLabels: (score?.activeDislikes ?? []).map((item) => item.label),
    ignoredDislikeLabels: (score?.ignoredDislikes ?? []).map((item) => item.label),
  };
}

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
  const guestReviews = acceptedGuestIds.map((guestId) => (
    satisfactionReview(data, guestId, placement.guestScores[guestId])
  ));
  const satisfactionReputation = roundReputation(
    guestReviews.reduce((sum, review) => sum + review.reputationImpact, 0),
  );
  const rejectedReputation = rejectedGuestIds.reduce(
      (sum, guestId) => sum + (data.indexes.guests[guestId]?.reject_reputation ?? 0),
      0,
    );
  const canceledReputation = canceledGuestIds.reduce(
      (sum, guestId) => sum + (data.indexes.guests[guestId]?.cancel_reputation ?? 0),
      0,
    );
  const reputationDelta = roundReputation(
    satisfactionReputation + rejectedReputation + canceledReputation,
  );
  const normalizedSatisfaction = guestReviews.length
    ? guestReviews.reduce((sum, review) => (
      sum + Math.max(-1, Math.min(1, review.satisfaction / review.positiveThreshold))
    ), 0) / guestReviews.length
    : 0;
  const evaluationScore = Math.round(normalizedSatisfaction * 100);
  const thresholds = scenario.grade_thresholds
    ?? data.balance?.evaluation_grade_thresholds
    ?? { good: 50, excellent: 80 };
  let grade = "영업 완료";
  if (evaluationScore >= thresholds.excellent) grade = "훌륭한 운영";
  else if (evaluationScore >= thresholds.good) grade = "좋은 운영";

  return {
    ...placement,
    baseFees,
    tips,
    income,
    guestReviews,
    satisfactionReputation,
    rejectedReputation,
    canceledReputation,
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
