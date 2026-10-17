"""Symptom-only prompts for sympy tasks. Example outputs are computed at the base and fix commits by build.py."""

SPEC = {
'44521b8f6c': ("ratint returns a wrong antiderivative for some rational functions with symbolic-constant coefficients: "
  "roots of the log part are duplicated, so the result's derivative is not the integrand and definite values come out "
  "wrong (sympy issue #28657). ratint should not produce duplicate root terms.",
  ['(lambda P: round(float((P.evalf(subs={x: 1e100}) - P.evalf(subs={x: 0})).evalf()), 6))(__import__("sympy.integrals.rationaltools", fromlist=["ratint"]).ratint(400*pi**2*x**2/(1600*pi**4*x**4 - 796*pi**2*x**2 + 100), x))']),
'998fbe45fc': ("manualintegrate hangs (never returns) on log((cos(x)/2 + 1)/(1 - cos(x)/2))/cos(x). It should return a "
  "result (an antiderivative, or an unevaluated integral rule) in reasonable time instead of looping.",
  ['__import__("sympy.integrals.manualintegrate", fromlist=["manualintegrate"]).manualintegrate(log((cos(x)/2 + 1)/(1 - cos(x)/2))/cos(x), x) is not None']),
'27be5eba66': ("inverse_laplace_transform does not undo an unevaluated LaplaceTransform: "
  "inverse_laplace_transform(LaplaceTransform(f(t), t, s), s, t) should give f(t)*Heaviside(t) (and f(x)*Heaviside(x) "
  "when inverting into another variable x). When the transform variable does not match (inverting over a different "
  "variable than s), the expression is a constant in that variable and should come back times DiracDelta(t).",
  ['inverse_laplace_transform(LaplaceTransform(Function("f")(t), t, s), s, t)',
   'inverse_laplace_transform(LaplaceTransform(Function("f")(t), t, s), s, x)']),
'9350380769': ("log(x).is_finite gives wrong answers: for x that may be zero, log(x) can be infinite, so is_finite must not "
  "be True. For x known to be nonzero and finite, log(x) is finite; for an unevaluated log(0) is_finite is False; when "
  "zero cannot be excluded (e.g. an integer or a nonnegative symbol) the answer is None.",
  ['log(Symbol("i", integer=True)).is_finite', 'log(Symbol("nn", nonnegative=True)).is_finite',
   'log(Symbol("nz", finite=True, nonzero=True)).is_finite', 'log(0, evaluate=False).is_finite']),
'ca0a14d19a': ("The derivative of asech(x) is wrong for x < -1: asech(x).diff(x) returns -1/(x*sqrt(1 - x**2)), which has "
  "the wrong sign on that branch, and the series expansions around points left of -1 inherit the error. The derivative "
  "must agree with asech's principal branch everywhere (compare against a numerical derivative at x = -3).",
  ['asech(x).diff(x)', '(lambda d: N(d.subs(x, -3), 10))(asech(x).diff(x))']),
'5e60418896': ("Some special-function rewrites have sign errors: li(z).rewrite(Shi) and li(z).rewrite(Chi) do not equal "
  "li(z) numerically (for 0 < z < 1 or z > 1), and erfi(z).rewrite(expint) does not equal erfi(z) (e.g. at z = 2). "
  "Rewrites must preserve the value of the function.",
  ['N((li(z).rewrite(Shi) - li(z)).subs(z, 3), 10)', 'N((erfi(z).rewrite(expint) - erfi(z)).subs(z, 2), 10)']),
'ed2a9bef3b': ("Integrating products of Piecewise functions with symbolic breakpoints gives nan: with "
  "p = [(a1, t < 1), (a2, t < 2), (a3, t < 3)] and f_i = Piecewise(*p).subs(t, t_i), "
  "integrate(f2*integrate(f3, (t3, 0, t2)), (t2, 0, t1)) is nan for every t1 >= 0 (sympy issue #28469). Piecewise "
  "interval evaluation must handle these boundaries, so the result is the correct piecewise expression in t1.",
  ['(lambda a1, a2, a3, t, t1, t2, t3: integrate(Piecewise((a1, t < 1), (a2, t < 2), (a3, t < 3)).subs(t, t2) * integrate(Piecewise((a1, t < 1), (a2, t < 2), (a3, t < 3)).subs(t, t3), (t3, 0, t2)), (t2, 0, t1)).subs({t1: Rational(5, 2), a1: 1, a2: 2, a3: 3}))(*symbols("a1 a2 a3 t t1 t2 t3"))']),
'1e427cc30a': ("Matrix.eigenvals(rational=True) returns floating-point eigenvalues for matrices with float entries, e.g. "
  "Matrix([[1.0, 0.0], [0.0, 2.0]]).eigenvals(rational=True) gives float keys. With rational=True the entries should be "
  "converted to rationals so the eigenvalues are exact.",
  ['Matrix([[1.0, 0.0], [0.0, 2.0]]).eigenvals(rational=True)']),
'8ff0458f56': ("QRdecomposition of a symbolic matrix with linearly dependent columns is wrong: for A = Matrix([[a, k*a], "
  "[b, k*b]]) with real a, b, k, the rank is 1 but Q gets two columns and Q.H*Q contains nan. The decomposition should "
  "detect the dependency, give Q with A.rank() columns, and still satisfy Q*R == A.",
  ['(lambda a, b, k: Matrix([[a, k*a], [b, k*b]]).QRdecomposition()[0].cols)(*symbols("a b k", real=True))']),
'3e18ad01a1': ("nonlinsolve returns incorrect parametric solutions for systems with Abs: nonlinsolve([Abs(x) - y], x, y) "
  "returns {(y, y), (-y, y)} without the condition y >= 0, and systems like [Abs(x) - 1, x - y] give wrong answers. "
  "Since the solver cannot express these conditions, it should raise NotImplementedError rather than return wrong solutions.",
  ['nonlinsolve([Abs(x) - y], x, y)', 'nonlinsolve([Abs(x) - 1, x - y], x, y)']),
'64f6a7cafb': ("solve cannot solve equations and systems containing Max or Min: solve([Eq(y, Max(x, -x)), Eq(y, 1)], (x, y)) "
  "fails or gives incomplete results. solve should handle Max/Min (for example by rewriting them as Piecewise first) and "
  "return all solutions, e.g. [(-1, 1), (1, 1)] for that system.",
  ['solve([Eq(y, Max(x, -x)), Eq(y, 1)], (x, y))', 'solve([Eq(y, Min(x, -x)), Eq(y, 2*x + 3)], (x, y))']),
'5aec828105': ("fraction(expr, exact=True) is wrong for an unevaluated negative power: for u = Pow(2, -2, evaluate=False), "
  "fraction(u, exact=True) should be (1, Pow(2, 2, evaluate=False)), keeping the exponent unevaluated.",
  ['fraction(Pow(2, -2, evaluate=False), exact=True)']),
'd671b70c7d': ("One-sided limits of exponentials with a singular exponent ignore the direction: limit(2**(1/x), x, 0, dir='-') "
  "should be 0 and dir='+' should be oo, and likewise limit(3**tan(x), x, pi/2, dir='-') is oo while dir='+' is 0 "
  "(sympy issue #28975). The direction must be respected in these cases.",
  ['limit(2**(1/x), x, 0, dir="-")', 'limit(3**tan(x), x, pi/2, dir="+")']),
'5746517ff8': ("subresultants_pg and modified_subresultants_pg produce NaN (Pell-Gordon variables) when a pseudo-remainder "
  "becomes zero, e.g. for p = 4*x**3 + 3*x**2 + x + 2 and q = x + 1. A zero pseudo-remainder must terminate the "
  "sequence, so the result is [p, q].",
  ['__import__("sympy.polys.subresultants_qq_zz", fromlist=["subresultants_pg"]).subresultants_pg(4*x**3 + 3*x**2 + x + 2, x + 1, x)']),
}
