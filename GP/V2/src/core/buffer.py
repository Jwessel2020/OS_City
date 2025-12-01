import threading
import time
from typing import TypeVar, Generic, Optional
from collections import deque

T = TypeVar('T')

class BoundedBuffer(Generic[T]):
    """
    A thread-safe bounded buffer implementing the Producer-Consumer pattern manually
    using threading.Lock and threading.Condition.
    
    OS Concepts Demonstrated:
    - Mutual Exclusion (Lock)
    - Condition Variables (wait/notify)
    - Bounded Buffer (Backpressure)
    - Blocking I/O (wait for space/item)
    """
    
    def __init__(self, capacity: int, name: str = "Buffer"):
        self.capacity = capacity
        self.name = name
        self._buffer: deque[T] = deque()
        self._lock = threading.Lock()
        
        # Condition variables for coordination
        # not_full: signaled when an item is removed (space available)
        self._not_full = threading.Condition(self._lock)
        # not_empty: signaled when an item is added (item available)
        self._not_empty = threading.Condition(self._lock)
        
        self._closed = False
        
        # Instrumentation stats
        self.stats = {
            "puts": 0,
            "gets": 0,
            "waits_for_space": 0,
            "waits_for_item": 0,
            "drop_count": 0
        }

    def put(self, item: T, timeout: Optional[float] = None) -> bool:
        """
        Add an item to the buffer. Blocks if full until space is available or timeout.
        Returns True if successful, False on timeout.
        Raises ValueError if buffer is closed.
        """
        start_time = time.perf_counter()
        with self._lock:
            if self._closed:
                raise ValueError(f"Buffer {self.name} is closed")
                
            while len(self._buffer) >= self.capacity:
                self.stats["waits_for_space"] += 1
                # Wait releases the lock and blocks until notified or timeout
                success = self._not_full.wait(timeout=timeout)
                
                if self._closed:
                    raise ValueError(f"Buffer {self.name} is closed")
                    
                if not success:
                    return False # Timed out
            
            self._buffer.append(item)
            self.stats["puts"] += 1
            
            # Signal consumers that an item is available
            self._not_empty.notify()
            return True

    def get(self, timeout: Optional[float] = None) -> Optional[T]:
        """
        Remove and return an item. Blocks if empty until item available or timeout.
        Returns item if successful, None on timeout.
        Raises StopIteration if buffer is closed and empty.
        """
        with self._lock:
            while not self._buffer:
                if self._closed:
                    # If closed and empty, we are done
                    raise StopIteration("Buffer closed and empty")
                
                self.stats["waits_for_item"] += 1
                success = self._not_empty.wait(timeout=timeout)
                
                if not success:
                    return None # Timed out
            
            item = self._buffer.popleft()
            self.stats["gets"] += 1
            
            # Signal producers that space is available
            self._not_full.notify()
            return item

    def try_put(self, item: T) -> bool:
        """
        Non-blocking put. Returns True if added, False if full.
        Useful for non-critical logging to prevent cascading blockage.
        """
        with self._lock:
            if self._closed:
                return False
            
            if len(self._buffer) >= self.capacity:
                self.stats["drop_count"] += 1
                return False
            
            self._buffer.append(item)
            self.stats["puts"] += 1
            self._not_empty.notify()
            return True

    def close(self) -> None:
        """
        Close the buffer. No more puts allowed. 
        Consumers can still drain remaining items.
        """
        with self._lock:
            self._closed = True
            # Wake up everyone so they check the closed flag
            self._not_empty.notify_all()
            self._not_full.notify_all()

    def qsize(self) -> int:
        """Return current number of items."""
        with self._lock:
            return len(self._buffer)
            
    def is_full(self) -> bool:
        """Check if buffer is full."""
        with self._lock:
            return len(self._buffer) >= self.capacity

