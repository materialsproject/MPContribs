# CoRE MOF Lux schemas

These Pydantic models describe the released CoRE MOF v26.0.2 artifacts. The
canonical join key is the exact release-preserved `structure_id`; row order,
formula, common name, topology, and `source_id` are not join keys.

## Models

| Model | Released artifact | Relationship | v26.0.2 rows |
| --- | --- | --- | ---: |
| `StructureRegistryRecord` | structure-name registry | one per structure | 42,574 |
| `CifManifestRecord` | CIF integrity manifest | one per structure | 42,574 |
| `MetadataRecord` | chemistry and checker summary | one per structure | 42,574 |
| `ZeoFeaturesRecord` | pore, periodicity, and OMS features | one per structure | 42,574 |
| `TopologyRecord` | nested CrystalNets result | one per structure | 42,574 |
| `CheckerFindingRecord` | individual checker result | five per structure | 212,870 |
| `CalculationDiagnosticRecord` | failed/partial calculations | zero to four per structure | 49,028 |

`CheckerFindingRecord.detail_errors` and `raw_prediction_output` retain their
source JSON serialization as strings. The five checkers publish different
nested payload shapes; storing the strings keeps the combined table
Arrow-compatible while validators still require valid JSON objects and a
consistent operational vote.

These schemas do not grant permission to redistribute or upload CIF files.
Data publication and upload remain separate approval steps.
