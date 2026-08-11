## ADDED Requirements

### Requirement: Synchronize models from NewAPI
The system SHALL retrieve models from the active NewAPI `/models` endpoint and merge them into a local model catalog.

#### Scenario: First successful synchronization
- **WHEN** NewAPI returns a list of model identifiers
- **THEN** the system creates catalog entries and records the synchronization timestamp

#### Scenario: Synchronization fails
- **WHEN** NewAPI is unreachable or returns an invalid response
- **THEN** the system retains the previous catalog and reports the failure without partially replacing it

### Requirement: Preserve local model metadata
The system MUST preserve manual capability assignments and feature bindings when an existing model appears in a later synchronization.

#### Scenario: Existing model is synchronized again
- **WHEN** a model with manual capabilities is returned by NewAPI
- **THEN** the system updates upstream metadata without replacing its manual capabilities or bindings

### Requirement: Track unavailable models
The system SHALL mark previously synchronized models as unavailable when absent from a successful complete synchronization and MUST NOT silently delete them.

#### Scenario: Bound model disappears
- **WHEN** a successful synchronization no longer contains a model that is bound to a feature
- **THEN** the model and binding remain visible with an unavailable status

### Requirement: Classify model capabilities without enforcing them
The system SHALL store detected capabilities and optional manual capabilities for each model, and MUST treat an unrecognized model as `unknown` rather than assigning it to a feature.

#### Scenario: Recognizable embedding model
- **WHEN** metadata or configured detection rules identify an embedding model
- **THEN** the catalog recommends the `embedding` capability without binding the model automatically

#### Scenario: Unrecognized model
- **WHEN** no reliable capability can be inferred
- **THEN** the catalog records `unknown` and leaves all feature bindings unchanged

### Requirement: Support manual capability correction
The system SHALL allow an administrator to assign one or more capabilities to any synchronized model.

#### Scenario: Assign multiple capabilities
- **WHEN** the administrator marks a model as both `llm` and `vision_llm`
- **THEN** the catalog uses both manual capabilities for recommendation and filtering
