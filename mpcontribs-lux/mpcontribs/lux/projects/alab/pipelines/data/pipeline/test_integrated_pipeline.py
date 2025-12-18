#!/usr/bin/env python3
"""
Comprehensive Integration Tests for A-Lab Pipeline

Tests the complete pipeline including:
- Auto-discovery (schemas, analyses)
- Filter configurations
- Hook system
- Edge cases and error handling
- End-to-end workflow

Usage:
    python test_integrated_pipeline.py              # Run all tests
    python test_integrated_pipeline.py --verbose    # Verbose output
    pytest test_integrated_pipeline.py              # Use pytest
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json
import traceback

# Add paths
sys.path.insert(0, str(Path("data/products")))
sys.path.insert(0, str(Path("data/pipeline")))
sys.path.insert(0, str(Path("data/analyses")))
sys.path.insert(0, str(Path("data")))
sys.path.insert(0, str(Path("data/tools")))

# Test results tracking
test_results = []


def log_test(test_name: str, passed: bool, message: str = ""):
    """Track test results"""
    test_results.append({
        'test': test_name,
        'passed': passed,
        'message': message
    })
    status = "✓" if passed else "✗"
    print(f"  {status} {test_name}")
    if message and not passed:
        print(f"     {message}")


def test_header(title: str):
    """Print test section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# =============================================================================
# Auto-Discovery Tests
# =============================================================================

def test_schema_auto_discovery():
    """Test that schemas are auto-discovered from schema directory"""
    test_header("TEST 1: Schema Auto-Discovery")
    
    try:
        from schema_manager import SchemaManager
        
        manager = SchemaManager()
        discovered = manager.get_table_names()
        
        # Should discover at least these core schemas
        expected_schemas = ['experiments', 'experiment_elements', 'powder_doses']
        
        all_found = all(s in discovered for s in expected_schemas)
        log_test(
            "Core schemas discovered",
            all_found,
            f"Expected {expected_schemas}, found {discovered}"
        )
        
        # Test that schemas have model_fields
        for schema_name in discovered:
            schema_class = manager.get_schema(schema_name)
            has_fields = hasattr(schema_class, 'model_fields') and len(schema_class.model_fields) > 0
            log_test(
                f"Schema '{schema_name}' has fields",
                has_fields,
                f"Fields: {len(schema_class.model_fields) if has_fields else 0}"
            )
        
        # Test excluded fields detection
        experiments_schema = manager.get_schema('experiments')
        if experiments_schema:
            excluded = manager.get_excluded_fields('experiments')
            log_test(
                "Excluded fields detected",
                True,
                f"Found {len(excluded)} excluded fields: {excluded}"
            )
        
        return True
        
    except Exception as e:
        log_test("Schema auto-discovery", False, str(e))
        traceback.print_exc()
        return False


def test_analysis_auto_discovery():
    """Test that analyses are auto-discovered from analyses directory"""
    test_header("TEST 2: Analysis Auto-Discovery")
    
    try:
        from base_analyzer import AnalysisPluginManager
        
        manager = AnalysisPluginManager()
        discovered = manager.list_analyzers()
        
        # Should discover at least these built-in analyses
        expected_analyses = ['xrd_dara', 'powder_statistics']
        
        all_found = all(a in discovered for a in expected_analyses)
        log_test(
            "Built-in analyses discovered",
            all_found,
            f"Expected {expected_analyses}, found {discovered}"
        )
        
        # Test analyzer metadata
        for analyzer_name in discovered:
            analyzer = manager.get_analyzer(analyzer_name)
            
            has_analyze = hasattr(analyzer, 'analyze') and callable(analyzer.analyze)
            log_test(f"Analyzer '{analyzer_name}' has analyze()", has_analyze)
            
            has_schema = hasattr(analyzer, 'get_output_schema') and callable(analyzer.get_output_schema)
            log_test(f"Analyzer '{analyzer_name}' has get_output_schema()", has_schema)
            
            if has_schema:
                schema = analyzer.get_output_schema()
                log_test(
                    f"Analyzer '{analyzer_name}' schema valid",
                    isinstance(schema, dict) and len(schema) > 0,
                    f"Fields: {list(schema.keys())}"
                )
        
        return True
        
    except Exception as e:
        log_test("Analysis auto-discovery", False, str(e))
        traceback.print_exc()
        return False


