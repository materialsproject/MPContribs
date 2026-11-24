# two_d_mxenes schemas: field reference

These pydantic models are the data contract for the `two_d_mxenes` MPContribs project. `MXeneEntry` is exactly the `data` of one contribution; the relaxed structure is submitted alongside it as a pymatgen `Structure` in the contribution's `structures` component. Labelling rules and validation phases are in the [project README](../README.md); the code that builds and uploads entries is described in [`pipelines/README.md`](../pipelines/README.md).

| module | contents | role |
|---|---|---|
| `labels.py` | `MXeneLabel`; `parse_folder_label`, `join_elements`, `split_elements`, `expected_core_sequence`, `expected_termination_coordination` | chemistry and stacking labels, and the rules linking them to geometry |
| `descriptors.py` | `StructureDescriptors`; `UNIT`, `space_group_numbers` | geometric descriptors of the relaxed structure |
| `properties.py` | `MXeneProperties`, `Energetics`, `ElasticProperties`; `derived_elastic_properties`, `is_isotropic` | energetics and elastic properties, and the quantities derived from them |
| `provenance.py` | `Provenance` | calculation method of an entry (DFT or a machine-learning interatomic potential) |
| `mxene.py` | `MXeneEntry` | the data of one contribution, cross-validated |

Conventions:

- Every field is a scalar or a short string; the schema has no list fields. Element lists are strings ordered by atomic number and joined by `-` (e.g. `Ti-V-Nb-Mo`, `C-N`, `O-F`); sequences are strings joined by `-` (e.g. `F-Hf-C-Hf-F`, `O-P-O`), with the elements of a mixed layer joined by `/` (e.g. `Ti/V`).
- Every string field is a `Literal` vocabulary or has a pattern and a maximum length. Numeric fields have physical bounds.
- Numeric fields declare their unit as `json_schema_extra={"unit": ...}` (`""` for dimensionless); text fields have no unit. Integers that are categories rather than quantities (`terminationSite`, `configuration`, `spaceGroupNumber`) declare no unit and are stored as text columns, so they display as `1` or `187` rather than as floats; ordered quantities (`n`, `nMetals`, `nSites`) are dimensionless numbers that support range filters. The MPContribs column definitions are generated from this metadata.
- Field names are camelCase without underscores, as MPContribs requires.
- Each model declares `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)`: unknown fields, NaN and infinity are rejected.
- Every model converts to Apache Arrow (checked by `tests/test_models_for_arrow_compatibility.py`).
- The schemas contain no code that operates on structures or files; that code is in `pipelines/`.

## Validation performed on construction

- `MXeneLabel`: every metal is one of the 40 transition metals and every termination one of `Termination`; element lists are distinct and ordered by atomic number; `nMetals` counts `metals`; the stacking is allowed for n (`t`/`h` for n = 1; `t`/`h1a`/`h1b`/`h2` for n ≥ 2); `terminationSite` is set if and only if `terminations` is set.
- `StructureDescriptors`: bounds, patterns and lengths as listed below; `spaceGroupSymbol` is a short Hermann–Mauguin symbol produced by spglib and matches `spaceGroupNumber`; `coordinationSequence` has one entry per interior layer of `layerSequence`.
- `ElasticProperties`: `c11` and `c12` are given together; `c11` is nonzero (a negative value is accepted and marks an unstable sheet); `c22` requires `c66`; Young's modulus and Poisson's ratio are given only for C22 = C11; when present, `c66`, the moduli and `mechanicallyStable` are consistent with them; derived values without `c11` and `c12` are rejected.
- `Provenance`: `potential` is given if and only if `method` is `MLIP`.
- `MXeneEntry`: `mxeneId` is `<reducedFormula>-<label>`; the formula holds exactly the labelled elements in M_{n+1}X_n(T_2) proportions; every layer of the layer sequence holds elements of its role (T, M, X), and the layers together hold every labelled element; `metalArrangement` matches the metal layers; the core coordination sequence matches `stacking`; the outer-metal coordination matches `terminationSite` on both surfaces; elastic data of a non-hexagonal cell (space group outside 143–194) includes `c22`, and a hexagonal cell has C22 = C11.

## Models

### `MXeneEntry`

Contribution data for one MXene: labels, descriptors and properties.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `mxeneId` | `str` | – | length ≤ 96; pattern `^(?:[A-Z][a-z]?[0-9]{0,3}){2,16}-(?:h1a\|h1b\|h2\|h\|t)(?:-[12])?(?:-c[1-9][0-9]{0,2})?$` | yes | Unique identifier within this project: reduced formula plus folder label, e.g. `Hf2CF2-h-1`, `Ti3C2-h1a` or `TiVNbMoC3O2-t-1-c2`. |
| `labels` | `MXeneLabel` | – |  | yes | Chemistry and stacking labels of this MXene. |
| `descriptors` | `StructureDescriptors` | – |  | yes | Geometric descriptors computed from the relaxed structure. |
| `provenance` | `Provenance` | – |  | no | Method used to relax the structure and compute the properties (DFT unless stated otherwise). |
| `properties` | `MXeneProperties or None` | – |  | no | Computed properties: energetics and elastic constants. |

