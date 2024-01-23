
class Point:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

class Line:
    def __init__(self, p1: Point, p2: Point):
        self.p1 = p1
        self.p2 = p2

# Ejemplo de uso
# point1 = Point(1.0, 2.0, 3.0)
# point2 = Point(4.0, 5.0, 6.0)
# line = Line(point1, point2)
