/**
 * テーマ構成銘柄のウェイト計算。
 *
 * `basket_weight` は絶対額ではなく相対値として入力されるため、表示上の構成比は
 * 合計に対する比率として求める。分母には有効な紐付けだけを含める。
 */
import type { ThemeConstituent } from "@/types";

/** 構成比の分母。テーマから外した銘柄を含めると現在の構成が薄まるため、有効な紐付けのみ合計する。 */
export function activeWeightTotal(constituents: ThemeConstituent[]): number {
  return constituents
    .filter((c) => c.relation_is_active)
    .reduce((sum, c) => sum + (c.basket_weight ?? 0), 0);
}

/**
 * 1銘柄の構成比を百分率で返す。算出できない場合は null。
 *
 * 無効な紐付け、ウェイト未設定、分母が0以下のいずれかに該当すると null になる。
 * 呼び出し側は null を「—」として表示する。
 */
export function compositionRatio(
  constituent: ThemeConstituent,
  activeTotal: number,
): number | null {
  if (!constituent.relation_is_active) return null;
  if (constituent.basket_weight === null) return null;
  if (activeTotal <= 0) return null;
  return (constituent.basket_weight / activeTotal) * 100;
}
