"""
EventBus - 事件总线
模块间通过事件通信，解耦所有组件。
"""
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
from queue import Queue, Empty
from enum import Enum

logger = logging.getLogger("EventBus")


class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2


@dataclass
class Event:
    """事件对象"""
    topic: str                    # 事件主题，如 "email:new", "wechat:message"
    data: Any = None              # 事件数据
    source: str = ""              # 事件来源模块名
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __repr__(self):
        return f"Event({self.topic}, from={self.source}, id={self.event_id[:8]})"


class EventBus:
    """事件总线 - 进程内发布订阅"""

    def __init__(self):
        self._subscribers: Dict[str, List[tuple]] = {}   # topic -> [(sub_id, callback, priority)]
        self._lock = threading.RLock()
        self._event_queue: Queue = Queue()
        self._dispatch_thread: Optional[threading.Thread] = None
        self._running = False
        self._history: List[Event] = []
        self._history_max = 200

    # ── 发布 ────────────────────────────────────────────────────────────────

    def publish(self, topic: str, data: Any = None, source: str = "") -> Event:
        """同步发布一个事件，阻塞等待所有同步处理器"""
        event = Event(topic=topic, data=data, source=source)
        self._add_history(event)
        handlers = self._get_handlers(topic)
        for sub_id, cb, prio in sorted(handlers, key=lambda x: -x[2].value):
            try:
                cb(event)
            except Exception as e:
                logger.error(f"[EventBus] Handler error on {event}: {e}", exc_info=True)
        return event

    def post(self, topic: str, data: Any = None, source: str = "") -> Event:
        """异步发布 - 非阻塞，放入队列由后台线程分发"""
        event = Event(topic=topic, data=data, source=source)
        self._add_history(event)
        self._event_queue.put(event)
        self._ensure_dispatcher()
        return event

    def post_batch(self, events: List[Event]):
        """批量异步发布"""
        for e in events:
            self._event_queue.put(e)
        self._ensure_dispatcher()

    # ── 订阅 ────────────────────────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        callback: Callable[[Event], Any],
        priority: EventPriority = EventPriority.NORMAL,
        subscriber_id: Optional[str] = None,
    ) -> str:
        """订阅事件，返回订阅ID（可用来取消）"""
        if subscriber_id is None:
            subscriber_id = uuid.uuid4().hex
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append((subscriber_id, callback, priority))
            # priority 高的排前面
            self._subscribers[topic].sort(key=lambda x: -x[2].value)
        logger.debug(f"[EventBus] {subscriber_id} subscribed to {topic} (prio={priority.name})")
        return subscriber_id

    def unsubscribe(self, subscriber_id: str, topic: Optional[str] = None):
        """取消订阅。传 topic 只删该 topic，否则删所有该 subscriber_id 的订阅"""
        with self._lock:
            if topic and topic in self._subscribers:
                self._subscribers[topic] = [
                    (sid, cb, p) for sid, cb, p in self._subscribers[topic]
                    if sid != subscriber_id
                ]
            else:
                for t in self._subscribers:
                    self._subscribers[t] = [
                        (sid, cb, p) for sid, cb, p in self._subscribers[t]
                        if sid != subscriber_id
                    ]

    # ── 查询 ────────────────────────────────────────────────────────────────

    def get_handlers(self, topic: str) -> List[str]:
        """返回某 topic 的所有订阅者ID"""
        with self._lock:
            return [sid for sid, _, _ in self._subscribers.get(topic, [])]

    def get_history(
        self,
        topic: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Event]:
        """查询历史事件"""
        events = self._history
        if topic:
            events = [e for e in events if e.topic == topic]
        if since:
            events = [e for e in events if e.timestamp >= since]
        return events[-limit:]

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _get_handlers(self, topic: str) -> List[tuple]:
        with self._lock:
            return list(self._subscribers.get(topic, []))

    def _ensure_dispatcher(self):
        if self._dispatch_thread and self._dispatch_thread.is_alive():
            return
        self._running = True
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatch_thread.start()

    def _dispatch_loop(self):
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
            except Empty:
                if not self._running:
                    break
                continue
            handlers = self._get_handlers(event.topic)
            for sub_id, cb, prio in handlers:
                try:
                    cb(event)
                except Exception as e:
                    logger.error(f"[EventBus] Dispatch error on {event}: {e}", exc_info=True)

    def _add_history(self, event: Event):
        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max:]

    def stop(self):
        self._running = False


# 全局单例
event_bus = EventBus()