### `MXeneLabel`

Chemical and structural labels that identify one MXene variant.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `metals` | `str` | – | length ≤ 29; pattern `^[A-Z][a-z]?(?:-[A-Z][a-z]?){0,9}$` | yes | Transition metals M, by atomic number and joined by `-`, e.g. `Ti` (single metal), `Ti-Mo` (double metal) or `Ti-V-Nb-Mo` (high entropy). |
| `nMetals` | `int` | dimensionless | ≥ 1; ≤ 10 | yes | Number of distinct transition metals (1 for a single-metal MXene; 4 or more is usually called high entropy). |
| `nonmetals` | `Literal['C', 'N', 'C-N']` | – |  | yes | X elements: `C` (carbide), `N` (nitride) or `C-N` (carbonitride). |
| `terminations` | `str or None` | – | length ≤ 11; pattern `^[A-Z][a-z]?(?:-[A-Z][a-z]?){0,3}$` | no | Termination elements T, by atomic number and joined by `-`, e.g. `O` or `O-F`; null for a pristine (unterminated) MXene. |
| `n` | `Literal[1, 2, 3, 4]` | dimensionless |  | yes | Thickness index n in M_{n+1}X_n: the number of X layers (1 for M2X, 2 for M3X2, 3 for M4X3, 4 for M5X4). |
| `stacking` | `Literal['t', 'h', 'h1a', 'h1b', 'h2']` | – |  | yes | Stacking label of the metal/X layers: `t` (all octahedral), `h` or `h2` (all prismatic), `h1a` (O-P-O...), `h1b` (P-O-P...). `h` is used only for n=1 and `h1a`, `h1b`, `h2` only for n>=2. |
| `terminationSite` | `Literal[1, 2] or None` | – |  | no | Termination site (the `-1`/`-2` suffix of the label). For n=1, 1 = octahedral and 2 = prismatic outer metal layers; for n>=2, 1 = same coordination as the inner metal layers and 2 = opposite. Required for terminated MXenes and null for pristine ones. Stored as a label (text column), not as a quantity. |
| `configuration` | `int or None` | – | ≥ 1; ≤ 999 | no | Index of the atomic arrangement (the `-c<k>` suffix of the label), distinguishing structures with the same composition and stacking, e.g. special quasirandom structures of a solid solution. Null if the label has no such suffix. Stored as a label (text column), not as a quantity. |

### `StructureDescriptors`

Geometric descriptors computed directly from the relaxed structure.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `reducedFormula` | `str` | – | length ≤ 80; pattern `^(?:[A-Z][a-z]?[0-9]{0,3}){2,16}$` | yes | Reduced chemical formula of the slab: metals, then X, then terminations, each group by atomic number, e.g. `Hf2CF2`, `Ti3C2O2` or `TiMo2C2`. |
| `nSites` | `int` | dimensionless | ≥ 3; ≤ 10000 | yes | Number of sites in the simulation cell. |
| `a` | `float` | Å | > 0; ≤ 100 | yes | Length of in-plane lattice vector a, in Å. |
| `b` | `float` | Å | > 0; ≤ 100 | yes | Length of in-plane lattice vector b, in Å. |
| `gamma` | `float` | degree | > 0; < 180 | yes | Angle between in-plane lattice vectors a and b, in degrees. |
| `cellArea` | `float` | Å**2 | > 0 | yes | In-plane area of the simulation cell /a x b/, in Å². |
| `areaPerFormulaUnit` | `float` | Å**2 | > 0 | yes | In-plane area per M_{n+1}X_nT_x formula unit, in Å². |
| `arealMassDensity` | `float` | mg/m**2 | > 0 | yes | Mass per unit sheet area, in mg/m². |
| `thickness` | `float` | Å | > 0; ≤ 50 | yes | Distance along the normal between the lowest and highest atomic nuclei of the sheet, in Å (atomic radii not included). |
| `vacuum` | `float` | Å | > 0 | yes | Vacuum gap between periodic images of the sheet along the normal, in Å (cell height minus `thickness`). |
| `layerSequence` | `str` | – | length ≤ 256; pattern `^[A-Z][a-z]?(?:/[A-Z][a-z]?){0,9}(?:-[A-Z][a-z]?(?:/[A-Z][a-z]?){0,9}){2,10}$` | yes | Elements of each atomic layer from bottom to top, joined by `-`; a mixed layer lists its elements by atomic number joined by `/`, e.g. `F-Hf-C-Hf-F`, `Mo-C-Ti-C-Mo` or `Ti/V-C-Ti/V`. |
| `coordinationSequence` | `str` | – | length ≤ 17; pattern `^[OP](?:-[OP]){0,8}$` | yes | Coordination of each interior layer from bottom to top, joined by `-`: `O` (octahedral) if the layers directly below and above it are staggered, `P` (trigonal prismatic) if they are eclipsed, e.g. `O-P-O`. The outermost layers have no entry. |
| `metalArrangement` | `Literal['single', 'out-of-plane ordered', 'in-plane mixed']` | – |  | yes | Distribution of the metals over the metal layers: `single` (one metal), `out-of-plane ordered` (each metal layer holds one element, e.g. Mo2TiC2) or `in-plane mixed` (at least one metal layer holds several elements: in-plane ordered or solid solution). |
| `metalNonmetalBondLength` | `float` | Å | > 0; ≤ 5 | yes | Mean nearest-neighbour M-X distance over all M sites, in Å. |
| `metalTerminationBondLength` | `float or None` | Å | > 0; ≤ 5 | no | Mean nearest-neighbour T-M distance over all T sites, in Å. Null for pristine MXenes. |
| `spaceGroupSymbol` | `str` | – | length ≤ 12 | yes | Short Hermann-Mauguin symbol of the space group of the periodic slab model, as determined by spglib, e.g. `P-6m2`. |
| `spaceGroupNumber` | `int` | – | ≥ 1; ≤ 230 | yes | International number of `spaceGroupSymbol`. Stored as a label (text column), not as a quantity. |

