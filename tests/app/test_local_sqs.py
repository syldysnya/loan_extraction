from app.local_sqs import LocalSQS


def _ignore(body: str) -> None:
    pass


def test_receives_oldest_first(queue):
    queue.send("first")
    queue.send("second")

    assert queue.receive(on_dead_letter=_ignore).body == "first"


def test_received_message_is_hidden_until_visibility_timeout(tmp_path):
    queue = LocalSQS(str(tmp_path / "q"), visibility_timeout_s=60, max_receive_count=3)
    queue.send("body")

    assert queue.receive(on_dead_letter=_ignore) is not None
    assert queue.receive(on_dead_letter=_ignore) is None


def test_delete_removes_message(queue):
    queue.send("body")
    received = queue.receive(on_dead_letter=_ignore)

    queue.delete(received.receipt_handle)

    assert queue.receive(on_dead_letter=_ignore) is None


def test_moves_to_dlq_after_max_receives(queue):
    dead: list[str] = []
    queue.send("body")

    for _ in range(3):
        assert queue.receive(on_dead_letter=dead.append) is not None
    assert queue.receive(on_dead_letter=dead.append) is None

    assert dead == ["body"]
    assert len(list(queue.dlq.glob("*.json"))) == 1


def test_redrive_moves_only_kept_messages_with_reset_count(queue):
    for body in ["keep", "skip"]:
        queue.send(body)
        for _ in range(4):
            queue.receive(on_dead_letter=_ignore)

    assert queue.redrive(keep=lambda body: body == "keep") == ["keep"]
    assert queue.receive(on_dead_letter=_ignore).body == "keep"  # visible again, count reset
    assert len(list(queue.dlq.glob("*.json"))) == 1
