# ADR-0010: Owner password and opaque bearer sessions

- **Decision ID:** ADR-0010
- **Status:** Implemented for P-01 conditional backend
- **Context:** Local administrative API needs owner-controlled authentication without plaintext passwords or hardcoded credentials.
- **Problem:** Protect administrative endpoints in a loopback desktop-backend deployment.
- **Options considered:** No auth because localhost; hardcoded token; password hash plus opaque sessions; OS-integrated auth immediately.
- **Selected decision:** Argon2id owner password hash, random opaque bearer token, SHA-256 token hash storage, expiry and revocation.
- **Reasons:** Avoids plaintext/default credentials and supports testable session lifecycle.
- **Consequences:** Owner must bootstrap via CLI. Windows Credential Manager/DPAPI integration remains future work. Bearer tokens must be protected by the client; HTTPS/remote access are not enabled.
