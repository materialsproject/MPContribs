# two_d_mxenes schemas: field reference

These pydantic models are the data contract for the `two_d_mxenes` MPContribs project. `MXeneEntry` is exactly the `data` of one contribution; the relaxed structure is submitted alongside it as a pymatgen `Structure` in the contribution's `structures` component. Labelling rules and validation phases are in the [project README](../README.md); the code that builds and uploads entries is described in [`pipelines/README.md`](../pipelines/README.md).

| module | contents | role |
|---|---|---|
| `labels.py` | `MXeneLabel`; `parse_folder_label`, `expected_core_sequence`, `expected_termination_coordination` | chemistry and stacking labels, and the rules linking them to geometry |
| `descriptors.py` | `StructureDescriptors`; `UNIT`, `space_group_numbers` | geometric descriptors of the relaxed structure |
| `properties.py` | `MXeneProperties`, `Energetics`, `ElasticProperties`; `derived_elastic_properties` | energetics and elastic properties, and the quantities derived from them |
| `mxene.py` | `MXeneEntry` | the data of one contribution, cross-validated |

Conventions:

- Every field is a scalar or a short string; the schema has no list fields. Sequences are strings joined by `-` (e.g. `F-Hf-C-Hf-F`, `O-P-O`).
- Every string field is a `Literal` vocabulary or has a pattern and a maximum length. Numeric fields have physical bounds.
- Numeric fields declare their unit as `json_schema_extra={"unit": ...}` (`""` for dimensionless); text fields have no unit. The MPContribs column definitions are generated from this metadata.
- Field names are camelCase without underscores, as MPContribs requires.
- Each model declares `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)`: unknown fields, NaN and infinity are rejected.
- Every model converts to Apache Arrow (checked by `tests/test_models_for_arrow_compatibility.py`).
- The schemas contain no code that operates on structures or files; that code is in `pipelines/`.

## Validation performed on construction

- `MXeneLabel`: M is one of the 40 transition metals; the stacking is allowed for n (`t`/`h` for n = 1; `t`/`h1a`/`h1b`/`h2` for n ≥ 2); `terminationSite` is set if and only if `termination` is set.
- `StructureDescriptors`: bounds, patterns and lengths as listed below; `spaceGroupSymbol` is a short Hermann–Mauguin symbol produced by spglib and matches `spaceGroupNumber`; `coordinationSequence` has one entry per interior layer of `layerSequence`.
- `ElasticProperties`: `c11` and `c12` are given together; when present, `c66`, the moduli and `mechanicallyStable` are consistent with them; derived values without `c11` and `c12` are rejected.
- `MXeneEntry`: `mxeneId` is `<formula>-<label>`; the formula and layer sequence match the labels; the core coordination sequence matches `stacking`; the outer-metal coordination matches `terminationSite` on both surfaces.

## Models

### `MXeneEntry`

Contribution data for one MXene: labels, descriptors and properties.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `mxeneId` | `str` | – | length ≤ 20; pattern `^[A-Z][a-z]?[2-4][CN][2-3]?(?:[FO]2)?-(?:h1a\|h1b\|h2\|h\|t)(?:-[12])?$` | yes | Unique identifier within this project: formula plus folder label, e.g. `Hf2CF2-h-1` or `Ti3C2-h1a`. |
| `labels` | `MXeneLabel` | – |  | yes | Chemistry and stacking labels of this MXene. |
| `descriptors` | `StructureDescriptors` | – |  | yes | Geometric descriptors computed from the relaxed structure. |
| `properties` | `MXeneProperties or None` | – |  | no | Computed properties: energetics and elastic constants. |

### `MXeneLabel`

Chemical and structural labels that identify one MXene variant.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `metal` | `Literal[...40 transition metals]` | – |  | yes | Symbol of the transition metal M, e.g. `Ti`. |
| `nonmetal` | `Literal['C', 'N']` | – |  | yes | Symbol of the X element: `C` (carbide) or `N` (nitride). |
| `termination` | `Literal['F', 'O'] or None` | – |  | no | Symbol of the surface termination T, or null for a pristine (unterminated) MXene. |
| `n` | `Literal[1, 2, 3]` | dimensionless |  | yes | Thickness index n in M_{n+1}X_n: the number of X layers (1 for M2X, 2 for M3X2, 3 for M4X3). |
| `stacking` | `Literal['t', 'h', 'h1a', 'h1b', 'h2']` | – |  | yes | Stacking label of the metal/X layers: `t` (all octahedral), `h` or `h2` (all prismatic), `h1a` (O-P-O...), `h1b` (P-O-P...). `h` is used only for n=1 and `h1a`, `h1b`, `h2` only for n>=2. |
| `terminationSite` | `Literal[1, 2] or None` | dimensionless |  | no | Termination site (the `-1`/`-2` suffix of the label). For n=1, 1 = octahedral and 2 = prismatic outer metal layers; for n>=2, 1 = same coordination as the inner metal layers and 2 = opposite. Required for terminated MXenes and null for pristine ones. |

