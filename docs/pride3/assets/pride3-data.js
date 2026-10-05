/* 第3回 DCLトーナメント PRIDE ─ 共有データ（仮：名前は？？？・日程は仮案） */
window.PRIDE3 = {
  status: "live",
  entryDeadline: "2026-10-18T23:59:00+09:00",
  announceDate: "10/19",
  finalDate: "2026-11-04T22:00:00+09:00",
  nights: ["10/25", "10/29", "11/1", "11/4"],
  champion: "",
  runnerUp: "",
  format: [
    { n: "2名",     br: "一本勝負",    bye: "—",    nights: "11/4" },
    { n: "3〜4名",  br: "4枠・2回戦",  bye: "4−N",  nights: "11/1 → 11/4" },
    { n: "5〜8名",  br: "8枠・3回戦",  bye: "8−N",  nights: "10/29 → 11/1 → 11/4" },
    { n: "9〜16名", br: "16枠・4回戦", bye: "16−N", nights: "10/25 → 10/29 → 11/1 → 11/4" }
  ],
  skeleton: [
    { name: "1回戦", n: 3 }, { name: "準々決勝", n: 4 }, { name: "準決勝", n: 2 }, { name: "決勝", n: 1 }
  ],
  entrants: Array.from({length: 11}, (_, i) => ({ seed: i + 1, name: "？？？" })),
  rounds: [
    { name: "1回戦", date: "10/25(日)", matches: [
      { id: "R1-1", at: "2026-10-25T22:00:00+09:00", a: { seed: 8,  name: "？？？" }, b: { seed: 9,  name: "？？？" }, winner: "" },
      { id: "R1-2", at: "2026-10-25T22:00:00+09:00", a: { seed: 10, name: "？？？" }, b: { seed: 11, name: "？？？" }, winner: "" },
      { id: "R1-3", at: "2026-10-25T22:00:00+09:00", a: { seed: 6,  name: "？？？" }, b: { seed: 7,  name: "？？？" }, winner: "" }
    ]},
    { name: "準々決勝", date: "10/29(木)", matches: [
      { id: "QF-1", at: "2026-10-29T22:00:00+09:00", src: [0], a: { seed: 2, name: "？？？", bye: true }, b: null, winner: "" },
      { id: "QF-2", at: "2026-10-29T22:00:00+09:00", src: [],  a: { seed: 4, name: "？？？", bye: true }, b: { seed: 5, name: "？？？", bye: true }, winner: "" },
      { id: "QF-3", at: "2026-10-29T22:00:00+09:00", src: [1], a: { seed: 3, name: "？？？", bye: true }, b: null, winner: "" },
      { id: "QF-4", at: "2026-10-29T22:00:00+09:00", src: [2], a: { seed: 1, name: "？？？", bye: true }, b: null, winner: "" }
    ]},
    { name: "準決勝", date: "11/1(日)", matches: [
      { id: "SF-1", at: "2026-11-01T22:00:00+09:00", src: [0, 1], a: null, b: null, winner: "" },
      { id: "SF-2", at: "2026-11-01T22:00:00+09:00", src: [2, 3], a: null, b: null, winner: "" }
    ]},
    { name: "決勝", date: "11/4(水)", matches: [
      { id: "FINAL", at: "2026-11-04T22:00:00+09:00", src: [0, 1], a: null, b: null, winner: "" }
    ]}
  ]
};