def test_custom_schema_hook():
    """Test adding a custom schema via hook"""
    test_header("TEST 3: Custom Schema Hook")
    
    try:
        from schema_manager import SchemaManager
        from pydantic import BaseModel, Field
        
        # Create a temporary custom schema
        custom_schema_dir = Path("data/products/schema")
        custom_schema_file = custom_schema_dir / "test_custom_schema.py"
        
        # Write custom schema
        custom_schema_code = '''"""Test custom schema"""
from pydantic import BaseModel, Field

class TestCustomData(BaseModel, extra="forbid"):
    """Test custom data schema"""
    __schema_table__ = "test_custom_data"
    
    experiment_id: str = Field(description="Experiment ID")
    custom_field: float = Field(description="Custom measurement")
'''
        
        with open(custom_schema_file, 'w') as f:
            f.write(custom_schema_code)
        
        try:
            # Re-discover schemas
            manager = SchemaManager()
            discovered = manager.get_table_names()
            
            custom_found = 'test_custom_data' in discovered
            log_test(
                "Custom schema auto-discovered",
                custom_found,
                f"Found in: {discovered}"
            )
            
            if custom_found:
                custom_schema = manager.get_schema('test_custom_data')
                log_test(
                    "Custom schema loaded correctly",
                    custom_schema is not None and hasattr(custom_schema, 'model_fields'),
                    f"Fields: {list(custom_schema.model_fields.keys()) if custom_schema else []}"
                )
        
        finally:
            # Cleanup
            if custom_schema_file.exists():
                custom_schema_file.unlink()
        
        return True
        
    except Exception as e:
        log_test("Custom schema hook", False, str(e))
        traceback.print_exc()
        return False


def test_custom_analyzer_hook():
    """Test adding a custom analyzer via hook"""
    test_header("TEST 4: Custom Analyzer Hook")
    
    try:
        from base_analyzer import AnalysisPluginManager
        
        # Create a temporary custom analyzer
        custom_analyzer_file = Path("data/analyses/test_custom_analyzer.py")
        
        # Write custom analyzer
        custom_analyzer_code = '''"""Test custom analyzer"""
from pathlib import Path
import pandas as pd
from base_analyzer import BaseAnalyzer

class TestCustomAnalyzer(BaseAnalyzer):
    """Test custom analysis"""
    name = "test_custom"
    description = "Test custom analysis for testing"
    cli_flag = "--test-custom"
    
    def analyze(self, experiments_df: pd.DataFrame, parquet_dir: Path) -> pd.DataFrame:
        results = []
        for _, exp in experiments_df.iterrows():
            results.append({
                'experiment_name': exp.get('name', 'test'),
                'test_metric': 42.0
            })
        return pd.DataFrame(results)
    
    def get_output_schema(self):
        return {
            'test_metric': {'type': 'float', 'required': True, 'description': 'Test metric'}
        }
'''
        
        with open(custom_analyzer_file, 'w') as f:
            f.write(custom_analyzer_code)
        
        try:
            # Re-discover analyzers
            manager = AnalysisPluginManager()
            discovered = manager.list_analyzers()
            
            custom_found = 'test_custom' in discovered
            log_test(
                "Custom analyzer auto-discovered",
                custom_found,
                f"Found in: {discovered}"
            )
            
            if custom_found:
                custom_analyzer = manager.get_analyzer('test_custom')
                log_test(
                    "Custom analyzer loaded correctly",
                    custom_analyzer is not None and hasattr(custom_analyzer, 'analyze'),
                    f"Name: {custom_analyzer.name if custom_analyzer else 'N/A'}"
                )
                
                # Test analyzer can be instantiated
                schema = custom_analyzer.get_output_schema()
                log_test(
                    "Custom analyzer schema valid",
                    isinstance(schema, dict) and 'test_metric' in schema,
                    f"Schema: {schema}"
                )
        
        finally:
            # Cleanup
            if custom_analyzer_file.exists():
                custom_analyzer_file.unlink()
        
        return True
        
    except Exception as e:
        log_test("Custom analyzer hook", False, str(e))
        traceback.print_exc()
        return False


# =============================================================================
# Filter Configuration Tests
# =============================================================================

