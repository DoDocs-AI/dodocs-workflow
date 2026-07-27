# demo Specification

## Purpose

Sample capability used by tests/validate-openspec.sh to prove the spec format
dodocs-workflow agents write stays compatible with the pinned OpenSpec CLI.

## Requirements

### Requirement: Demo listing

The system SHALL list demo items in reverse chronological order.

#### Scenario: Default ordering

- GIVEN three demo items created on different days
- WHEN the user opens the demo list
- THEN the newest item SHALL appear first
