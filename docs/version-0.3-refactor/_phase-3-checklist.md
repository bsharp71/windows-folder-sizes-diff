# Phase 3 Implementation Checklist

## 1. Database Migration (Alembic 0003)
- [x] Add `parent_directory_id` INTEGER NULL FK → directories.id to directories
- [x] Add `depth` INTEGER NOT NULL DEFAULT 0 to directories
- [x] Add indexes: directories(parent_directory_id), directories(depth)
- [x] Add `inclusive_logical_bytes` INTEGER NULL to directory_observations
- [x] Add `inclusive_file_count` INTEGER NULL to directory_observations
- [x] Add `direct_child_count` INTEGER NOT NULL DEFAULT 0 to directory_observations
- [x] Add `descendant_directory_count` INTEGER NULL to directory_observations
- [x] Add `hierarchy_status` TEXT NOT NULL DEFAULT 'pending' to directory_observations
- [x] Add `hierarchy_algorithm_version` INTEGER NOT NULL DEFAULT 0 to scans
- [x] Add `direct_measurement_status` TEXT NOT NULL DEFAULT 'not_started' to scans
- [x] Add `hierarchy_aggregation_status` TEXT NOT NULL DEFAULT 'not_started' to scans

## 2. ORM Models
- [x] Update Directory model: parent_directory_id, depth
- [x] Update DirectoryObservation model: inclusive fields, hierarchy_status
- [x] Update Scan model: hierarchy_algorithm_version, direct_measurement_status, hierarchy_aggregation_status

## 3. Scanner Models
- [x] Update FolderObservation: add parent_path, depth, direct_child_count

## 4. Scanner
- [x] Update FolderScanner to track parent_path and depth during traversal
- [x] Emit direct_child_count in observations

## 5. Repositories
- [x] Update DirectoryRepository.ensure_many for parent_directory_id and depth
- [x] Update ObservationRepository.insert_many for new fields

## 6. Hierarchy Aggregation (analysis/hierarchy.py)
- [x] Create HierarchyAggregator class
- [x] Implement bottom-up iterative aggregation
- [x] Implement hierarchy validation (orphans, cycles, depth consistency)
- [x] Implement partial status propagation
- [x] Batch persistence of inclusive results

## 7. Differ Updates
- [x] Update DirectoryDiff model with direct/inclusive fields
- [x] Update ScanDiffSummary with hierarchy-aware totals
- [x] Update ScanDiffer to calculate direct and inclusive deltas

## 8. Persistence Updates
- [x] Run hierarchy aggregation after scan completion
- [x] Handle hierarchy aggregation failure gracefully

## 9. Configuration
- [x] Add HIERARCHY_ALGORITHM_VERSION constant
- [x] Update configuration hash to include hierarchy version

## 10. GUI Updates
- [x] Update main window for direct/inclusive display
- [x] Add hierarchy toggle (direct growth / folder tree)
- [x] Update folder detail panel
- [x] Update summary panel

## 11. CLI Updates
- [x] Add --tree option to report command
- [x] Add --direct-only option
- [x] Add folder-show command
- [x] Update compare command output

## 12. Text Reports
- [x] Update text log writer for direct/inclusive terminology
- [x] Add hierarchy summary section
- [x] Add non-overlapping total warnings

## 13. Tests
- [x] Direct and inclusive size tests
- [x] Nested hierarchy test
- [x] Parent/child double-count test
- [x] Root direct file test
- [x] Multiple branches test
- [x] File deletion test
- [x] Directory removal test
- [x] New directory tree test
- [x] Inaccessible descendant test
- [x] Orphan test
- [x] Cycle test
- [x] Migration test
- [x] Report total test

## 10. GUI Updates
- [ ] Update main window for direct/inclusive display
- [ ] Add hierarchy toggle (direct growth / folder tree)
- [ ] Update folder detail panel
- [ ] Update summary panel

## 11. CLI Updates
- [ ] Add --tree option to report command
- [ ] Add --direct-only option
- [ ] Add folder-show command
- [ ] Update compare command output

## 12. Text Reports
- [ ] Update text log writer for direct/inclusive terminology
- [ ] Add hierarchy summary section
- [ ] Add non-overlapping total warnings

## 13. Tests
- [ ] Direct and inclusive size tests
- [ ] Nested hierarchy test
- [ ] Parent/child double-count test
- [ ] Root direct file test
- [ ] Multiple branches test
- [ ] File deletion test
- [ ] Directory removal test
- [ ] New directory tree test
- [ ] Inaccessible descendant test
- [ ] Orphan test
- [ ] Cycle test
- [ ] Migration test
- [ ] Report total test