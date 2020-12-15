# RedoxThermoCSP

Documentation for the `RedoxThermoCSP` [landing
page](https://contribs.materialsproject.org/redox_thermo_csp/).

## Introduction

RedoxThermoCSP is a set of tools to calculate **thermodynamic properties of perovskites**
AMO<sub>3-δ</sub>. Depending on the temperature and oxygen partial pressure, many of these
perovskites show an oxygen non-stoichiometry expressed by *δ*. Moreover, the composition
of these perovskites can be tuned over a large range of different elements, allowing to
tune their thermodynamic properties. For these reasons, those materials are ideally
suitable as redox materials in two-step thermochemical redox cycles (see Fig. 1).  In a
first step, the materials are reduced at high temperature and/or low oxygen partial
pressure under the release of oxygen. The heat for the reduction can be supplied through
concentrated solar power (CSP). In a second step, the materials are re-oxidized in air,
or, if thermodynamically possible, in steam, or CO<sub>2</sub>. By this means, these
perovskites may be used for two-step thermochemical oxygen storage, pumping, or air
separation.  Moreover, some of them can be used for water splitting or CO<sub>2</sub>
splitting, allowing the generation of solar fuels. Our approach is based upon creating
**solid solutions of perovskites** to tune their thermodynamic properties. These solid
solutions, denoted by

(A</sup>'</sup><sub>x</sub>A</sup>''</sup><sub>1-x</sub>)<sup>(6-n)+</sup>(M</sup>'</sup><sub>y</sub>M</sup>''</sup><sub>1-y</sub>)<sup>(n-2δ)+</sup>O<sub>3-δ</sub>

with n = 3, 4, 5 are defined by varying the content of the transition metals M while
maintaining a fixed Goldschmidt tolerance factor by varying the content of A site metals.

The theoretical data is based on DFT calculations performed within the infrastructure of
[The Materials Project](https://www.materialsproject.org) based on
[VASP](https://www.vasp.at). Part of our data is gathered using
[pymatgen](http://pymatgen.org) and
[FireWorks](https://materialsproject.github.io/fireworks/). Reaction enthalpies were
calculated using pymatgen's [reaction
calculator](https://materialsproject.org/docs/rxncalculator). If you use our tool, please
cite the respective publications[^1]. Although carefully researched, we assume no liability
for the accuracy of the data.

![Figure 1](Fig_1.png)

**Fig. 1:** Two-step thermochemical cycles based on perovskites AMO<sub>3-δ</sub> with a
reduction step at high temperature and/or low oxygen partial pressure, followed by
re-oxidation at lower temperature and/or lower partial pressure[^2].

## Generating thermodynamic data

### Experimental data

The experimental thermodynamic data has been acquired in **thermogravimetric experiments**
using the **van't Hoff approach**.  Powdered samples (100-300 mg) are subjected to
different atmospheres at different temperature levels (≈400-1300 °C) in a thermobalance.
Oxygen partial pressures p<sub>O2</sub> between ≈10<sup>-4</sup> bar and 0.9 bar are set
using a mixture of O<sub>2</sub>, Ar, and synthetic air in different flow rates. From
equilibrium data of the mass change Δm induced by oxygen release or uptake, we retreived
the change in redox enthalpy as a function of the oxygen non-stoichiometry ΔH(δ) and the
respective change in entropy ΔS(δ).  This data is available by opening the materials
details pages by clicking on a contribution identifier in the table of materials data. The
experimental thermodynamic data is fit using an empirical model. This allows interpolating
between the measured data points and, to some extent, extrapolations.  Our approach allows
modelling the **thermodynamics of perovskite solid solutions**.  Take a solid solution
like Ca<sub>0.5</sub>Sr<sub>0.5</sub>Fe<sub>0.5</sub>Mn<sub>0.5</sub>O<sub>3-δ</sub> for
example. According to DFT data, the <b>redox enthalpy ΔH</b> of SrMnO<sub>3-δ</sub> or
CaMnO<sub>3-δ</sub> is signifiantly larger than the redox enthalpies of
SrFeO<sub>3-δ</sub> or CaFeO<sub>3-δ</sub>. As the Fe<sup>4+</sup> ions in this
perovskites are typically reduced more readily than the Mn<sup>4+</sup> ions, the redox
enthalpy for low values of δ is typically lower than for high values of δ[^3]. In our
model, this behavior is represented by determining a lower limit of ΔH (dH<sub>min</sub>)
for δ → 0 and a higher limit of ΔH (dH<sub>max</sub>) for δ → 0.5, with an arctangent
function describing the gradual increase of ΔH as a function of δ between these limits.

The **change in entropy ΔS** for a perovskite can be modeled assuming dilute species[^4].
We use this model by assuming two independent sub-lattices in a solid solution containing
the two different redox-active species, of which the one with the less redox-active
species only contributes significantly for high values of δ.

The mass change Δm of perovskites was measured vs. a reference point at
p<sub>O2</sub>=0.18 bar and T=400 °C. Therefore, the change in non-stoichiometry is only
measured relative to this reference point as a value of Δδ. To obtain the absolute δ
values, we determined the δ at the reference point, denoted by δ<sub>0</sub> (δ = Δδ +
δ<sub>0</sub>). This has been done by using the dilute species model and substituing δ for
Δδ + δ<sub>0</sub>, which allows obtaining δ<sub>0</sub> as one of the fit parameters.
This method can be inaccurate, therefore, some experimental datasets are shifted in
direction of δ, such as the dataset for
Ca<sub>0.15</sub>Sr<sub>0.85</sub>Mn<sub>0.2</sub>Fe<sub>0.8</sub>O<sub>3-δ</sub>. All
thermodynamic properties are given per mol of O.

Our set of experimental thermodynamic data consists of **24 materials**, which are
solid solutions of perovskites with fixed tolerance factor w.r.t. the fully oxidized
state. Some datasets contain only small ranges of δ, which is due to the constraints in
redox conditions we can achieve in the thermobalance. For instance, Co-substituted
SrFeO<sub>3-δ</sub> perovskites could only be measured at very high δ values, as they
cannot be oxidized further under ambient oxygen pressure and decompose as soon as δ > ≈0.5
at temperatures above 600-700 °C.

Details on our empirical model, the redox behavior of perovskite solid solutions, and our
measurement approach can be found in [^1] and [^3].

### Theoretical data

The crystal structures of SrFeO<sub>3</sub> (perovskite, cubic unit cell, space group 221)
and Sr<sub>2</sub>Fe<sub>2</sub>O<sub>5</sub> (brownmillerite, orthorhombic, space group
46) are used as prototypes for the perovskite solid solutions. To allow solid solutions
with integer occupancies, 2x2x2 supercells are created from these prototypes and
occupancies are rounded to fractions of 1/8, leading to a maximum of 144 atoms per unit
cell for the brownmillerites. The most stable distribution of species in the solid
solution is found by minimizing the Ewald sum. GGA and GGA+<i>U</i> calculations are
combined according to <a href="https://doi.org/10.1103/PhysRevB.84.045115">Jain et.
al.</a> The redox enthalpy for a complete reduction from perovskite (δ=0) to
brownmillerite (δ=0.5) under the release of oxygen is calculated using the reaction
calculator in pymatgen and normalized per mol of O.<br> Based on these values, the gradual
increase of redox <b>enthalpies</b> with increasing δ in solid solutions is modelled by
assuming two independent sub-lattices, accounting for the two species with different
reducibility. The redox enthalpies of the solid solution endmembers serve as boundaries
for the minimum and maximum redox enthalpies, and ΔH(δ,T) is determined by first
calculating the equilibrium p<sub>O2</sub>(δ,T) based on the non-stoichiometries of the
individual sub-lattices, which is then used to calculate ΔH(δ,T) as a numerical derivative
of the oxygen partial pressure vs. the temperature.

The <b>entropy</b> of the solid solutions is calculated as the sum of three
constituents:<br> <center>ΔS(δ,T) = S<sub>0,O2</sub>(T) + Δs<sub>vib</sub>(T) +
Δs<sub>conf</sub>(δ,T)</center><br> S<sub>0, O2</sub>(T) refers to the partial molar
entropy of oxygen, which can be determined by using the <a
href="https://janaf.nist.gov/">NIST-JANAF thermochemical tables</a> and the Shomate
equation. Δs<sub>conf</sub>(δ,T) describes the configurational entropy, which can be
calculated using the dilute species model for both sub-lattices, and Δs<sub>vib</sub>(T)
is the vibrational entropy, which can be determined using the Debye model from the Debye
temperatures.  The Debye temperatures are calculated from the elastic tensors, which are
determined using <a href="http://dx.doi.org/10.1038/sdata.2015.9">DFT data</a>. Elastic
tensors are not available for some materials, in which case the data for
SrFeO<sub>3-δ</sub> is used instead as an approximation. As the vibrational entropy is
usually the smallest of the three contributions to the total entropy change, the error
introduced by doing so is small. The set of elastic tensors in The Materials Project is
continuously extended, which will eventually allow to get more accurate data for more and
more materials.

Our set of theoretical thermodynamic data consists of **> 240 perovskite/brownmillerite
redox pairs**, many of them solid solutions with fixed tolerance factor. Pure ternary
compounds, such as EuFeO<sub>3-δ</sub> or BaMnO<sub>3-δ</sub> are also included,
irrespective of their predicted stability according to the tolerance factor. All materials
used in our contribution are accessible through The Materials Project, where additional
data can be found, such as the predicted thermodynamic stability which is related to the
energy above hull. The dataset also includes perovskites which are likely to be highly
unstable under the conditions conceivable in practical application, such as
MgCoO<sub>3-δ</sub>, NaVO<sub>3-δ</sub>, or SrCuO<sub>3-δ</sub>.

Details on our theoretical approach to modelling the thermodynamic data of perovskite
solid solutions are given in [^1].

## Using the Isographs tool

A list of available materials is available on the bottom of the page. This list can be
filtered by entering elements or the composition in the search bar:

![filtering entries](Fig_2.png)

By clicking on one of the rows, the corresponding "Isographs" are displayed above.
Theoretical data is shown in <font color="red">red</font>, and experimental data (if
available) is shown in <font color="blue">blue</font>. Interpolated experimental data is
shown as solid line, whereas extrapolated experimental data is displayed as dashed line to
indicate its potential inaccuracy. Please note: As described above, the experimental data
can be shifted significantly in δ direction w.r.t. the theoretical data - this has
typically no big impact on the relative changes in non-stoichiometry.

The Isographs tool includes the following 6 plots:

* **Isotherm:** Shows the non-stoichiometry δ as a function of the oxygen partial pressure
    p<sub>O2</sub> (in bar) with fixed temperature T (in K)
* **Isobar:** Shows the non-stoichiometry δ as a function of the temperature T (in K) with
    fixed oxygen partial pressure p<sub>O2</sub> (in bar)
* **Isoredox:** Shows the oxygen partial pressure p<sub>O2</sub> (in bar) as a function of
    the temperature T (in K) with fixed non-stoichiometry δ
* **Enthalpy (dH):** Shows the redox enthalpy ΔH as a function of the non-stoichiometry δ.
    Please note: The experimental dataset only contains values of ΔH(δ) instead of ΔH(δ,T)
    due to the measurement method. The fixed temperature value T therefore only refers to
    the theoretical data.
* **Entropy (dS):** Shows the redox entropy ΔS as a function of the non-stoichiometry δ.
    Please note: The experimental dataset only contains values of ΔS(δ) instead of ΔS(δ,T)
    due to the measurement method. The fixed temperature value T therefore only refers to
    the theoretical data.
* **Ellingham diagram:** Shows ΔG<sup>0</sup> as a function of the temperature T (in K)
    with fixed non-stoichiometry δ. The <font color="gray">gray</font> isobar line can be
    adjusted to account for different oxygen partial pressures according to
    ΔG(p<sub>O2</sub>) = ΔG<sup>0</sup> - 1/2 * RT * ln(p<sub>O2</sub>). If ΔG<sup>0</sup>
    is below the isobar line, the reduction occurs spontaneously.

The graphs are interactive. Upon change of the fixed temperature or pressure values on the
sliders above the graphs, the plot will be updated automatically. Moreover, the data can
be zoomed in by selecting an area in the graph with the mouse, and zoomed out by double
clicking on the graph. All graphs are based on <a href="https://plot.ly/">plotly</a>.
Plotly allows downloading the plots as .png files and editing graphs online:

![downloading graphs](Fig_3.png)

## Using the Energy Analysis tool

The Energy Analysis tool is a powerful means to find the ideal redox material for a
specific application. It returns a ranked list of suitable materials visualized as an
interactive bar graph. The energy input is given as heat input per complete redox cycle
(reduction + oxidation step).

The energy input neccessary to operate a certain redox cycle consitutes of the following
elements:

* **Chemical Energy:** The chemical energy is defined by the redox enthalpy and is
    calculated as the integral over ΔH(δ) from δ<sub>ox</sub> to δ<sub>red</sub>. It is
    inversely proportional to the heat recovery efficiency &#x03B7;<sub>hrec, solid</sub>,
    as a more efficient heat recovery system allows for a larger fraction of the redox
    material to be re-heated by the waste heat from the previous cycle.
* **Sensible Energy:** The chemical energy is defined by the heat capacity and is
    calculated using the Debye model based on the elastic tensors of the materials (see
    above). Due to the relatively small changes in oxygen content of many perovskites upon
    reduction, this typically constitutes the largest share of energy consumption per mol
    of product. Please note that the experimental dataset does not contain heat capacity
    data, so the sensible energy is always based on theoretical considerations. The heat
    recovery efficiency &#x03B7;<sub>hrec, solid</sub> has an analogous effect on the
    amount of sensible energy required per redox cycle as for the chemical energy.
* **Pumping Energy:** This refers to the energy required to pump the oxygen released
    during reduction out of the reactor chamber. It is independent of the reduction
    temperature or any oxidation conditions. No heat recovery from pumping is assumed. It
    is possible to either define a fixed value of pumping energy in terms of kJ/kg of
    redox material, or use the mechanical envelope function defined by <a
    href="https://www.sciencedirect.com/science/article/pii/S0038092X16305552">Brendelberger
    et. al</a>. The latter refers to the minimum energy required to pump a certain amount
    of oxygen using mechanical pumps according to an analytical function, which is defined
    between 10<sup>-6</sup> bar and 0.7 bar total pressure (=oxygen partial pressure in
    this case) with an operating temperature of the pump of 200 °C. The value defined by
    the mechanical envelope may be undercut at low oxygen partial pressures <a
    href="https://www.sciencedirect.com/science/article/pii/S0038092X18304961">using
    thermochemical pumps</a> as an alternative. Sweep gas operation cannot be modelled
    using our approach.
* **Steam Generation:** This value is only displayed if water splitting is selected as
    process type. It refers to the energy required to heat steam to the oxidation
    temperature of the redox material. The inlet temperature of the steam generator can be
    defined. If it is below 100 °C, the heat of evaporation (40.79 kJ/mol) and the energy
    required to heat liquid water to its boiling point are considered. The heat capacities
    for water and steam are calculated using data from the <a
    href="https://janaf.nist.gov/">NIST-JANAF thermochemical tables</a>. For water
    splitting, a lower ratio of H<sub>2</sub> vs. H<sub>2</sub>O in the product stream
    increases the amount of energy required for steam generation significantly, as more
    water needs to be heated up to generate the same amount of hydrogen.  It is also
    possible to define a heat recovery efficiency from steam, which may be different from
    the heat recovery efficiency from the solid.

**Options:**

* **Data source:** Select experimental or theoretical data. Please note that experimental
    data may be inaccurate outside the window of process conditions set by our measurement
    (400-1200 °C, 10<sup>-4</sup>-0.9 bar p<sub>O2</sub> in most cases).
* **Process type:** Air Separation, Water Splitting, CO<sub>2</sub> Splitting. Please
    note that if experimental data is selected, only Air Separation can be chosen. This is
    intended - we did not study materials experimentally which are capable of water or
    CO<sub>2</sub> splitting.
* **Display parameters:** The materials can be ranked by different parameters, including
    energy per mol of material or per mol of product. The heat to fuel efficiency for
    water splitting is defined as the <a href="https://h2tools.org/node/3131">higher
    heating value of hydrogen</a> divided by the total heat input + pumping energy. It
    does not account for any losses. Practical total efficiencies are therefore always
    lower than the displayed value.
* **Amount of materials to display:** The amount of materials displayed can be changed to
    get a better overview.

## Using the results for materials selection

Although the <i>RedoxThermoCSP</i> tools yield a rich dataset with profound physical and
chemical background, it is important to consider its limitations. Any theoretical dataset
is only as good as the theory behind it, and fitted experimental data may be biased by the
fitting method. In general, we want these tools to serve as a method of materials
pre-selection. The theoretical data cannot replace experiments, but it will significantly
reduce the amount of materials to investigate experimentally and increase the success rate
of experiments.

Our materials screening method predicts some materials which are likely to be unstable. We
excluded those materials in the <i>Energy Analysis</i> section, but this data is still
available to plot <i>Isographs</i>, and more information can be found in the accompanying
publications. We excluded 36 materials out of the >200 theoretical datasets for the
following reasons:

* **tolerance factor < 0.9:** Experiments performed in our labs have shown that
    EuFeO<sub>3-δ</sub> is a stable perovskite, whereas EuCuO<sub>3-δ</sub> could not be
    synthesized due to its tolerance factor of about 0.88 (Cu<sup>3+</sup> ions have a too
    large ionic radius).
* **Covalent V-O bonds:** Compounds such as NaVO<sub>3</sub> are stable, but those are not
    perovskite-structured. Due to the high covalency of the V-O bond in those cases, they
    form salt like structures with vanadate anions. Therefore, we exclude all compounds with
    V<sup>5+</sup> cations in the lattice.
* **Low melting points (alkali molybdenates):** Some compounds form perovskites and
    similar structures, but they have melting points of only a few hundred degrees
    centrigrade, making them not useful for most thermochemical applications. Moreover, it
    is not reasonable to calculate properties like the oxygen non-stoichiometry for these
    compounds, at least not the way we treat solids. One example is sodium molybenate, and
    therefore exclude all compounds containing Mo<sup>5+</sup> cations[^5].

This list is by no means complete, most of the perovskite solid solutions we suggest have
never been systhesized. However, with some understanding of perovskite chemistry and using
literature on similar phases, it should be possible to get a good estimate on the
stability of a suggested phase.<br> Moreover, one can also search these phases in <i>The
Materials Project</i> and find the so-called energy above hull. This is the DFT-calculated
energy difference between this phase and the most stable phase(s) containing the same
elements. In principle, if this energy is above 0, it means that the phase is metastable
according to DFT and may eventually decompose. However, some of these phases have been
synthesiszed and are stable, so this value just gives a first indication.

Finally, kinetic limitations also play a role, which are completely neglected herein, as
DFT calculations are performed for a temperature of 0 K. Especially at low temperatures
(below 350-600 °C), the phase may never be oxidized to the level predicted by
thermodynamic calculations. Therefore, one should be especially careful when looking for
materials to be applied in this temperature range, especially if they have very low redox
enthalpies (chemical energy per mol of redox material).

<b>This checklist may be helpful to evaluate whether a material suggested in the <i>Energy
Analysis</i> section is actually a good choice:</b>

* Is the phase a stable perovskite (ionic structure)? What are its expected physical
    properties (compare literature on similar phases)?
* May the oxidation reaction be kinetically limited? Check if the oxidation temperature is
    high enough. Most perovskites require 350-600 °C to show appreciable oxidation rates.
* Is the energy above hull exceptionally large? Is the predicted redox enthalpy
    reasonable? Check the materials on <i>The Materials Project</i> in terms of the energy
    above hull (-> "Explore Materials" on The Materials Project) and in terms of the redox
    enthalpy (-> "Calculate Reaction")

That being said, we believe that <i>RedoxThermoCSP</i> will make it a lot easier to find
perovskite materials for thermochemical applications. Enjoy using it and feel free to use
the data for your research! Our journal publications (see below) must be attributed.


[^1]: J. Vieten, B. Bulfin, P. Huck, M. Horton, D. Guban, L. Zhu, Youjun L., K. A.
    Persson, M. Roeb, C. Sattler (2019). "Materials design of perovskite solid solutions
    for thermochemical applications" **Energy & Environmental Science** (accepted
    article), [10.1039/C9EE00085B](http://dx.doi.org/10.1039/C9EE00085B)
[^2]: J. Vieten et al. (2019). "Redox behavior of solid solutions in the
    SrFe<sub>1-x</sub>Cu<sub>x</sub>O<sub>3-δ</sub> system for application in
    thermochemical oxygen storage and air separation" **Energy Technology** 7(1):
    131-139., [10.1002/ente.201800554](http://dx.doi.org/10.1002/ente.201800554)
[^3]: J. Vieten, B. Bulfin, M. Senholdt, M. Roeb, C. Sattler, M. Schmücker (2017). "Redox
  thermodynamics and phase composition in the system SrFeO3−δ — SrMnO3−δ." **Solid State
  Ionics 308**: 149-155., [10.1016/j.ssi.2017.06.014](https://doi.org/10.1016/j.ssi.2017.06.014)
[^4]: B. Bulfin, L. Hoffmann, L. de Oliveira, N. Knoblauch, F. Call, M. Roeb, C. Sattler,
  M. Schmücker (2016). "Statistical thermodynamics of non-stoichiometric ceria and ceria
  zirconia solid solutions" **Physical Chemistry Chemical Physics 18**(33):
  23147-23154., [10.1039/c6cp03158g](http://dx.doi.org/10.1039/c6cp03158g)
[^5]: K. Eda, K. Furusawa, F. Hatayama, S. Takagi, N. Sotani (1991). "Formation of
  Na<sub>0.9</sub>Mo<sub>6</sub>O<sub>17</sub> in a Solid-Phase Process. Transformations
  of a Hydrated Soldium Molybdenum Bronze,
  Na<sub>0.23</sub>(H<sub>2</sub>O)<sub>0.78</sub>MoO<sub>3</sub>, with Heat Treatments in
  a Nitrogen Atmosphere" <u>Bull. Chem. Soc. Jpn.</u> <b>64</b>(99): 161-164., <a
  href="http://dx.doi.org/10.1246/bcsj.64.161">DOI: 10.1246/bcsj.64.161</a>
