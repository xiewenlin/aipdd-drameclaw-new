## ADDED Requirements

### Requirement: Resolve a model by feature identifier
Cloud model callers MUST request a runtime model by stable feature identifier instead of reading Provider-specific credentials, Base URLs, transport-prefixed model names, or official channel state.

#### Scenario: Resolve a globally bound feature
- **WHEN** a task requests a feature with a valid global binding
- **THEN** the resolver returns the custom NewAPI connection, bound model identifier, and protocol adapter for that feature

### Requirement: Enforce one global binding across all projects
The resolver SHALL select models only from the global feature bindings and MUST NOT allow a request or project configuration to override the selected model.

#### Scenario: Legacy project model field exists
- **WHEN** a project contains a legacy image selection or video backend and the requested feature has a global binding
- **THEN** the resolver selects the global binding and does not use the project value

#### Scenario: Request attempts to select another model
- **WHEN** a request includes a model identifier that differs from the global feature binding
- **THEN** the system rejects or ignores the model override and uses the global binding according to the API contract

### Requirement: Fail when runtime configuration is incomplete
The resolver MUST return a structured error when the NewAPI connection is missing, the feature has no effective binding, or the selected model is unavailable.

#### Scenario: Feature is not configured
- **WHEN** a task requests a feature with no request, project, or global model selection
- **THEN** the task fails before provider invocation with an error naming the missing feature

#### Scenario: Selected model is unavailable
- **WHEN** a task resolves to a catalog model marked unavailable
- **THEN** the task fails before provider invocation and requests configuration repair

### Requirement: Route all cloud operations through custom NewAPI
Text, image, video, audio, and embedding cloud adapters SHALL use the active custom NewAPI Base URL and credential returned by the resolver.

#### Scenario: Generate an image
- **WHEN** an image task resolves a configured image feature
- **THEN** the image adapter sends the request to the custom NewAPI endpoint with the bound model identifier

#### Scenario: Generate a video
- **WHEN** a video task resolves a configured video feature
- **THEN** the video adapter creates and polls the NewAPI task without reading a direct cloud Provider credential

### Requirement: Keep local computation transports explicit
The system MAY retain explicitly configured local computation transports, and those transports MUST be represented separately from cloud model bindings.

#### Scenario: Project uses local ComfyUI
- **WHEN** a project explicitly selects an allowed local ComfyUI transport
- **THEN** the local task bypasses NewAPI without enabling any direct cloud Provider route

### Requirement: Migrate legacy model selections safely
The system SHALL provide a dry-run migration for legacy global logical models, image selections, video backends, audio settings, embedding settings, and project-level model fields before writing global bindings or removing legacy fields.

#### Scenario: Legacy value can be mapped
- **WHEN** dry-run finds a legacy value matching a synchronized model
- **THEN** the report shows the proposed global feature binding or legacy project field removal without modifying configuration

#### Scenario: Legacy value cannot be mapped
- **WHEN** dry-run cannot match a legacy value
- **THEN** the report marks it unresolved and leaves the original value intact
