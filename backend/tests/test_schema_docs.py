"""schema.sql とドキュメントの整合性を検査するテスト。

生成物が古い場合や、手書きのデータ定義書がスキーマとずれた場合に失敗する。
"""

from scripts import generate_schema_docs as docs


def test_generated_docs_are_up_to_date():
    """生成対象ファイルが schema.sql の現在の内容と一致する。"""
    schema = docs.parse_schema(docs.SCHEMA_PATH)
    for path, expected in docs.build_outputs(schema).items():
        actual = path.read_text(encoding="utf-8") if path.exists() else None
        assert actual == expected, (
            f"{path.relative_to(docs.REPO_ROOT)} が古い。"
            "`python scripts/generate_schema_docs.py` を実行すること"
        )


def test_data_dictionary_matches_schema():
    """手書きのデータ定義書がスキーマのテーブル・列・型と一致する。"""
    schema = docs.parse_schema(docs.SCHEMA_PATH)
    problems = docs.check_dictionary(schema)
    assert problems == [], "\n".join(problems)
