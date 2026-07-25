from __future__ import annotations

import telegram_run_summary_after_sync as telegram


def test_persistent_text_uses_separate_id_ledger(tmp_path, monkeypatch) -> None:
    (tmp_path / "telegram_credentials.txt").write_text(
        "token=test\nchat_id=1\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        telegram, "_send_message", lambda token, chat_id, message: 12345
    )
    assert telegram.send_persistent_text(str(tmp_path), "persist")
    assert not (tmp_path / telegram.TELEGRAM_MESSAGE_IDS_FILE).exists()
    persistent = (
        tmp_path / telegram.TELEGRAM_PERSISTENT_MESSAGE_IDS_FILE
    ).read_text(encoding="utf-8")
    assert persistent.strip() == "12345"