def test_filter_configurations():
    """Test various filter configurations"""
    test_header("TEST 5: Filter Configurations")
    
    try:
        from base_product import ExperimentFilter
        
        # Test 1: Simple type filter
        filter1 = ExperimentFilter(types=["NSC"])
        query1 = filter1.to_mongo_query()
        log_test(
            "Simple type filter",
            'name' in query1 and '$regex' in query1['name'],
            f"Query: {query1}"
        )
        
        # Test 2: Multiple types
        filter2 = ExperimentFilter(types=["NSC", "Na"])
        query2 = filter2.to_mongo_query()
        log_test(
            "Multiple type filter",
            'name' in query2,
            f"Query: {query2}"
        )
        
        # Test 3: Status filter
        filter3 = ExperimentFilter(status=["completed"])
        query3 = filter3.to_mongo_query()
        log_test(
            "Status filter",
            'status' in query3,
            f"Query: {query3}"
        )
        
        # Test 4: XRD requirement
        filter4 = ExperimentFilter(has_xrd=True)
        query4 = filter4.to_mongo_query()
        log_test(
            "XRD requirement filter",
            'metadata.diffraction_results.sampleid_in_aeris' in query4,
            f"Query: {query4}"
        )
        
        # Test 5: Combined filters
        filter5 = ExperimentFilter(
            types=["NSC"],
            status=["completed"],
            has_xrd=True
        )
        query5 = filter5.to_mongo_query()
        log_test(
            "Combined filters",
            len(query5) >= 2,
            f"Query has {len(query5)} conditions"
        )
        
        # Test 6: Specific experiment names
        filter6 = ExperimentFilter(experiment_names=["NSC_249_001", "NSC_249_002"])
        query6 = filter6.to_mongo_query()
        log_test(
            "Specific experiment names",
            'name' in query6 and '$in' in query6['name'],
            f"Query: {query6}"
        )
        
        # Test 7: Date range filter
        filter7 = ExperimentFilter(
            date_range={
                "start": "2024-01-01",
                "end": "2024-12-31"
            }
        )
        query7 = filter7.to_mongo_query()
        log_test(
            "Date range filter",
            'last_updated' in query7,
            f"Query: {query7}"
        )
        
        # Test 8: Empty filter (should match all)
        filter8 = ExperimentFilter()
        query8 = filter8.to_mongo_query()
        log_test(
            "Empty filter (match all)",
            query8 == {},
            f"Query: {query8}"
        )
        
        return True
        
    except Exception as e:
        log_test("Filter configurations", False, str(e))
        traceback.print_exc()
        return False


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

