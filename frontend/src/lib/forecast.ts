/**
 * 会社予想の改訂履歴の整形。
 *
 * APIは予想を含む開示を新しい順に返す。画面では「前回の予想からいくら変わったか」を
 * 見たいので、時系列で1つ前の開示と比較した差分を持たせる。
 */
import type { FinancialDisclosure } from "@/types";

/** 差分を付けた予想の改訂1件。 */
export interface ForecastRevision {
  disclosure: FinancialDisclosure;
  /** 1つ前の開示からの変化。比較できない場合は null。 */
  changes: {
    revenue: number | null;
    operatingIncome: number | null;
    netIncome: number | null;
    eps: number | null;
  };
}

function diff(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null) return null;
  return current - previous;
}

/**
 * 新しい順の開示列に、1つ前の開示との差分を付けて返す。
 *
 * 最も古い開示には比較対象が無いため、差分は全て null になる。
 * 一方の値が欠けている項目も比較しない（ゼロとして扱わない）。
 */
export function withForecastChanges(
  disclosures: FinancialDisclosure[],
): ForecastRevision[] {
  return disclosures.map((disclosure, index) => {
    // 入力は新しい順なので、時系列で1つ前は次の要素
    const previous = disclosures[index + 1] ?? null;
    return {
      disclosure,
      changes: {
        revenue: diff(disclosure.forecast_revenue, previous?.forecast_revenue ?? null),
        operatingIncome: diff(
          disclosure.forecast_operating_income,
          previous?.forecast_operating_income ?? null,
        ),
        netIncome: diff(disclosure.forecast_net_income, previous?.forecast_net_income ?? null),
        eps: diff(disclosure.forecast_eps, previous?.forecast_eps ?? null),
      },
    };
  });
}
