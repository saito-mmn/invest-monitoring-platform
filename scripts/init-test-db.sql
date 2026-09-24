-- テスト専用データベース。pytest は全テーブルを TRUNCATE するため、
-- 開発用の `invest` と同じDBを対象にしない。
CREATE DATABASE invest_test OWNER invest;
