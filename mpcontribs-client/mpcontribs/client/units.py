"""Define unit registry used in the client."""

from pint import UnitRegistry

ureg: UnitRegistry = UnitRegistry(
    autoconvert_offset_to_baseunit=True,
    preprocessors=[
        lambda s: s.replace("%%", " permille "),
        lambda s: s.replace("%", " percent "),
    ],
)
if "percent" not in ureg:
    # percent is native in pint >= 0.21
    ureg.define("percent = 0.01 = %")
if "permille" not in ureg:
    # permille is native in pint >= 0.24.2
    ureg.define("permille = 0.001 = ‰ = %%")
if "ppm" not in ureg:
    # ppm is native in pint >= 0.21
    ureg.define("ppm = 1e-6")
ureg.define("ppb = 1e-9")
ureg.define("atom = 1")
ureg.define("bohr_magneton = e * hbar / (2 * m_e) = µᵇ = µ_B = mu_B")
ureg.define("electron_mass = 9.1093837015e-31 kg = mₑ = m_e")
ureg.define("sccm = cm³/min")
