from app.alerting.emit import emit, drain_queue, _queue


def setup_function():
    while not _queue.empty():
        _queue.get_nowait()


def test_emit_enqueues_event():
    emit("collision", "ip:10.0.0.1", {"reason": "duplicate"})
    items = drain_queue()
    assert len(items) == 1
    assert items[0].trigger_type == "collision"
    assert items[0].resource_key == "ip:10.0.0.1"
    assert items[0].context == {"reason": "duplicate"}


def test_drain_returns_empty_when_no_events():
    assert drain_queue() == []


def test_emit_is_thread_safe():
    import threading
    def producer():
        for i in range(100):
            emit("sync_error", f"sync:p{i}", {})
    threads = [threading.Thread(target=producer) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(drain_queue()) == 400
