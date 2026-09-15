from typing import Optional
import math


class MembershipFunction:
    def __init__(self, a: float = 0, b: float = 0, c: float = 0, name: Optional[str] = None):
        self.a = a
        self.b = b
        self.c = c
        self.dimension = 1
        self.domain = None
        self.name = name

    def getDimension(self) -> int:
        return self.dimension

    @staticmethod
    def evaluate(x, a, b, c) -> float:
        """
        Pure/thread-safe membership evaluation.

        This is the preferred runtime path in PyFCS because it does not mutate
        shared MembershipFunction state between calls or worker threads.
        """
        x = float(x)
        a = float(a)
        b = float(b)
        c = float(c)

        if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)):
            return 0.0

        if not (a <= b <= c):
            return 0.0

        if x <= a:
            return 1.0
        if x > c:
            return 0.0

        if a < x <= b:
            denom = 2 * (b - a)
            if denom == 0:
                return 1.0
            return ((b - x) + (b - a)) / denom

        denom = 2 * (c - b)
        if denom == 0:
            return 0.0
        return (c - x) / denom

    def getValue(self, o: object) -> float:
        # Backwards-compatible instance API.
        return self.evaluate(o, self.a, self.b, self.c)

    def setParam(self, p: Optional[list]) -> None:
        # Retained for backwards compatibility. New PyFCS membership paths use
        # evaluate() directly and therefore do not rely on mutable state.
        if p is not None and len(p) == 3:
            self.a = float(p[0])
            self.b = float(p[1])
            self.c = float(p[2])

    def getParam(self) -> object:
        return [self.a, self.b, self.c]

    def getName(self) -> Optional[str]:
        return self.name

    def setName(self, name: Optional[str]) -> None:
        self.name = name