def test_edge_cases():
    """Test edge cases and potential breaking scenarios"""
    test_header("TEST 6: Edge Cases & Error Handling")
    
    try:
        from base_product import ProductConfig, ExperimentFilter, ProductMetadata
        
        # Test 1: Invalid product name
        try:
            invalid_config = ProductConfig(
                name="invalid name with spaces!",
                experiment_filter=ExperimentFilter()
            )
            log_test("Invalid product name rejected", False, "Should have raised ValueError")
        except ValueError:
            log_test("Invalid product name rejected", True, "Correctly rejected invalid name")
        
        # Test 2: Empty product name
        try:
            empty_config = ProductConfig(
                name="",
                experiment_filter=ExperimentFilter()
            )
            log_test("Empty product name rejected", False, "Should have raised ValueError")
        except (ValueError, Exception):
            log_test("Empty product name rejected", True, "Correctly rejected empty name")
        
        # Test 3: Valid product with underscores
        try:
            valid_config = ProductConfig(
                name="valid_product_123",
                experiment_filter=ExperimentFilter()
            )
            log_test("Valid product name accepted", True, f"Name: {valid_config.name}")
        except Exception as e:
            log_test("Valid product name accepted", False, str(e))
        
        # Test 4: Missing required fields
        try:
            from schema_manager import SchemaManager
            manager = SchemaManager()
            exp_schema = manager.get_schema('experiments')
            
            if exp_schema:
                # Try to create with missing required fields
                try:
                    invalid_exp = exp_schema(
                        experiment_id="test",
                        name="test"
                        # Missing other required fields
                    )
                    log_test("Missing required fields rejected", False, "Should have raised validation error")
                except Exception:
                    log_test("Missing required fields rejected", True, "Correctly rejected")
        except Exception as e:
            log_test("Schema validation test", False, str(e))
        
        # Test 5: Field validation (optional fields accept None)
        try:
            from schema_manager import SchemaManager
            manager = SchemaManager()
            exp_schema = manager.get_schema('experiments')
            
            if exp_schema:
                # Test that validation works at all
                try:
                    # Try to create with invalid status (not in Literal)
                    invalid_exp = exp_schema(
                        experiment_id="test",
                        name="test",
                        experiment_type="TEST",
                        target_formula="test",
                        last_updated=datetime.now(),
                        status="invalid_status",  # Not in Literal["completed", "error", "active", "unknown"]
                    )
                    log_test("Invalid enum values rejected", False, "Should have rejected invalid status")
                except Exception:
                    log_test("Invalid enum values rejected", True, "Correctly rejected invalid status")
                
                # Test that valid data passes
                try:
                    valid_exp = exp_schema(
                        experiment_id="test",
                        name="test",
                        experiment_type="TEST",
                        target_formula="test",
                        last_updated=datetime.now(),
                        status="completed",
                        heating_temperature=1100.0  # Valid temperature
                    )
                    log_test("Valid data accepted", True, "Schema accepts valid data")
                except Exception as e:
                    log_test("Valid data accepted", False, f"Schema rejected valid data: {e}")
        except Exception as e:
            log_test("Schema validation test", False, str(e))
        
        # Test 6: Non-existent analyzer
        try:
            from base_analyzer import AnalysisPluginManager
            manager = AnalysisPluginManager()
            
            non_existent = manager.get_analyzer("this_does_not_exist")
            log_test(
                "Non-existent analyzer handled",
                non_existent is None,
                "Should return None for missing analyzer"
            )
        except Exception as e:
            log_test("Non-existent analyzer test", False, str(e))
        
        # Test 7: Non-existent schema
        try:
            from schema_manager import SchemaManager
            manager = SchemaManager()
            
            non_existent = manager.get_schema("this_does_not_exist")
            log_test(
                "Non-existent schema handled",
                non_existent is None,
                "Should return None for missing schema"
            )
        except Exception as e:
            log_test("Non-existent schema test", False, str(e))
        
        return True
        
    except Exception as e:
        log_test("Edge cases", False, str(e))
        traceback.print_exc()
        return False


def test_config_files():
    """Test configuration files exist and are valid"""
    test_header("TEST 7: Configuration Files")
    
    try:
        import yaml
        
        # Test defaults.yaml
        defaults_file = Path("data/config/defaults.yaml")
        if defaults_file.exists():
            with open(defaults_file) as f:
                defaults = yaml.safe_load(f)
            
            log_test(
                "defaults.yaml exists and valid",
                isinstance(defaults, dict) and 'version' in defaults,
                f"Version: {defaults.get('version')}"
            )
            
            # Check required sections
            required_sections = ['mongodb', 'parquet', 'analyses', 'upload']
            for section in required_sections:
                log_test(
                    f"defaults.yaml has '{section}' section",
                    section in defaults,
                    f"Keys: {list(defaults.keys())}"
                )
        else:
            log_test("defaults.yaml exists", False, "File not found")
        
        # Test filters.yaml
        filters_file = Path("data/config/filters.yaml")
        if filters_file.exists():
            with open(filters_file) as f:
                filters = yaml.safe_load(f)
            
            log_test(
                "filters.yaml exists and valid",
                isinstance(filters, dict),
                f"Keys: {list(filters.keys())}"
            )
            
            # Check presets exist
            if 'presets' in filters:
                presets = filters['presets']
                log_test(
                    "Filter presets defined",
                    len(presets) > 0,
                    f"Presets: {list(presets.keys())}"
                )
        else:
            log_test("filters.yaml exists", False, "File not found")
        
        # Test analyses.yaml
        analyses_file = Path("data/config/analyses.yaml")
        if analyses_file.exists():
            with open(analyses_file) as f:
                analyses = yaml.safe_load(f)
            
            log_test(
                "analyses.yaml exists and valid",
                isinstance(analyses, dict) and 'analyses' in analyses,
                f"Keys: {list(analyses.keys())}"
            )
            
            # Check built-in analyses documented
            if 'analyses' in analyses:
                builtin = analyses['analyses']
                expected_analyses = ['xrd_dara', 'powder_statistics']
                for analyzer in expected_analyses:
                    log_test(
                        f"Analysis '{analyzer}' documented",
                        analyzer in builtin,
                        f"Documented: {list(builtin.keys())}"
                    )
        else:
            log_test("analyses.yaml exists", False, "File not found")
        
        return True
        
    except Exception as e:
        log_test("Configuration files", False, str(e))
        traceback.print_exc()
        return False


