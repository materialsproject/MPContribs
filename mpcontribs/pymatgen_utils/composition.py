"""adapted from pymatgen.core.composition"""

import collections, six, re, os, json
from monty.fractions import gcd
from monty.design_patterns import cached_class
from fractions import Fraction
from abc import ABCMeta

ptfile = os.path.join(os.path.dirname(__file__), "periodic_table.json")
with open(ptfile, "rt") as f:
    _pt_data = json.load(f)

@cached_class
class Element(object):
    def __init__(self, symbol):
        self._symbol = "%s" % symbol
        self._data = _pt_data[symbol]
        self._x = self._data.get("X", 0)

    @property
    def symbol(self):
        """Element symbol"""
        return self._symbol

    @property
    def X(self):
        """Electronegativity"""
        return self._x

class Composition(collections.Mapping, collections.Hashable,
                  six.with_metaclass(ABCMeta)):
    amount_tolerance = 1e-8
    special_formulas = {
        "LiO": "Li2O2", "NaO": "Na2O2", "KO": "K2O2", "HO": "H2O2", "CsO":
        "Cs2O2", "RbO": "Rb2O2", "O": "O2",  "N": "N2", "F": "F2", "Cl": "Cl2",
        "H": "H2"
    }

    def __init__(self, *args, **kwargs): #allow_negative=False
        self.allow_negative = kwargs.pop('allow_negative', False)
        if len(args) == 1 and isinstance(args[0], Composition):
            elmap = args[0]._elmap
        elif len(args) == 1 and isinstance(args[0], six.string_types):
            elmap = self._parse_formula(args[0])
        else:
            elmap = dict(*args, **kwargs)
        self._elmap = {}
        self._natoms = 0
        for k, v in elmap.items():
            if v < -Composition.amount_tolerance and not self.allow_negative:
                raise CompositionError("Amounts in Composition cannot be negative!")
            if abs(v) >= Composition.amount_tolerance:
                self._elmap[Element(k)] = v
                self._natoms += abs(v)

    def _parse_formula(self, formula):

        def get_sym_dict(f, factor):
            sym_dict = collections.defaultdict(float)
            for m in re.finditer(r"([A-Z][a-z]*)([-*\.\d]*)", f):
                el = m.group(1)
                amt = 1
                if m.group(2).strip() != "":
                    amt = float(m.group(2))
                sym_dict[el] += amt * factor
                f = f.replace(m.group(), "", 1)
            if f.strip():
                raise CompositionError("{} is an invalid formula!".format(f))
            return sym_dict

        m = re.search(r"\(([^\(\)]+)\)([\.\d]*)", formula)
        if m:
            factor = 1
            if m.group(2) != "":
                factor = float(m.group(2))
            unit_sym_dict = get_sym_dict(m.group(1), factor)
            expanded_sym = "".join(["{}{}".format(el, amt)
                                    for el, amt in unit_sym_dict.items()])
            expanded_formula = formula.replace(m.group(), expanded_sym)
            return self._parse_formula(expanded_formula)
        return get_sym_dict(formula, 1)

    def get_integer_formula_and_factor(self, max_denominator=10000):
        mul = gcd(*[
            Fraction(v).limit_denominator(max_denominator)
            for v in self._elmap.values()
        ])
        sym_amt = self.get_el_amt_dict()
        d = { k: round(v/mul) for k,v in sym_amt.items() }
        (formula, factor) = reduce_formula(d)
        if formula in Composition.special_formulas:
            formula = Composition.special_formulas[formula]
            factor /= 2
        return formula, factor * mul

    def get_el_amt_dict(self):
        d = collections.defaultdict(float)
        for e, a in self._elmap.items():
            d[e.symbol] += a
        return d

def reduce_formula(sym_amt):
    syms = sorted(sym_amt.keys(), key=lambda s: Element(s).X)
    syms = list(filter(
        lambda s: abs(sym_amt[s]) > Composition.amount_tolerance, syms
    ))
    num_el = len(syms)
    contains_polyanion = (
        num_el >= 3 and
        Element(syms[num_el-1]).X - Element(syms[num_el-2]).X < 1.65
    )
    factor = abs(gcd(*sym_amt.values()))
    reduced_form = []
    n = num_el-2 if contains_polyanion else num_el
    for i in range(0, n):
        s = syms[i]
        normamt = sym_amt[s] * 1.0 / factor
        reduced_form.append(s)
        reduced_form.append(formula_double_format(normamt))
    if contains_polyanion:
        poly_sym_amt = {
            syms[i]: sym_amt[syms[i]] / factor for i in range(n, num_el)
        }
        (poly_form, poly_factor) = reduce_formula(poly_sym_amt)
        if poly_factor != 1:
            reduced_form.append("({}){}".format(poly_form, int(poly_factor)))
        else:
            reduced_form.append(poly_form)
    reduced_form = "".join(reduced_form)
    return reduced_form, factor

def formula_double_format(afloat, ignore_ones=True, tol=1e-8):
    if ignore_ones and afloat == 1:
        return ""
    elif abs(afloat - int(afloat)) < tol:
        return str(int(afloat))
    else:
        return str(round(afloat, 8))

class CompositionError(Exception):
    """Exception class for composition errors"""
    pass

