"use client";
import { useState } from "react";
import { initDb, runBackfill, runDailyUpdate } from "@/lib/api";
import { PUBLIC_READ_ONLY } from "@/lib/runtime";

interface ActionState {
  loading: boolean;
  result: string | null;
  error: string | null;
}

const init: ActionState = { loading: false, result: null, error: null };

function ActionCard({
  title, description, label, state, onRun,
}: {
  title: string;
  description: string;
  label: string;
  state: ActionState;
  onRun: () => void;
}) {
  return (
    <div className="bg-white border rounded-lg p-5 space-y-3">
      <h3 className="font-semibold">{title}</h3>
      <p className="text-sm text-gray-500">{description}</p>
      <button
        onClick={onRun}
        disabled={state.loading}
        className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
      >
        {state.loading ? "実行中..." : label}
      </button>
      {state.result && <p className="text-green-600 text-sm">完了: {state.result}</p>}
      {state.error && <p className="text-red-600 text-sm">エラー: {state.error}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const [daily, setDaily] = useState<ActionState>(init);
  const [backfill, setBackfill] = useState<ActionState>(init);
  const [dbInit, setDbInit] = useState<ActionState>(init);

  const run = async (
    fn: () => Promise<{ status: string }>,
    set: React.Dispatch<React.SetStateAction<ActionState>>,
  ) => {
    set({ loading: true, result: null, error: null });
    try {
      const r = await fn();
      set({ loading: false, result: r.status, error: null });
    } catch (e) {
      set({ loading: false, result: null, error: (e as Error).message });
    }
  };

  if (PUBLIC_READ_ONLY) {
    return (
      <div className="rounded-lg border border-blue-100 bg-blue-50 p-6">
        <h1 className="text-xl font-semibold">公開デモ</h1>
        <p className="mt-2 text-sm text-blue-900">
          表示しているテーマ・銘柄・株価・財務はすべて架空のデモ用データです。
          市場データの利用条件を踏まえ、公開環境には実データを置いていません。
        </p>
        <p className="mt-2 text-sm text-blue-900">
          この環境では管理操作を無効化しています。データ更新は認証済みの管理環境から実行します。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">設定</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <ActionCard
          title="日次データ更新"
          description="最新の指標・銘柄価格データを取得してDBに保存します（バックグラウンド実行）"
          label="日次更新を実行"
          state={daily}
          onRun={() => run(runDailyUpdate, setDaily)}
        />
        <ActionCard
          title="バックフィル"
          description="過去データを一括取得します。初回セットアップ時や欠損データの補完に使用します（バックグラウンド実行）"
          label="バックフィルを実行"
          state={backfill}
          onRun={() => run(runBackfill, setBackfill)}
        />
        <ActionCard
          title="DB 初期化"
          description="schema.sql を適用してテーブルを作成します。既存データは保持されます（IF NOT EXISTS）"
          label="DB を初期化"
          state={dbInit}
          onRun={() => run(initDb, setDbInit)}
        />
      </div>
    </div>
  );
}
