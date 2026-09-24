import Link from "next/link";
import { PUBLIC_READ_ONLY } from "@/lib/runtime";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">投資データ基盤</h1>
      <p className="text-gray-600">戦略・テーマ・投資対象と、株価・財務データを確認できます。</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/themes" className="rounded-lg border bg-white p-5 hover:border-blue-500">
          <h2 className="font-semibold">テーマ</h2>
          <p className="mt-1 text-sm text-gray-500">戦略別のテーマと投資対象を確認する</p>
        </Link>
        <Link href="/investment-targets" className="rounded-lg border bg-white p-5 hover:border-blue-500">
          <h2 className="font-semibold">投資対象</h2>
          <p className="mt-1 text-sm text-gray-500">銘柄・ETF等の市場データを確認する</p>
        </Link>
      </div>
      {/* 読み取り専用モードでは設定画面への導線が無いため、公開デモの前提はここで説明する。 */}
      {PUBLIC_READ_ONLY && (
        <section className="rounded-lg border border-blue-100 bg-blue-50 p-5">
          <h2 className="font-semibold text-blue-900">このデモについて</h2>
          <p className="mt-2 text-sm text-blue-900">
            表示しているテーマ・銘柄・株価・財務は<strong>すべて架空のデモ用データ</strong>です。
            市場データの利用条件が第三者への提供を禁じているため、公開環境には実データを置かず、
            架空データだけを持つ別のデータベースを参照しています。
          </p>
          <p className="mt-2 text-sm text-blue-900">
            実データを扱う環境は非公開で、公開側とデータ・認証情報・データベースを共有しません。
            両者は同じスキーマとAPIを使うため、画面の挙動は実環境と同じです。
          </p>
          <p className="mt-2 text-sm text-blue-900">
            この環境は閲覧のみ可能です。更新系のAPIは実装済みですが、
            公開環境ではHTTPの入口とデータベースの権限の両方で書き込みを拒否しています。
          </p>
        </section>
      )}
    </div>
  );
}
