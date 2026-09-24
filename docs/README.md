# ドキュメント

公開しているのは**設計判断・データ契約・再現手順**の3種類です。
実行ログ、調査メモ、運用Runbookはリポジトリに含めていません。

## 読み方

### 採用・コードレビュー

1. [ルートREADME](../README.md)で目的、実装範囲、技術スタックを確認
2. [アーキテクチャ](architecture.md)でデータフロー、実行環境、権限境界を確認
3. [データ層の設計原則](data/design-principles.md)でFactと判断ロジックの分離を確認
4. [ER図](data/er-diagram.md)と[データ定義書](data/schema-data-dictionary.md)で物理実装へ降りる

### ローカルで再現

1. [開発ガイド](development.md)でPostgreSQL、Backend、Frontendを起動
2. 公開APIと同じread-only設定を使う場合は`DATABASE_READ_ONLY=true`で確認
3. スキーマ変更時は生成文書とデータ定義書の整合検査を実行

## 文書ごとの責務

同じ情報を複数の文書で管理しないため、質問ごとの正本を次のように分けます。

| 確認したいこと | 正本 |
|---|---|
| データフロー、実行環境、権限、コード責務 | [アーキテクチャ](architecture.md) |
| MasterからOutcomeまでの論理的な境界 | [データ層の設計原則](data/design-principles.md) |
| 列の意味、粒度、単位、運用ルール | [データ定義書](data/schema-data-dictionary.md) |
| 現在の型、制約、キー | [構造リファレンス](data/schema-reference.md)（自動生成） |
| 現在のテーブル間関係 | [ER図](data/er-diagram.md)（自動生成） |
| 外部データの採用元、保存、再配布、失敗時動作 | [取得元と利用方針](data/sources.md) |
| 起動、テスト、文書生成のコマンド | [開発ガイド](development.md) |

## 更新のルール

- **構造の記述は自動生成します。** `schema-reference.md` とER図は
  `backend/scripts/generate_schema_docs.py` が Alembic migration から生成するため、直接編集しません。
- **意味づけは手で書き、CIで検査します。** データ定義書とスキーマの食い違いは
  `generate_schema_docs.py --check` が検出します。
- **リンク切れと古い用語もCIで検出します**（`backend/scripts/check_docs.py`）。