### `StructureDescriptors`

Geometric descriptors computed directly from the relaxed structure.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `reducedFormula` | `str` | – | length ≤ 16; pattern `^(?:[A-Z][a-z]?[0-9]{0,2}){2,3}$` | yes | Reduced chemical formula of the slab in M, X, T order, e.g. `Hf2CF2` or `Ti3C2O2`. |
| `nSites` | `int` | dimensionless | ≥ 3; ≤ 10000 | yes | Number of sites in the simulation cell. |
| `a` | `float` | Å | > 0; ≤ 100 | yes | Length of in-plane lattice vector a, in Å. |
| `b` | `float` | Å | > 0; ≤ 100 | yes | Length of in-plane lattice vector b, in Å. |
| `gamma` | `float` | degree | > 0; < 180 | yes | Angle between in-plane lattice vectors a and b, in degrees. |
| `cellArea` | `float` | Å**2 | > 0 | yes | In-plane area of the simulation cell /a x b/, in Å². |
| `areaPerFormulaUnit` | `float` | Å**2 | > 0 | yes | In-plane area per M_{n+1}X_nT_x formula unit, in Å². |
| `arealMassDensity` | `float` | mg/m**2 | > 0 | yes | Mass per unit sheet area, in mg/m². |
| `thickness` | `float` | Å | > 0; ≤ 50 | yes | Distance along the normal between the lowest and highest atomic nuclei of the sheet, in Å (atomic radii not included). |
| `vacuum` | `float` | Å | > 0 | yes | Vacuum gap between periodic images of the sheet along the normal, in Å (cell height minus `thickness`). |
| `layerSequence` | `str` | – | length ≤ 32; pattern `^[A-Z][a-z]?(?:-[A-Z][a-z]?){2,8}$` | yes | Element of each atomic layer from bottom to top, joined by `-`, e.g. `F-Hf-C-Hf-F`. |
| `coordinationSequence` | `str` | – | length ≤ 17; pattern `^[OP](?:-[OP]){0,8}$` | yes | Coordination of each interior layer from bottom to top, joined by `-`: `O` (octahedral) if the layers directly below and above it are staggered, `P` (trigonal prismatic) if they are eclipsed, e.g. `O-P-O`. The outermost layers have no entry. |
| `metalNonmetalBondLength` | `float` | Å | > 0; ≤ 5 | yes | Mean nearest-neighbour M-X distance over all M sites, in Å. |
| `metalTerminationBondLength` | `float or None` | Å | > 0; ≤ 5 | no | Mean nearest-neighbour T-M distance over all T sites, in Å. Null for pristine MXenes. |
| `spaceGroupSymbol` | `str` | – | length ≤ 12 | yes | Short Hermann-Mauguin symbol of the space group of the periodic slab model, as determined by spglib, e.g. `P-6m2`. |
| `spaceGroupNumber` | `int` | dimensionless | ≥ 1; ≤ 230 | yes | International number of `spaceGroupSymbol`. |

### `MXeneProperties`

All computed properties reported for one MXene.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `energetics` | `Energetics or None` | – |  | no | DFT energies of the relaxed structure. |
| `elastic` | `ElasticProperties or None` | – |  | no | In-plane elastic constants and moduli. |

### `Energetics`

Energies of the relaxed MXene from DFT.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `totalEnergyPerAtom` | `float or None` | eV/atom | ≥ -100; ≤ 100 | no | DFT total energy of the relaxed slab per atom, in eV/atom. |
| `formationEnergyPerAtom` | `float or None` | eV/atom | ≥ -20; ≤ 20 | no | Formation energy per atom relative to the elemental reference states given in the project description, in eV/atom. |
| `relativeStackingEnergy` | `float or None` | meV/atom | ≥ 0; ≤ 10000 | no | Total energy per atom relative to the lowest-energy stacking with the same composition (same M, X, T and n), in meV/atom. Zero for the most stable stacking. |

### `ElasticProperties`

In-plane (2D) elastic properties of the sheet.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `c11` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C11, in N/m. |
| `c12` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C12, in N/m. |
| `c66` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C66 (in-plane shear), in N/m. |
| `youngsModulus` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m. |
| `poissonRatio` | `float or None` | dimensionless | ≥ -10; ≤ 10 | no | In-plane Poisson's ratio C12 / C11 (dimensionless). |
| `shearModulus` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | In-plane 2D shear modulus, equal to C66, in N/m. |
| `mechanicallyStable` | `bool or None` | – |  | no | Whether the Born stability criteria for a hexagonal sheet are satisfied: C11 > 0, C11 > /C12/ and C66 > 0. |

## Regenerating this reference

The tables are generated from the models: for each field, its annotation, the `unit` in `json_schema_extra`, the constraints in `FieldInfo.metadata`, `is_required()` and the description. Regenerate them after changing a model so that code and documentation stay identical.
