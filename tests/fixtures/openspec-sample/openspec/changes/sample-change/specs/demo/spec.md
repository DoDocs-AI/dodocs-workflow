## ADDED Requirements

### Requirement: Greeting on first visit

The system SHALL greet the user by name on their first visit of the day.

#### Scenario: First visit of the day

- GIVEN a logged-in user who has not visited today
- WHEN they open the dashboard
- THEN a greeting with their display name SHALL be shown

## MODIFIED Requirements

### Requirement: Demo listing

The system SHALL list demo items in reverse chronological order, with greeted items
pinned to the top of the list.

#### Scenario: Default ordering

- GIVEN three demo items created on different days
- WHEN the user opens the demo list
- THEN the newest item SHALL appear first

#### Scenario: Greeted item pinned

- GIVEN a demo item that has been greeted today
- WHEN the user opens the demo list
- THEN the greeted item SHALL appear before all non-greeted items
