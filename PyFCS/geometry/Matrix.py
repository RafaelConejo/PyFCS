import copy
import math

class Matrix:
    def __init__(self, n, x=None):
        self.n = n
        if x is None:
            self.x = [[0.0] * n for _ in range(n)]
        else:
            self.x = copy.deepcopy(x)

    def clone(self):
        obj = copy.copy(self)
        obj.x = copy.deepcopy(self.x)
        return obj

    def traza(self):
        tr = 0.0
        for i in range(self.n):
            tr += self.x[i][i]
        return tr

    @staticmethod
    def suma(a, b):
        resultado = Matrix(a.n)
        for i in range(a.n):
            for j in range(a.n):
                resultado.x[i][j] = a.x[i][j] + b.x[i][j]
        return resultado

    @staticmethod
    def producto(a, b):
        resultado = Matrix(a.n)
        for i in range(a.n):
            for j in range(a.n):
                for k in range(a.n):
                    resultado.x[i][j] += a.x[i][k] * b.x[k][j]
        return resultado

    @staticmethod
    def producto_escalar(a, d):
        resultado = Matrix(a.n)
        for i in range(a.n):
            for j in range(a.n):
                resultado.x[i][j] = a.x[i][j] * d
        return resultado

    @staticmethod
    def producto_escalar_inverso(d, a):
        return Matrix.producto_escalar(a, d)

    @staticmethod
    def traspuesta(a):
        n = a.n
        d = Matrix(n)
        for i in range(n):
            for j in range(n):
                d.x[i][j] = a.x[j][i]
        return d

    def determinante(self):
        a = self.clone()
        for k in range(self.n - 1):
            for i in range(k + 1, self.n):
                for j in range(k + 1, self.n):
                    a.x[i][j] -= a.x[i][k] * a.x[k][j] / a.x[k][k]
        deter = 1.0
        for i in range(self.n):
            deter *= a.x[i][i]
        return deter

    @staticmethod
    def inversa(d):
        n = d.n
        a = d.clone()
        b = Matrix(n)
        c = Matrix(n)
        for i in range(n):
            b.x[i][i] = 1.0
        for k in range(n - 1):
            for i in range(k + 1, n):
                for s in range(n):
                    b.x[i][s] -= a.x[i][k] * b.x[k][s] / a.x[k][k]
                for j in range(k + 1, n):
                    a.x[i][j] -= a.x[i][k] * a.x[k][j] / a.x[k][k]
        for s in range(n):
            c.x[n - 1][s] = b.x[n - 1][s] / a.x[n - 1][n - 1]
            for i in range(n - 2, -1, -1):
                c.x[i][s] = b.x[i][s] / a.x[i][i]
                for k in range(n - 1, i, -1):
                    c.x[i][s] -= a.x[i][k] * c.x[k][s] / a.x[i][i]
        return c

    def pol_caracteristico(self):
        pot = self.clone()
        for i in range(1, self.n + 1):
            pot = Matrix.producto(pot, self)
        s = [0.0] * (self.n + 1)
        p = [0.0] * (self.n + 1)
        for i in range(1, self.n + 1):
            s[i] = pot.traza()
        p[0] = 1.0
        p[1] = -s[1]
        for i in range(2, self.n + 1):
            p[i] = -s[i] / i
            for j in range(1, i):
                p[i] -= s[i - j] * p[j] / i
        return p

    def valores_propios(self, max_iter):
        CERO = 1e-8
        contador = 0
        a = self.clone()
        p = Matrix(self.n)
        q = Matrix(self.n)
        for i in range(self.n):
            q.x[i][i] = 1.0
        while contador < max_iter:
            k = l = 0
            maximo = abs(a.x[k][1])
            for i in range(self.n - 1):
                for j in range(i + 1, self.n):
                    if abs(a.x[i][j]) > maximo:
                        k, l = i, j
                        maximo = abs(a.x[i][j])
            sumsq = sum(a.x[i][i] * a.x[i][i] for i in range(self.n))
            tolerancia = 0.0001 * math.sqrt(sumsq) / self.n
            if maximo < tolerancia:
                break
            p.x = [[0.0] * self.n for _ in range(self.n)]
            for i in range(self.n):
                p.x[i][i] = 1.0
            y = a.x[k][k] - a.x[l][l]
            if abs(y) < CERO:
                c = s = math.sin(math.pi / 4)
            else:
                x = 2 * a.x[k][l]
                z = math.sqrt(x * x + y * y)
                c = math.sqrt((z + y) / (2 * z))
                s = Matrix.signo(x / y) * math.sqrt((z - y) / (2 * z))
            p.x[k][k] = c
            p.x[l][l] = c
            p.x[k][l] = s
            p.x[l][k] = -s
            a = Matrix.producto(p, Matrix.producto(a, Matrix.traspuesta(p)))
            q = Matrix.producto(q, Matrix.traspuesta(p))
            contador += 1
        if contador == max_iter:
            raise ValueError("No se han podido calcular los valores propios")
        valores = [round(a.x[i][i], 3) for i in range(self.n)]
        return valores, q

    def __str__(self):
        texto = "\n"
        for i in range(self.n):
            for j in range(self.n):
                texto += f"\t {round(1000 * self.x[i][j]) / 1000}"
            texto += "\n"
        texto += "\n"
        return texto

    @staticmethod
    def signo(x):
        return 1 if x > 0 else -1


class ValoresExcepcion(Exception):
    def __init__(self, message):
        super().__init__(message)


# Ejemplo de uso
# matrix = Matrix(3, [[1, 2, 3], [4, 5, 6], [7, 8, 9]])
# valores, vectores = matrix.valores_propios(100)
# print("Valores propios:", valores)
# print("Vectores propios:")
# for vector in vectores.x:
#     print(vector)
