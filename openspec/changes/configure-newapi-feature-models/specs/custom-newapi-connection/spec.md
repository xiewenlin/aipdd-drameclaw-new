## ADDED Requirements

### Requirement: Configure one custom NewAPI connection
The system SHALL allow an administrator to configure exactly one active custom NewAPI API Base URL and API Key for all cloud model operations.

#### Scenario: Save a valid connection
- **WHEN** the administrator submits a valid NewAPI URL and a non-empty API Key
- **THEN** the system stores the normalized API Base URL and protected credential as the active cloud model connection

#### Scenario: Preserve an existing key
- **WHEN** the administrator updates the URL while leaving the replacement API Key empty
- **THEN** the system preserves the previously stored API Key

### Requirement: Normalize NewAPI URLs
The system MUST accept NewAPI URLs with or without a trailing slash and with or without the `/v1` suffix, and SHALL derive endpoints without duplicating path segments.

#### Scenario: URL already contains version path
- **WHEN** the administrator enters a URL ending in `/v1/`
- **THEN** the model list endpoint resolves to exactly one `/v1/models` path

### Requirement: Test the NewAPI connection
The system SHALL provide a connection test that calls the configured model-list endpoint with the configured credential and reports an actionable result.

#### Scenario: Authentication fails
- **WHEN** NewAPI rejects the credential
- **THEN** the system reports an authentication error without exposing the API Key

#### Scenario: Connection succeeds
- **WHEN** NewAPI returns a valid model-list response
- **THEN** the system records and displays a successful test status and timestamp

### Requirement: Keep secrets out of responses and logs
The system MUST NOT return the complete API Key from configuration APIs or write Authorization values to application logs.

#### Scenario: Read connection settings
- **WHEN** a client loads the configuration page
- **THEN** the API indicates whether a credential exists without returning its complete value

### Requirement: Display an official service link only
The system SHALL expose an optional server-configured official service URL as a normal external link and MUST NOT use that URL as a runtime model channel.

#### Scenario: Official link is configured
- **WHEN** `official_service_url` is present
- **THEN** the configuration page displays it as an external link that does not modify the active NewAPI connection

#### Scenario: Official link is absent
- **WHEN** `official_service_url` is empty
- **THEN** the configuration page hides the official service entry
