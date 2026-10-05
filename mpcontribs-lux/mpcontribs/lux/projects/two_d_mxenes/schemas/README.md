# two_d_mxenes schemas: field reference

These pydantic models are the data contract for the `two_d_mxenes` MPContribs project. Every uploaded record is an `MXeneEntry` and must validate against them. Labelling rules and background are in the [project README](../README.md); how records are built and uploaded is in [`pipelines/README.md`](../pipelines/README.md).

| module | models | role |
|---|---|---|
| `labels.py` | `MXeneLabel`; `expected_core_sequence`, `expected_termination_coordination` | chemistry and stacking labels and the rules linking them to geometry |
| `structure.py` | `MXeneStructure`, `StructureDescriptors`; `plain_formula` | stored structure, and everything computed from it |
| `properties.py` | `MXeneProperties`, `Energetics`, `ElasticProperties` | energetics and elastic properties supplied in the properties spreadsheet, and the quantities derived from them |
| `calculation.py` | `CalculationSettings` | DFT settings, recorded once per project |
| `mxene.py` | `MXeneEntry`; `infer_chemistry` | the full record and the label/structure cross-checks |

Conventions:

- Field names are camelCase without underscores, as MPContribs requires.
- Units are stated in every description: Å for lengths, eV/atom for energies (meV/atom for the relative stacking energy), N/m for 2D elastic constants and moduli, mg/m² for areal density.
- All models forbid unknown fields (`extra="forbid"`) and reject NaN and infinity.
- Every model converts to Apache Arrow (checked by `tests/test_models_for_arrow_compatibility.py`), so records can be stored as Parquet.
- "Required: no" fields may be null; in `properties` they are null when the spreadsheet cell is blank.

## Validation performed on construction

- `MXeneLabel`: M must be a transition metal; the stacking must be allowed for n (`t`/`h` for n = 1; `t`/`h1a`/`h1b`/`h2` for n ≥ 2); `terminationSite` is set if and only if `termination` is set.
- `MXeneStructure`: `species` and `fracCoords` have equal length, element symbols are valid, lattice vectors a and b lie in the xy plane.
- `MXeneEntry`: the composition matches the labels; the measured core coordination sequence matches `stacking`; the measured outer-metal coordination matches `terminationSite` on both surfaces.
- `StructureDescriptors.from_structure` raises if an atomic layer contains more than one element.

## Models

### `MXeneEntry`

A single MXene: its labels, relaxed structure and properties.

| field | type | required | description |
|---|---|---|---|
| `mxeneId` | `str` | yes | Unique identifier within this project: formula plus folder label, e.g. `Hf2CF2-h-1` or `Ti3C2-h1a`. |
| `labels` | `MXeneLabel` | yes | Chemistry and stacking labels of this MXene. |
| `structure` | `MXeneStructure` | yes | Relaxed slab structure (from a VASP CONTCAR). |
| `descriptors` | `StructureDescriptors` | yes | Geometric descriptors computed from `structure`. |
| `properties` | `MXeneProperties` or null | no | Computed properties: energetics and elastic constants. |

### `MXeneLabel`

Chemical and structural labels that identify one MXene variant.

| field | type | required | description |
|---|---|---|---|
| `metal` | `str` | yes | Symbol of the transition metal M, e.g. `Ti`. |
| `nonmetal` | `Literal['C', 'N']` | yes | Symbol of the X element: `C` (carbide) or `N` (nitride). |
| `termination` | `Literal['F', 'O']` or null | no | Symbol of the surface termination T, or null for a pristine (unterminated) MXene. |
| `n` | `Literal[1, 2, 3]` | yes | Thickness index n in M_{n+1}X_n: the number of X layers (1 for M2X, 2 for M3X2, 3 for M4X3). |
| `stacking` | `Literal['t', 'h', 'h1a', 'h1b', 'h2']` | yes | Stacking label of the metal/X layers as defined by the MXene nomenclature: `t` (all octahedral), `h` or `h2` (all prismatic), `h1a` (O-P-O...), `h1b` (P-O-P...). `h` is used only for n=1 and `h1a`, `h1b`, `h2` only for n>=2. |
| `terminationSite` | `Literal[1, 2]` or null | no | Termination site (the `-1`/`-2` suffix of the label). For n=1, 1 = octahedral and 2 = prismatic outer metal layers; for n>=2, 1 = same coordination as the inner metal layers and 2 = opposite. Required for terminated MXenes and null for pristine ones. |

### `MXeneStructure`

Relaxed slab structure, stored in an Arrow/Parquet-friendly form.

| field | type | required | description |
|---|---|---|---|
| `lattice` | 3×3 `float` | yes | 3x3 matrix of lattice vectors in Å; rows are a, b, c. a and b lie in the plane of the sheet and c spans the sheet plus vacuum. |
| `species` | `list[str]` | yes | Element symbol of each site, in the same order as `fracCoords`. |
| `fracCoords` | list of `[x, y, z]` | yes | Fractional coordinates of each site with respect to `lattice`. |

### `StructureDescriptors`

Geometric descriptors computed directly from the relaxed structure.

