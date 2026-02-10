from typing import Optional

class MembershipFunction():
    def __init__(self, a: float = 0, b: float = 0, c: float = 0, name: Optional[str] = None):
        self.a = a
        self.b = b
        self.c = c
        self.dimension = 1
        self.domain = None
        self.name = name

    def getDimension(self) -> int:
        return self.dimension

    def getValue(self, o: object) -> float:
        x = float(o)

        if x <= self.a:
            return 1
        if x > self.c:
            return 0

        if self.a < x <= self.b:
            return ((self.b - x) + (self.b - self.a)) / (2 * (self.b - self.a))
        else:
            return (self.c - x) / (2 * (self.c - self.b))

    def setParam(self, p: Optional[list]) -> None:
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
