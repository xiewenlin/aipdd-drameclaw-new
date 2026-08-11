## ADDED Requirements

### Requirement: Publish a server-owned feature catalog
The system SHALL publish stable feature identifiers with display metadata, recommended model capabilities, required status, and supported test operation.

#### Scenario: Configuration page loads
- **WHEN** the client requests the feature catalog
- **THEN** the server returns all configurable text, vision, image, video, audio, and embedding features

### Requirement: Bind models explicitly to features
The system SHALL allow each feature to bind one synchronized model or remain unconfigured, and MUST NOT create bindings automatically after model synchronization.

#### Scenario: Bind an image model
- **WHEN** the administrator selects a model for the `render_image` feature and saves
- **THEN** the system persists that exact model identifier as the global binding

#### Scenario: Leave a feature unconfigured
- **WHEN** the administrator clears a feature selection
- **THEN** the system persists a null binding and does not substitute a product default

### Requirement: Recommend models by capability
The configuration page SHALL prioritize available models whose effective capabilities match the selected feature.

#### Scenario: Open a text feature selector
- **WHEN** the administrator opens a feature that recommends `llm`
- **THEN** matching available models appear in the recommended list before other models

### Requirement: Allow selecting any synchronized model
The configuration page MUST provide an all-models view that permits binding any available synchronized model regardless of detected or manual capability.

#### Scenario: Select an unknown model
- **WHEN** the administrator enables the all-models view and selects an `unknown` model
- **THEN** the system allows the binding and displays a capability mismatch warning without blocking save

### Requirement: Validate bindings without hidden fallback
The system SHALL report missing, unavailable, and capability-mismatched bindings separately and MUST NOT silently replace them.

#### Scenario: Required feature has no binding
- **WHEN** configuration validation runs and a required feature is unconfigured
- **THEN** the result identifies the feature as missing and does not select another model

#### Scenario: Binding references an unavailable model
- **WHEN** configuration validation runs after a bound model becomes unavailable
- **THEN** the result identifies both the feature and unavailable model

### Requirement: Test a feature binding
The system SHALL allow an administrator to run a minimal protocol-specific test for a configured feature.

#### Scenario: Test an embedding binding
- **WHEN** the administrator tests a configured embedding feature
- **THEN** the system calls the NewAPI embedding adapter with a minimal input and reports success or an actionable failure