| field | type | required | description |
|---|---|---|---|
| `reducedFormula` | `str` | yes | Reduced chemical formula of the slab in M, X, T order, e.g. `Hf2CF2` or `Ti3C2O2`. |
| `nSites` | `int` | yes | Number of sites in the simulation cell. |
| `a` | `float` | yes | Length of in-plane lattice vector a, in Å. |
| `b` | `float` | yes | Length of in-plane lattice vector b, in Å. |
| `gamma` | `float` | yes | Angle between in-plane lattice vectors a and b, in degrees. |
| `cellArea` | `float` | yes | In-plane area of the simulation cell \|a × b\|, in Å^2. |
| `areaPerFormulaUnit` | `float` | yes | In-plane area per M_{n+1}X_nT_x formula unit, in Å^2. |
| `arealMassDensity` | `float` | yes | Mass per unit sheet area, in mg/m^2. |
| `thickness` | `float` | yes | Distance along z between the lowest and highest atomic nuclei of the sheet, in Å (does not include atomic radii). |
| `vacuum` | `float` | yes | Vacuum gap between periodic images of the sheet along z, in Å (cell height along the normal minus `thickness`). |
| `layerSequence` | `list[str]` | yes | Element of each atomic layer from bottom to top, e.g. [`F`, `Hf`, `C`, `Hf`, `F`]. |
| `coordinationSequence` | `list[str]` | yes | Coordination of each interior layer from bottom to top: `O` (octahedral) if the layers directly below and above it are staggered, `P` (trigonal prismatic) if they are eclipsed. The first and last layers have no entry. |
| `metalNonmetalBondLength` | `float` | yes | Mean nearest-neighbour M-X distance over all M sites, in Å. |
| `metalTerminationBondLength` | `float` or null | no | Mean nearest-neighbour T-M distance over all T sites, in Å. Null for pristine MXenes. |
| `spaceGroupSymbol` | `str` | yes | Hermann-Mauguin symbol of the space group of the periodic slab model, determined with spglib (symprec=0.1 Å). |
| `spaceGroupNumber` | `int` | yes | International number of `spaceGroupSymbol`. |

### `MXeneProperties`

All computed properties reported for one MXene.

| field | type | required | description |
|---|---|---|---|
| `energetics` | `Energetics` or null | no | DFT energies of the relaxed structure. |
| `elastic` | `ElasticProperties` or null | no | In-plane elastic constants and moduli. |

### `Energetics`

Energies of the relaxed MXene from DFT.

| field | type | required | description |
|---|---|---|---|
| `totalEnergyPerAtom` | `float` or null | no | DFT total energy of the relaxed slab per atom, in eV/atom. |
| `formationEnergyPerAtom` | `float` or null | no | Formation energy per atom relative to the elemental reference states given in the project description, in eV/atom. |
| `relativeStackingEnergy` | `float` or null | no | Total energy per atom relative to the lowest-energy stacking with the same composition (same M, X, T and n), in meV/atom. Zero for the most stable stacking. |

### `ElasticProperties`

In-plane (2D) elastic properties of the sheet.

| field | type | required | description |
|---|---|---|---|
| `c11` | `float` or null | no | 2D elastic constant C11, in N/m. |
| `c12` | `float` or null | no | 2D elastic constant C12, in N/m. |
| `c66` | `float` or null | no | 2D elastic constant C66 (in-plane shear), in N/m. |
| `youngsModulus` | `float` or null | no | In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m. |
| `poissonRatio` | `float` or null | no | In-plane Poisson's ratio C12 / C11 (dimensionless). |
| `shearModulus` | `float` or null | no | In-plane 2D shear modulus, equal to C66, in N/m. |
| `mechanicallyStable` | `bool` or null | no | Whether the Born stability criteria for a hexagonal sheet are satisfied: C11 > 0, C11 > /C12/ and C66 > 0. |

### `CalculationSettings`

DFT settings used to relax the structures and compute properties.

| field | type | required | description |
|---|---|---|---|
| `code` | `str` or null | no | Simulation code, e.g. `VASP`. |
| `codeVersion` | `str` or null | no | Version of the simulation code, e.g. `5.4.4`. |
| `functional` | `str` or null | no | Exchange-correlation functional, e.g. `PBE`. |
| `vdwCorrection` | `str` or null | no | Dispersion correction, e.g. `DFT-D3`, or null if none. |
| `pseudopotentials` | `list[str]` or null | no | Pseudopotential (e.g. PAW POTCAR) labels used for each element. |
| `energyCutoff` | `float` or null | no | Plane-wave kinetic energy cutoff, in eV. |
| `kpointMesh` | `list[int]` or null | no | Monkhorst-Pack or Gamma-centred k-point mesh for relaxations. |
| `spinPolarized` | `bool` or null | no | Whether calculations were spin-polarized. |
| `electronicConvergence` | `float` or null | no | Electronic (SCF) energy convergence, in eV. |
| `forceConvergence` | `float` or null | no | Maximum residual force on any atom after relaxation, in eV/Å. |
| `elasticMethod` | `str` or null | no | How elastic constants were obtained, e.g. `energy-strain fitting with +/-2% strain`. |

## Regenerating this reference

The tables above are generated from the models' field descriptions. After changing a model, regenerate them so that code and documentation stay identical: print `Model.model_fields` (name, `annotation`, `is_required()`, `description`) for each model, in the order above.