### `Provenance`

Calculation method of one entry.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `method` | `Literal['DFT', 'MLIP']` | – |  | no | Method used to relax the structure and compute the properties: `DFT` (settings in the project metadata) or `MLIP` (machine-learning interatomic potential named in `potential`). |
| `potential` | `str or None` | – | length ≤ 64; pattern `^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$` | no | Name and version of the machine-learning interatomic potential, e.g. `MACE-MP-0-medium`. Required for `MLIP` and null for `DFT`. |

### `MXeneProperties`

All computed properties reported for one MXene.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `energetics` | `Energetics or None` | – |  | no | Energies of the relaxed structure. |
| `elastic` | `ElasticProperties or None` | – |  | no | In-plane elastic constants and moduli. |

### `Energetics`

Energies of the relaxed MXene.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `totalEnergyPerAtom` | `float or None` | eV/atom | ≥ -100; ≤ 100 | no | Total energy of the relaxed slab per atom, in eV/atom, from the method in `provenance`. |
| `formationEnergyPerAtom` | `float or None` | eV/atom | ≥ -20; ≤ 20 | no | Formation energy per atom relative to the elemental reference states given in the project description, in eV/atom. |
| `relativeStackingEnergy` | `float or None` | meV/atom | ≥ 0; ≤ 10000 | no | Total energy per atom relative to the lowest-energy structure in this project with the same reduced formula and the same method (any stacking or configuration), in meV/atom. Zero for the most stable one. |

### `ElasticProperties`

In-plane (2D) elastic properties of the sheet.

| field | type | unit | limits | required | description |
|---|---|---|---|---|---|
| `c11` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C11, in N/m. Nonzero. |
| `c12` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C12, in N/m. |
| `c22` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C22, in N/m. Given for non-hexagonal cells (with C66); null for hexagonal sheets, where C22 = C11. |
| `c66` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | 2D elastic constant C66 (in-plane shear), in N/m. |
| `youngsModulus` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | In-plane 2D Young's modulus (C11^2 - C12^2) / C11, in N/m. Defined for isotropic sheets (C22 = C11) only. |
| `poissonRatio` | `float or None` | dimensionless | ≥ -10; ≤ 10 | no | In-plane Poisson's ratio C12 / C11 (dimensionless). Defined for isotropic sheets (C22 = C11) only. |
| `shearModulus` | `float or None` | N/m | ≥ -10000; ≤ 10000 | no | In-plane 2D shear modulus, equal to C66, in N/m. |
| `mechanicallyStable` | `bool or None` | – |  | no | Whether the Born stability criteria are satisfied: C11 > 0, C66 > 0 and C11 C22 > C12^2 (C11 > /C12/ when C22 = C11). |

## Regenerating this reference

The tables are generated from the models: for each field, its annotation, the `unit` in `json_schema_extra`, the constraints in `FieldInfo.metadata`, `is_required()` and the description. Regenerate them after changing a model so that code and documentation stay identical.
