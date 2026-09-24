"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  getInvestmentTargets,
  getTheme,
  getThemeInvestmentTargets,
  removeThemeInvestmentTarget,
  upsertThemeInvestmentTarget,
} from "@/lib/api";
import { activeWeightTotal, compositionRatio } from "@/lib/weights";
import { PUBLIC_READ_ONLY } from "@/lib/runtime";
import type { InvestmentTarget, ThemeConstituent, ThemeDetail } from "@/types";

const STRATEGY_COLORS: Record<string, string> = {
  core: "bg-blue-100 text-blue-800",
  satellite: "bg-green-100 text-green-800",
  alternatives: "bg-purple-100 text-purple-800",
};

const TARGET_TYPE_LABELS: Record<string, string> = {
  individual_stock: "個別株",
  etf: "ETF",
  mutual_fund: "投資信託",
  reit: "REIT",
  bond: "債券",
  index: "指数",
  commodity: "商品",
};

function formatWeight(weight: number | null): string {
  return weight === null ? "—" : weight.toFixed(2);
}

export default function ThemeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const themeId = Number(use(params).id);
  const [theme, setTheme] = useState<ThemeDetail | null>(null);
  const [constituents, setConstituents] = useState<ThemeConstituent[]>([]);
  const [allTargets, setAllTargets] = useState<InvestmentTarget[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 追加フォームの入力
  const [newTargetId, setNewTargetId] = useState<number | "">("");
  const [newWeight, setNewWeight] = useState("1.0");
  
  const [newRationale, setNewRationale] = useState("");
  const reloadConstituents = () =>
    getThemeInvestmentTargets(themeId).then(setConstituents);

  useEffect(() => {
    getTheme(themeId).then(setTheme).catch((e) => setError(e.message));
    reloadConstituents().catch((e) => setError(e.message));
    if (!PUBLIC_READ_ONLY) {
      getInvestmentTargets(true).then(setAllTargets).catch((e) => setError(e.message));
    }
    // reloadConstituents は themeId からのみ導かれるため依存に含めない
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeId]);

  /** 紐付けの更新系は、成功したら一覧を取り直して表示を実体に合わせる。 */
  const mutate = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      await reloadConstituents();
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const addConstituent = () =>
    mutate(async () => {
      if (newTargetId === "") return;
      await upsertThemeInvestmentTarget(themeId, {
        target_id: newTargetId,
        basket_weight: Number(newWeight) || 0,
        rationale: newRationale.trim() || null,
      });
      setNewTargetId("");
      setNewWeight("1.0");
      setNewRationale("");
    });

  if (error) return <p className="text-red-600">{error}</p>;
  if (!theme) return <p className="text-gray-500">読み込み中...</p>;

  const activeTotalWeight = activeWeightTotal(constituents);
  // 既に有効な紐付けがある銘柄は選択肢から外す。無効な紐付けは行の「戻す」で復帰させる。
  const linkedActiveIds = new Set(
    constituents.filter((c) => c.relation_is_active).map((c) => c.target_id),
  );
  const selectableTargets = allTargets.filter((t) => !linkedActiveIds.has(t.target_id));

  return (
    <div className="space-y-8">
      <div>
        <Link href="/themes" className="text-sm text-gray-500 hover:underline">
          ← テーマ一覧
        </Link>
        <div className="flex items-center gap-3 mt-1">
          <h1 className="text-2xl font-bold">{theme.theme_name}</h1>
          <span
            className={`text-xs px-2 py-0.5 rounded font-bold ${
              STRATEGY_COLORS[theme.strategy_key] ?? ""
            }`}
          >
            {theme.strategy_name}
          </span>
          {!theme.is_active && (
            <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">停止中</span>
          )}
        </div>
        <p className="text-sm text-gray-500 font-mono mt-1">{theme.theme_key}</p>
      </div>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">投資仮説</h2>
        {theme.description ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{theme.description}</p>
        ) : (
          <p className="text-gray-500 text-sm">
            仮説が未記入です。なぜこのテーマに投資するのかを残しておくと、後から検証できます。
          </p>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-lg font-semibold">構成銘柄</h2>
          <span className="text-sm text-gray-500">{constituents.length}件</span>
        </div>
        {constituents.length === 0 ? (
          <p className="text-gray-500 text-sm">紐付けられた銘柄がありません。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-100 text-left">
                  <th className="px-3 py-2">銘柄</th>
                  <th className="px-3 py-2">種別</th>
                  <th className="px-3 py-2 text-right">ウェイト</th>
                  <th className="px-3 py-2 text-right">構成比</th>
                  <th className="px-3 py-2">採用理由</th>
                  {!PUBLIC_READ_ONLY && <th className="px-3 py-2 text-right">操作</th>}
                </tr>
              </thead>
              <tbody>
                {constituents.map((c) => (
                  <tr
                    key={c.target_id}
                    className={`border-t hover:bg-gray-50 ${
                      c.relation_is_active ? "" : "text-gray-400"
                    }`}
                  >
                    <td className="px-3 py-2">
                      <Link
                        href={`/investment-targets/${c.target_id}`}
                        className="hover:underline"
                      >
                        {c.target_name}
                      </Link>
                      <span className="text-gray-500 font-mono ml-2">{c.target_key}</span>
                    </td>
                    <td className="px-3 py-2">
                      {c.target_type ? TARGET_TYPE_LABELS[c.target_type] ?? c.target_type : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {formatWeight(c.basket_weight)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {compositionRatio(c, activeTotalWeight)?.toFixed(1).concat("%") ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{c.theme_rationale ?? "—"}</td>
                    {!PUBLIC_READ_ONLY && (
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {c.relation_is_active ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              mutate(() => removeThemeInvestmentTarget(themeId, c.target_id))
                            }
                            className="text-sm text-red-600 hover:underline disabled:opacity-50"
                          >
                            外す
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              mutate(() =>
                                upsertThemeInvestmentTarget(themeId, {
                                  target_id: c.target_id,
                                  basket_weight: c.basket_weight ?? 1,
                                  rationale: c.theme_rationale,
                                }),
                              )
                            }
                            className="text-sm text-blue-600 hover:underline disabled:opacity-50"
                          >
                            戻す
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-gray-500">
          構成比は<strong>有効な</strong>構成銘柄のウェイト合計に対する比率です。保有金額ではありません。
          テーマから外した銘柄はウェイトを記録として残しますが、構成比には含めません。
          {!PUBLIC_READ_ONLY && "「外す」は記録を消さず無効にします。"}
        </p>

        {!PUBLIC_READ_ONLY && <form
          onSubmit={(e) => {
            e.preventDefault();
            addConstituent();
          }}
          className="border rounded-lg p-4 space-y-3 bg-gray-50"
        >
          <h3 className="font-medium text-sm">銘柄を追加</h3>
          <div className="grid gap-3 sm:grid-cols-[2fr_1fr] items-end">
            <label className="space-y-1">
              <span className="block text-xs text-gray-600">銘柄</span>
              <select
                required
                value={newTargetId}
                onChange={(e) => setNewTargetId(e.target.value ? Number(e.target.value) : "")}
                className="w-full border rounded px-2 py-1 text-sm bg-white"
              >
                <option value="">選択してください</option>
                {selectableTargets.map((target) => (
                  <option key={target.target_id} value={target.target_id}>
                    {target.target_name}（{target.target_key}）
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="block text-xs text-gray-600">ウェイト</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={newWeight}
                onChange={(e) => setNewWeight(e.target.value)}
                className="w-full border rounded px-2 py-1 text-sm"
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="block text-xs text-gray-600">
              採用理由 — なぜこの銘柄をこのテーマに入れるのか
            </span>
            <textarea
              rows={2}
              value={newRationale}
              onChange={(e) => setNewRationale(e.target.value)}
              className="w-full border rounded px-2 py-1 text-sm"
              placeholder="後から仮説を検証できるように、判断の根拠を残します"
            />
          </label>
          <button
            type="submit"
            disabled={busy || newTargetId === ""}
            className="text-sm bg-gray-900 text-white rounded px-3 py-1.5 disabled:opacity-40"
          >
            追加
          </button>
        </form>}
      </section>
    </div>
  );
}
