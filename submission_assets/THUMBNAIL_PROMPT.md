# 베스페라 호텔 제출 썸네일 생성 기록

- 방식: Codex 내장 `imagegen`
- 용도: 게임 제출 폼의 16:9 권장 썸네일
- 참조 이미지:
  - `submission_video/assets/title.png`
  - `submission_video/assets/reservation5-ssr.png`
  - `submission_video/assets/night4-synergy.png`

## 최종 프롬프트

```text
Use case: ads-marketing
Asset type: final game submission thumbnail, 16:9 landscape, intended for a Korean game showcase
Primary request: Create a polished, immediately readable thumbnail for the fantasy hotel management game shown in the three reference screenshots. Treat all three inputs as visual references, not edit targets.
Scene/backdrop: dark luxurious hotel interior implied through a simplified three-floor room grid, warm black and charcoal backdrop, thin antique-gold framing
Subject: left 40 percent is an ivory invitation panel with the Vespera diamond mark and game title; right 60 percent shows a simplified hotel room grid and three overlapping guest cards, with one prominent gold SSR royal guest card and smaller blue R and purple SR cards, clearly suggesting choosing guests and assigning rooms
Style/medium: premium stylized game key art mixed with elegant editorial UI, faithful to the restrained visual language of the references, not photorealistic, not a raw screenshot
Composition/framing: strong 16:9 thumbnail composition; large readable title at left; room grid and cards at right; generous margins; clear focal hierarchy when viewed small
Lighting/mood: warm candlelit gold accents, subtle purple glow around the SSR card, mysterious but welcoming pre-opening invitation
Color palette: near-black #11100F, charcoal #1B1917, ivory #F0E7D7, warm gold #D9AD5B, restrained blue and purple rank accents
Text (verbatim): render exactly once each: "HOTEL VESPERA", "베스페라 호텔", "개장 전 초청 영업", and "SSR"
Typography: HOTEL VESPERA small spaced capitals; 베스페라 호텔 large elegant Korean serif; 개장 전 초청 영업 in one small gold badge; SSR on the royal card
Constraints: preserve the existing Vespera brand mood and diamond motif; all Korean text must be spelled exactly; no other words, numbers, UI labels, logos, trademarks, or watermark; no tiny body copy; no clutter; no cropped title; no character portrait that is absent from the references
Avoid: generic mobile-game splash art, casino imagery, neon overload, ornate fantasy clutter, illegible Korean, duplicated text, fake screenshots
```
