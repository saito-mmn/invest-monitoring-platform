import { describe, expect, it } from "vitest";
import { activeWeightTotal, compositionRatio } from "./weights";
import type { ThemeConstituent } from "@/types";

function constituent(
  overrides: Partial<ThemeConstituent> & { target_id: number },
): ThemeConstituent {
  return {
    target_key: `${overrides.target_id}.T`,
    target_name: `銘柄${overrides.target_id}`,
    target_type: "individual_stock",
    market: "JP",
    currency: "JPY",
    is_active: true,
    created_at: "2026-01-01 00:00:00",
    updated_at: "2026-01-01 00:00:00",
    basket_weight: 1,
    theme_rationale: null,
    relation_is_active: true,
    ...overrides,
  };
}

describe("activeWeightTotal", () => {
  it("有効な紐付けだけを合計する", () => {
    const rows = [
      constituent({ target_id: 1, basket_weight: 3 }),
      constituent({ target_id: 2, basket_weight: 2 }),
      constituent({ target_id: 3, basket_weight: 5, relation_is_active: false }),
    ];

    expect(activeWeightTotal(rows)).toBe(5);
  });

  it("ウェイト未設定は0として扱う", () => {
    const rows = [
      constituent({ target_id: 1, basket_weight: 2 }),
      constituent({ target_id: 2, basket_weight: null }),
    ];

    expect(activeWeightTotal(rows)).toBe(2);
  });

  it("構成銘柄が無ければ0を返す", () => {
    expect(activeWeightTotal([])).toBe(0);
  });
});

describe("compositionRatio", () => {
  it("有効な構成銘柄の合計を100%として配分する", () => {
    const rows = [
      constituent({ target_id: 1, basket_weight: 3 }),
      constituent({ target_id: 2, basket_weight: 2 }),
      constituent({ target_id: 3, basket_weight: 5, relation_is_active: false }),
    ];
    const total = activeWeightTotal(rows);

    expect(compositionRatio(rows[0], total)).toBe(60);
    expect(compositionRatio(rows[1], total)).toBe(40);
  });

  it("有効な構成銘柄の構成比は合計で100%になる", () => {
    const rows = [
      constituent({ target_id: 1, basket_weight: 0.25 }),
      constituent({ target_id: 2, basket_weight: 0.25 }),
      constituent({ target_id: 3, basket_weight: 0.25, relation_is_active: false }),
      constituent({ target_id: 4, basket_weight: 0.25, relation_is_active: false }),
    ];
    const total = activeWeightTotal(rows);

    const sum = rows
      .map((row) => compositionRatio(row, total) ?? 0)
      .reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(100);
  });

  it("無効な紐付けは構成比を持たない", () => {
    const row = constituent({ target_id: 3, basket_weight: 5, relation_is_active: false });

    expect(compositionRatio(row, 10)).toBeNull();
  });

  it("ウェイト未設定は構成比を持たない", () => {
    const row = constituent({ target_id: 1, basket_weight: null });

    expect(compositionRatio(row, 10)).toBeNull();
  });

  it("有効な構成銘柄のウェイトが全て0なら構成比を出さない", () => {
    const rows = [
      constituent({ target_id: 1, basket_weight: 0 }),
      constituent({ target_id: 2, basket_weight: 0 }),
    ];

    expect(compositionRatio(rows[0], activeWeightTotal(rows))).toBeNull();
  });
});
