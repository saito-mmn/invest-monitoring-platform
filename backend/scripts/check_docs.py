"""ドキュメントの機械的な破綻を検出する。

このプロジェクトはドキュメントが多く、手作業の確認では次の2種類を取りこぼす。

1. **リンク切れ** — ファイルを移動・削除したときに残る参照
2. **実装と矛盾する語** — 移行や設計変更のあとに残る古い用語

どちらも「読めば分かる」が「読まないと分からない」ため、CIで落とす。
スキーマとデータ定義書の整合は `generate_schema_docs.py --check` が担当する。

使い方:
    python backend/scripts/check_docs.py
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 検査対象。docs配下に加えて、入口となるファイルを含める。
TARGET_GLOBS = ("docs/**/*.md", "README.md", ".claude/CLAUDE.md")

# 実装と矛盾する語。移行や設計変更で意味が変わったものを、理由つきで登録する。
# 経緯として言及してよい箇所は ALLOWED_CONTEXT で除外する。
FORBIDDEN_TERMS: dict[str, str] = {
    "PRAGMA": "SQLite固有。PostgreSQLへ移行済み",
    "AUTOINCREMENT": "SQLite固有。`GENERATED ALWAYS AS IDENTITY` を使う",
    "canonical_db.py": "GCS同期の暫定スクリプト。PostgreSQL移行で廃止済み",
    "snapshot_db.py": "SQLiteスナップショット生成。PostgreSQL移行で廃止済み",
    "db_bootstrap.py": "起動時のGCS取得。PostgreSQL移行で廃止済み",
    "docs/diagrams/": "旧フォルダ構成。architecture / data へ再編済み",
    "docs/database/": "旧フォルダ構成。data へ再編済み",
    "docs/references/": "旧フォルダ構成。data/sources へ再編済み",
    "docs/traceability/": "旧フォルダ構成。data/sources/<取得元>/ へ再編済み",
    "docs/operations/": "旧フォルダ構成。infrastructure へ再編済み",
}

# 移行の経緯として言及してよい文脈。行内にこれを含むなら見逃す。
ALLOWED_CONTEXT = (
    "LEGACY_SQLITE_PATH",
    "旧SQLite",
    "db-import",
    "SQLiteからPostgreSQL",
    "GCS SQLite",
)

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def target_files() -> list[Path]:
    """検査対象のMarkdownを返す。"""
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(pattern)))
    return files


def broken_links(path: Path) -> list[str]:
    """解決できないリンク先を返す。外部URLとアンカーのみの参照は対象外。"""
    problems = []
    for target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # 同じファイル内のアンカーを落として実体だけ見る
        relative = target.split("#", 1)[0]
        if not relative:
            continue
        if not (path.parent / relative).exists():
            problems.append(relative)
    return problems


def forbidden_terms(path: Path) -> list[tuple[int, str, str]]:
    """実装と矛盾する語を、行番号つきで返す。"""
    problems = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if any(allowed in line for allowed in ALLOWED_CONTEXT):
            continue
        for term, reason in FORBIDDEN_TERMS.items():
            if term in line:
                problems.append((number, term, reason))
    return problems


def main() -> int:
    link_problems: list[str] = []
    term_problems: list[str] = []

    for path in target_files():
        shown = path.relative_to(REPO_ROOT)
        for target in broken_links(path):
            link_problems.append(f"  {shown} → {target}")
        for number, term, reason in forbidden_terms(path):
            term_problems.append(f"  {shown}:{number} 「{term}」— {reason}")

    if link_problems:
        print("リンク切れ:")
        print("\n".join(link_problems))
    if term_problems:
        print("実装と矛盾する語:")
        print("\n".join(term_problems))
        print("\n  経緯として言及する必要がある場合は check_docs.py の ALLOWED_CONTEXT へ追加する")

    if link_problems or term_problems:
        return 1
    print(f"ドキュメント {len(target_files())} 件を検査。問題ありません")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