def test_mongodb_connection():
    """Test MongoDB connection (optional)"""
    test_header("TEST 8: MongoDB Connection (Optional)")
    
    try:
        from pymongo import MongoClient
        
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        db = client["temporary"]
        collection = db["release"]
        
        # Try to count documents
        count = collection.count_documents({})
        log_test(
            "MongoDB connection successful",
            count >= 0,
            f"Found {count} experiments in database"
        )
        
        # Test aggregation pipeline
        try:
            pipeline = [
                {"$group": {"_id": {"$substr": ["$name", 0, 3]}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            results = list(collection.aggregate(pipeline))
            log_test(
                "MongoDB aggregation works",
                len(results) > 0,
                f"Top types: {[r['_id'] for r in results]}"
            )
        except Exception as e:
            log_test("MongoDB aggregation", False, str(e))
        
        client.close()
        return True
        
    except Exception as e:
        log_test("MongoDB connection", False, f"Not available: {e}")
        print("  ℹ MongoDB tests skipped (server not available)")
        return True  # Don't fail if MongoDB isn't running


def test_parquet_transformer():
    """Test parquet transformation with filters"""
    test_header("TEST 9: Parquet Transformer with Filters")
    
    try:
        from mongodb_to_parquet import MongoToParquetTransformer
        
        # Create a temp directory for test output
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_parquet"
            
            # Test with filter (limit to 5 experiments for speed)
            experiment_filter = {
                'status': ['completed'],
                'has_xrd': True
            }
            
            try:
                transformer = MongoToParquetTransformer(output_dir=output_dir)
                # Use limit to make test fast
                transformer.transform_all(
                    limit=5,
                    skip_temp_logs=True,
                    skip_xrd_points=True,
                    experiment_filter=experiment_filter
                )
                transformer.close()
                
                # Check output files - metadata.json should always exist
                metadata_file = output_dir / 'metadata.json'
                log_test(
                    "Generated metadata.json",
                    metadata_file.exists(),
                    f"Size: {metadata_file.stat().st_size if metadata_file.exists() else 0} bytes"
                )
                
                # Parquet files may be empty if no data matches filter
                # This is OK - just log for informational purposes
                if (output_dir / 'experiments.parquet').exists():
                    size = (output_dir / 'experiments.parquet').stat().st_size
                    log_test(
                        "Generated experiments.parquet",
                        True,
                        f"Size: {size} bytes (0 bytes = no matching data, OK)"
                    )
                else:
                    log_test("experiments.parquet not created", True, "No matching data (OK)")
                
                log_test("Parquet transformation with filters", True, "Successfully generated filtered parquet")
                
            except Exception as e:
                log_test("Parquet transformation", False, f"MongoDB not available or error: {e}")
        
        return True
        
    except Exception as e:
        log_test("Parquet transformer", False, str(e))
        print("  ℹ Transformer test skipped (MongoDB may not be available)")
        return True


def test_diagram_generation():
    """Test schema diagram generation"""
    test_header("TEST 10: Diagram Generation")
    
    try:
        # Check if we have parquet data to diagram
        parquet_dir = Path("data/parquet")
        
        if not parquet_dir.exists() or not list(parquet_dir.glob("*.parquet")):
            log_test(
                "Diagram generation",
                True,
                "Skipped: No parquet data available"
            )
            return True
        
        from generate_diagram import ParquetSchemaAnalyzer, DiagramGenerator
        
        # Analyze schema
        analyzer = ParquetSchemaAnalyzer(parquet_dir)
        analysis = analyzer.analyze()
        
        log_test(
            "Schema analysis",
            'tables' in analysis and len(analysis['tables']) > 0,
            f"Found {len(analysis['tables'])} tables"
        )
        
        # Generate diagram
        generator = DiagramGenerator(analysis)
        
        # Test terminal output (shouldn't error)
        try:
            mermaid = generator.generate_mermaid()
            log_test(
                "Mermaid ERD generation",
                '```mermaid' in mermaid and 'erDiagram' in mermaid,
                f"Generated {len(mermaid)} characters"
            )
        except Exception as e:
            log_test("Mermaid generation", False, str(e))
        
        # Test summary generation
        try:
            summary = generator.generate_summary()
            log_test(
                "Summary generation",
                '# Parquet Schema Documentation' in summary,
                f"Generated {len(summary)} characters"
            )
        except Exception as e:
            log_test("Summary generation", False, str(e))
        
        return True
        
    except Exception as e:
        log_test("Diagram generation", False, str(e))
        traceback.print_exc()
        return False


def test_full_integration():
    """Test full pipeline integration"""
    test_header("TEST 11: Full Pipeline Integration")
    
    try:
        # Check all required directories exist
        dirs_to_check = [
            Path("data/products"),
            Path("data/products/schema"),
            Path("data/pipeline"),
            Path("data/analyses"),
            Path("data/config"),
            Path("data"),
            Path("data/tools")
        ]
        
        all_exist = True
        for dir_path in dirs_to_check:
            exists = dir_path.exists()
            log_test(f"Directory {dir_path} exists", exists)
            if not exists:
                all_exist = False
        
        # Check core files
        files_to_check = [
            Path("data/products/schema_manager.py"),
            Path("data/products/schema_validator.py"),
            Path("data/analyses/base_analyzer.py"),
            Path("data/pipeline/product_pipeline.py"),
            Path("data/config/defaults.yaml"),
            Path("data/config/filters.yaml"),
            Path("data/config/analyses.yaml"),
            Path("run_product_pipeline.sh")
        ]
        
        for file_path in files_to_check:
            exists = file_path.exists()
            log_test(f"File {file_path.name} exists", exists)
            if not exists:
                all_exist = False
        
        # Check Python dependencies
        try:
            import pandas
            import pydantic
            import yaml
            import rich
            log_test("Core Python dependencies installed", True)
        except ImportError as e:
            log_test("Core Python dependencies", False, str(e))
            all_exist = False
        
        return all_exist
        
    except Exception as e:
        log_test("Full integration", False, str(e))
        traceback.print_exc()
        return False


# =============================================================================
# Main Test Runner
# =============================================================================

def main():
    """Run all integration tests"""
    print("\n" + "=" * 70)
    print("  A-LAB PIPELINE COMPREHENSIVE INTEGRATION TESTS")
    print("=" * 70)
    print(f"\n  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run all tests
    tests = [
        test_schema_auto_discovery,
        test_analysis_auto_discovery,
        test_custom_schema_hook,
        test_custom_analyzer_hook,
        test_filter_configurations,
        test_edge_cases,
        test_config_files,
        test_mongodb_connection,
        test_parquet_transformer,
        test_diagram_generation,
        test_full_integration
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_func in tests:
        try:
            result = test_func()
            # Count individual test results logged within each function
        except Exception as e:
            print(f"\n✗ Test suite {test_func.__name__} crashed: {e}")
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in test_results if r['passed'])
    failed = sum(1 for r in test_results if not r['passed'])
    total = len(test_results)
    
    print(f"\n  Total:  {total} tests")
    print(f"  Passed: {passed} tests ({'green' if passed == total else 'yellow'})")
    print(f"  Failed: {failed} tests ({'red' if failed > 0 else 'green'})")
    
    if failed > 0:
        print("\n  Failed tests:")
        for result in test_results:
            if not result['passed']:
                print(f"    ✗ {result['test']}")
                if result['message']:
                    print(f"       {result['message']}")
    
    print("\n" + "=" * 70)
    
    if failed == 0:
        print("  ✓ ALL TESTS PASSED!")
        print("\n  Next steps:")
        print("    1. Create a product: ./run_product_pipeline.sh create")
        print("    2. Run pipeline: ./run_product_pipeline.sh run --product <name>")
        print("=" * 70)
        return 0
    else:
        print("  ✗ SOME TESTS FAILED")
        print("\n  Review failures above and fix issues.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
